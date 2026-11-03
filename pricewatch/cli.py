import argparse
import os
import subprocess
import sys

from . import STORES, db
from .extract import FetchError, fetch_price


def notify(title, message):
    """Show a macOS notification; silently skipped elsewhere, or when PRICEWATCH_QUIET is set
    (price lookups run by Claude set it, so filling in a new product doesn't pop up alerts)."""
    if os.environ.get("PRICEWATCH_QUIET"):
        return
    script = 'display notification {} with title {}'.format(
        _applescript_str(message), _applescript_str(title)
    )
    try:
        subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
    except FileNotFoundError:
        pass


def _applescript_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def display_name(product):
    return product["name"] + (" " + product["name_zh"] if product["name_zh"] else "")


def unit_money(v):
    """Unit prices under $1 (per egg, per oz) need a third decimal to be comparable."""
    return "${:.3f}".format(v) if v < 1 else "${:.2f}".format(v)


def record_and_alert(conn, product_id, store, price, qty=1, source="manual", note=None, url=None, variant="",
                     verified=True):
    """Record a pack price for one variant at a store; return alerts for drops, targets and a new cheapest store.

    A store can carry several variants (brands/sizes) of the same product, each tracked separately.
    """
    product = db.get_product(conn, product_id)
    before = next(p for p in db.overview(conn) if p["id"] == product_id)
    old = next((l for l in before["listings"] if l["store"] == store and l["variant"] == variant), None)

    listing_id = db.get_or_create_listing(conn, product_id, store, variant=variant, url=url, qty=qty if url else None)
    db.record_price(conn, listing_id, price, qty=qty, source=source, note=note, verified=verified)

    unit = price / qty
    name = display_name(product)
    store_name = STORES.get(store, store)
    per = "/" + product["unit"]
    alerts = []
    if old and old["unit_price"] is not None and unit < old["unit_price"] - 1e-9:
        alerts.append("{} dropped at {}: {} → {}{}".format(
            name, store_name, unit_money(old["unit_price"]), unit_money(unit), per))
    others = [l["unit_price"] for l in before["listings"]
              if not (l["store"] == store and l["variant"] == variant) and l["unit_price"] is not None]
    was_best = before["best_store"] == store
    if others and not was_best and unit < min(others):
        alerts.append("{} is now cheapest at {}: {}{}".format(name, store_name, unit_money(unit), per))
    target = product["target_price"]
    if target is not None and unit <= target:
        alerts.append("{} hit target at {}: {}{} (target {})".format(
            name, store_name, unit_money(unit), per, unit_money(target)))
    for msg in alerts:
        print("  🔔 " + msg)
        notify("Grocery price alert", msg)
    return alerts


def _store(store):
    if store not in STORES:
        sys.exit("未知超市: {}。可选: {}".format(store, ", ".join(STORES)))
    return store


def _product(conn, product_id):
    p = db.get_product(conn, product_id)
    if not p:
        sys.exit("没有 #{} 这个商品".format(product_id))
    return p


def cmd_add(conn, args):
    pid = db.add_product(conn, args.name, args.unit, args.zh, args.target)
    print("已添加 #{}: {}（按 {} 比价）".format(pid, display_name(db.get_product(conn, pid)), args.unit))


def cmd_record(conn, args):
    _product(conn, args.product_id)
    variant = args.variant or ""
    record_and_alert(conn, args.product_id, _store(args.store), args.price, args.qty, note=args.note, variant=variant,
                     verified=not args.unverified)
    label = STORES[args.store] + (" ({})".format(variant) if variant else "")
    print("已记录 #{} @ {}: ${:.2f} / {:g}".format(args.product_id, label, args.price, args.qty))


def cmd_link(conn, args):
    _product(conn, args.product_id)
    db.get_or_create_listing(conn, args.product_id, _store(args.store), variant=args.variant or "", url=args.url, qty=args.qty)
    print("已关联 #{} @ {}，`check` 时会自动抓价".format(args.product_id, STORES[args.store]))


def cmd_set(conn, args):
    _product(conn, args.product_id)
    db.update_product(conn, args.product_id, name=args.name, name_zh=args.zh, unit=args.unit, category=args.category)
    p = db.get_product(conn, args.product_id)
    print("已更新 #{}: {}（按 {} 比价，分类 {}）".format(p["id"], display_name(p), p["unit"], p["category"]))


def cmd_remove(conn, args):
    db.remove_product(conn, args.product_id)
    print("已删除 #{}".format(args.product_id))


def cmd_compare(conn, args):
    products = db.overview(conn)
    if not products:
        print("还没有商品。用 `python3 -m pricewatch add` 添加。")
        return
    for p in products:
        if args.product_id and p["id"] != args.product_id:
            continue
        print("#{} {}  (per {})".format(p["id"], display_name(p), p["unit"]))
        if not p["listings"]:
            print("    还没有价格")
        for l in p["listings"]:
            if l["unit_price"] is None:
                continue
            best = "  ← 最便宜" if l["store"] == p["best_store"] else ""
            label = STORES.get(l["store"], l["store"]) + (" ({})".format(l["variant"]) if l["variant"] else "")
            print("    {:<28} {:>9}/{:<6} (${:.2f} / {:g}){}".format(
                label, unit_money(l["unit_price"]), p["unit"],
                l["price"], l["qty"], best))
        print()


