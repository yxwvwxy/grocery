# Grocery Price Compare 买菜比价

对比同一种商品在 ShopRite、H Mart、Costco、99 Ranch、Target、Walmart 的价格。按**单价**（每磅、每个、每盎司…）比较，所以不同包装大小也能直接比。某家店降价、变成最便宜、或达到目标单价时，会弹出 macOS 通知。

只用 Python 自带的库，不用安装依赖。数据存在 `data/prices.db`（SQLite，不会上传到 git）。

## 网页看板（英文界面）

```bash
python3 -m pricewatch serve
```

浏览器会打开 http://127.0.0.1:8765：

- 对比表：每行一个商品（英文名 + 中文名），每列一家超市，最便宜的那格高亮
- 点一个商品：各超市最新单价的柱状图、单价走势图、全部记录，以及记录新价格的表单
- 记录价格时填**整包价格**和**一包有几个单位**，例如 Costco 鸡蛋 $7.49 / 24

## 命令行

```bash
python3 -m pricewatch add Eggs --zh 鸡蛋 --unit egg --target 0.25   # 新商品，按"每个蛋"比价
python3 -m pricewatch record 1 costco 7.49 --qty 24                 # 商品 #1 在 Costco：$7.49 一盒 24 个
python3 -m pricewatch record 1 hmart 3.49 --qty 12 --note sale
python3 -m pricewatch compare                                       # 各超市单价对比
python3 -m pricewatch link 1 target https://www.target.com/p/... --qty 12   # 关联页面，供自动抓价
python3 -m pricewatch check                                         # 自动抓取所有关联了链接的价格
python3 -m pricewatch remove 1
```

超市代号：`shoprite` `hmart` `costco` `ranch99` `target` `walmart`

## 自动抓价的限制

`check` 会读取商品页面上公开的结构化价格数据（schema.org JSON-LD / meta 标签）。实际情况：

- Walmart、ShopRite 会拦截脚本访问（返回验证页或 403）。
- Target 的价格是浏览器里用 JS 渲染出来的，页面源码里没有。

所以大部分价格目前需要**手动记录**，拿到小票后在看板上批量录入最实际。
