import argparse
import subprocess
import sys

from . import STORES, db
from .extract import FetchError, fetch_price


def notify(title, message):
    """Show a macOS notification; silently skipped elsewhere."""
    script = 'display notification {} with title {}'.format(
        _applescript_str(message), _applescript_str(title)
    )
    try:
        subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
    except FileNotFoundError:
        pass


def _applescript_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def check_alerts(item, new_price, previous):
    """Return alert messages when the new price is a drop or hits the target."""
    alerts = []
    name = "{} @ {}".format(item["name"], STORES.get(item["store"], item["store"]))
    if previous is not None and new_price < previous:
        alerts.append("{} 降价: ${:.2f} → ${:.2f}".format(name, previous, new_price))
    target = item["target_price"]
    if target is not None and new_price <= target:
        alerts.append("{} 达到目标价 ${:.2f}（现价 ${:.2f}）".format(name, target, new_price))
    return alerts


def record_and_alert(conn, item_id, price, source, note=None):
    item = db.get_item(conn, item_id)
    previous = next((i["latest"] for i in db.list_items(conn) if i["id"] == item_id), None)
    db.record_price(conn, item_id, price, source=source, note=note)
    alerts = check_alerts(item, price, previous)
    for msg in alerts:
        print("  🔔 " + msg)
        notify("买菜价格提醒", msg)
    return alerts


def cmd_add(conn, args):
    if args.store not in STORES:
        sys.exit("未知超市: {}。可选: {}".format(args.store, ", ".join(STORES)))
    item_id = db.add_item(conn, args.name, args.store, args.url, args.unit, args.target)
    print("已添加 #{}: {} @ {}".format(item_id, args.name, STORES[args.store]))
    if args.price is not None:
        record_and_alert(conn, item_id, args.price, "manual")
        print("  记录价格 ${:.2f}".format(args.price))


def cmd_record(conn, args):
    if not db.get_item(conn, args.item_id):
        sys.exit("没有 #{} 这个商品".format(args.item_id))
    record_and_alert(conn, args.item_id, args.price, "manual", args.note)
    print("已记录 #{}: ${:.2f}".format(args.item_id, args.price))


def cmd_remove(conn, args):
    db.remove_item(conn, args.item_id)
    print("已删除 #{}".format(args.item_id))


def cmd_list(conn, args):
    items = db.list_items(conn)
    if not items:
        print("还没有商品。用 `python3 -m pricewatch add` 添加。")
        return
    print("{:>4}  {:<28} {:<18} {:>9} {:>9} {:>9}  {}".format(
        "ID", "商品", "超市", "现价", "最低", "目标", "更新时间"))
    for i in items:
        fmt = lambda v: "-" if v is None else "${:.2f}".format(v)
        print("{:>4}  {:<28} {:<18} {:>9} {:>9} {:>9}  {}".format(
            i["id"], i["name"][:28], STORES.get(i["store"], i["store"]),
            fmt(i["latest"]), fmt(i["lowest"]), fmt(i["target_price"]),
            (i["latest_at"] or "-")[:16].replace("T", " ")))


def cmd_check(conn, args):
    """Fetch the current price of every item that has a product URL."""
    items = [i for i in db.list_items(conn) if i["url"]]
    if args.store:
        items = [i for i in items if i["store"] == args.store]
    if not items:
        print("没有带链接的商品可以自动抓取。")
        return
    failed = 0
    for i in items:
        label = "#{} {} @ {}".format(i["id"], i["name"], STORES.get(i["store"], i["store"]))
        try:
            price = fetch_price(i["url"])
        except FetchError as e:
            print("✗ {}: 抓取失败 ({})".format(label, e))
            failed += 1
            continue
        if price is None:
            print("✗ {}: 页面上没找到价格（这家店可能需要手动记录）".format(label))
            failed += 1
            continue
        print("✓ {}: ${:.2f}".format(label, price))
        record_and_alert(conn, i["id"], price, "auto")
    if failed:
        print("\n{} 个商品没抓到价格，可以用 `record` 手动记录。".format(failed))


def cmd_serve(conn, args):
    from .server import serve
    serve(args.port)


def main(argv=None):
    p = argparse.ArgumentParser(prog="pricewatch", description="买菜价格追踪")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="添加要追踪的商品")
    a.add_argument("name")
    a.add_argument("--store", required=True, help="超市: " + ", ".join(STORES))
    a.add_argument("--url", help="商品页面链接（有链接才能自动抓价格）")
    a.add_argument("--unit", help="规格，如 '1 lb'、'12 ct'")
    a.add_argument("--target", type=float, help="目标价，低于等于时提醒")
    a.add_argument("--price", type=float, help="顺便记录当前价格")
    a.set_defaults(func=cmd_add)

    r = sub.add_parser("record", help="手动记录一次价格")
    r.add_argument("item_id", type=int)
    r.add_argument("price", type=float)
    r.add_argument("--note", help="备注，如 '打折'、'会员价'")
    r.set_defaults(func=cmd_record)

    rm = sub.add_parser("remove", help="删除商品及其价格记录")
    rm.add_argument("item_id", type=int)
    rm.set_defaults(func=cmd_remove)

    sub.add_parser("list", help="列出所有商品和最新价格").set_defaults(func=cmd_list)

    c = sub.add_parser("check", help="自动抓取所有带链接商品的价格")
    c.add_argument("--store", help="只抓这家超市")
    c.set_defaults(func=cmd_check)

    s = sub.add_parser("serve", help="打开本地网页看板")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(func=cmd_serve)

    args = p.parse_args(argv)
    conn = db.connect()
    try:
        args.func(conn, args)
    finally:
        conn.close()