def cmd_check(conn, args):
    """Fetch the current price of every store listing that has a product URL."""
    listings = db.listings_with_url(conn)
    if args.store:
        listings = [l for l in listings if l["store"] == args.store]
    if not listings:
        print("没有带链接的商品可以自动抓取。")
        return
    failed = 0
    for l in listings:
        label = "{} @ {}".format(display_name(l), STORES.get(l["store"], l["store"]))
        try:
            price = fetch_price(l["url"])
        except FetchError as e:
            print("✗ {}: 抓取失败 ({})".format(label, e))
            failed += 1
            continue
        if price is None:
            print("✗ {}: 页面上没找到价格（这家店可能需要手动记录）".format(label))
            failed += 1
            continue
        print("✓ {}: ${:.2f}".format(label, price))
        record_and_alert(conn, l["product_id"], l["store"], price, l["qty"], source="auto", variant=l["variant"])
    if failed:
        print("\n{} 个没抓到价格，可以用 `record` 手动记录。".format(failed))


def cmd_refresh(conn, args):
    """Look up every tracked product again with Claude, one at a time (the weekly refresh)."""
    from . import lookup
    products = db.overview(conn)
    if args.product_id:
        products = [p for p in products if p["id"] == args.product_id]
    print("{}  开始查价：{} 个商品".format(db.now(), len(products)), flush=True)
    for p in products:
        state, message = lookup.lookup_once(p["id"])
        print("{}  #{} {}: {} — {}".format(db.now(), p["id"], display_name(p), state, message), flush=True)
    print("{}  查价结束".format(db.now()), flush=True)


def cmd_serve(conn, args):
    from .server import serve
    serve(args.port)


def main(argv=None):
    p = argparse.ArgumentParser(prog="pricewatch", description="买菜比价")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="添加要比价的商品")
    a.add_argument("name", help="英文名")
    a.add_argument("--zh", help="中文名")
    a.add_argument("--unit", required=True, help="比价单位，如 lb、egg、oz")
    a.add_argument("--target", type=float, help="目标单价，任一超市低于等于时提醒")
    a.set_defaults(func=cmd_add)

    r = sub.add_parser("record", help="记录某超市的价格")
    r.add_argument("product_id", type=int)
    r.add_argument("store", help="超市: " + ", ".join(STORES))
    r.add_argument("price", type=float, help="整包价格")
    r.add_argument("--qty", type=float, default=1, help="一包有几个单位（默认 1）")
    r.add_argument("--note", help="备注，如 '打折'、'会员价'")
    r.add_argument("--variant", help="这家店卖的具体品牌/规格，如 \"Eggland's Best 12ct\"（同一家店可以有多个variant）")
    r.add_argument("--unverified", action="store_true", help="价格来自超市官网的搜索结果，没能在商品页上确认")
    r.set_defaults(func=cmd_record)

    k = sub.add_parser("link", help="给某超市的商品关联页面链接，用于自动抓价")
    k.add_argument("product_id", type=int)
    k.add_argument("store")
    k.add_argument("url")
    k.add_argument("--qty", type=float, default=1, help="这个链接的一包有几个单位")
    k.add_argument("--variant", help="这家店卖的具体品牌/规格")
    k.set_defaults(func=cmd_link)

    st = sub.add_parser("set", help="修改商品的英文名、中文名或比价单位")
    st.add_argument("product_id", type=int)
    st.add_argument("--name", help="英文名")
    st.add_argument("--zh", help="中文名")
    st.add_argument("--unit", help="比价单位，如 lb、egg、fl oz")
    st.add_argument("--category", choices=db.CATEGORIES,
                     help="分类：meat 肉类、seafood 海鲜、vegetable 蔬菜、fruit 水果、dairy 蛋奶、pantry 干货调料、other 其他")
    st.set_defaults(func=cmd_set)

    rm = sub.add_parser("remove", help="删除商品及其所有价格")
    rm.add_argument("product_id", type=int)
    rm.set_defaults(func=cmd_remove)

    c = sub.add_parser("compare", help="对比各超市的单价")
    c.add_argument("product_id", type=int, nargs="?")
    c.set_defaults(func=cmd_compare)

    ch = sub.add_parser("check", help="自动抓取所有带链接的价格")
    ch.add_argument("--store", help="只抓这家超市")
    ch.set_defaults(func=cmd_check)

    rf = sub.add_parser("refresh", help="用 Claude 重新查所有追踪中的商品价格（每周查价）")
    rf.add_argument("product_id", type=int, nargs="?", help="只查这一个商品")
    rf.set_defaults(func=cmd_refresh)

    s = sub.add_parser("serve", help="打开本地网页看板")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(func=cmd_serve)

    args = p.parse_args(argv)
    conn = db.connect()
    try:
        args.func(conn, args)
    finally:
        conn.close()
