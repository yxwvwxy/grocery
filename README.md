# 买菜价格追踪

追踪 ShopRite、H Mart、99 Ranch、Target、Costco、Walmart、Trader Joe's、Asian Food Markets 的商品价格，降价或达到目标价时弹出 macOS 通知。只用 Python 自带的库，不用安装任何依赖。数据存在 `data/prices.db`（SQLite）。

## 网页看板

```bash
python3 -m pricewatch serve
```

会在浏览器打开 http://127.0.0.1:8765 ，在上面可以添加商品、记录价格、查看价格走势图。

## 命令行

```bash
python3 -m pricewatch add "鸡蛋 24个" --store costco --unit "24 ct" --target 6 --price 7.49
python3 -m pricewatch record 1 5.89 --note 打折    # 手动记录 #1 的新价格
python3 -m pricewatch list                          # 所有商品的现价、最低价、目标价
python3 -m pricewatch check                         # 自动抓取所有带 --url 的商品
python3 -m pricewatch remove 1
```

超市代号：`shoprite` `hmart` `ranch99` `target` `costco` `walmart` `traderjoes` `asianfood`

## 自动抓价的限制

`check` 会读取商品页面上公开的结构化价格数据（schema.org JSON-LD / meta 标签）。实际情况：

- Walmart、Trader Joe's、ShopRite 会拦截脚本访问（返回验证页或 403）。
- Target 的价格是浏览器里用 JS 渲染出来的，页面源码里没有。
- Asian Food Markets 没有网上价格。

所以这几家目前要**手动记录**（网页看板上点商品 → 输入价格，几秒钟）。拿到小票后批量录入最实际。
