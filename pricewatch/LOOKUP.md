# Price lookup instructions

These are the instructions Claude follows when it looks up grocery prices for this app,
both for a single product just added from the dashboard and for the weekly refresh of
every tracked product. All changes go through the `python3 -m pricewatch` command line,
run from the repository root; never edit `data/prices.db` directly.

## Stores and where prices may come from

| Store code | Store | Official sites (the only allowed sources) |
|---|---|---|
| `shoprite` | ShopRite | shoprite.com |
| `hmart` | H Mart | hmart.com, sameday.hmart.com |
| `costco` | Costco | costco.com, sameday.costco.com |
| `ranch99` | 99 Ranch | 99ranch.com, fresh.99ranch.com |
| `target` | Target | target.com |
| `walmart` | Walmart | walmart.com |

Use only each store's own official site, for prices and anything else. Never use Instacart,
DoorDash, Uber Eats, Postmates, warehouserunner.com or any other third-party aggregator or
price tracker. Restrict WebSearch to the store's own domains (`allowed_domains`).

Prefer the price on the item's own product page. Several stores often block automated visits
(Walmart's bot check, ShopRite's 403, Costco's sign-in, 99 Ranch errors). When the product page
can't be read, you may use the price the store's own site shows for that exact item in its
search results or category listings (a WebSearch result on the store's domain counts), and
record it with `--unverified` so the dashboard marks it. If several such results disagree, use
the regular (non-sale) price that matches the item's size; if you still can't tell which price
is right, skip the item. If nothing on the official site shows a price, skip that store.

## 1. Make the product's names and compare unit complete

Run `python3 -m pricewatch compare <product_id>` to see the product. Then make sure it has:

- an English name in normal title case (`bacon` → `Bacon`, `half and half` → `Half and Half`);
  if it was added under a Chinese name only, give it the common English name
- a Chinese name, the one used in Chinese grocery stores in the US (`Bacon` → `培根`)
- a compare unit that makes different pack sizes comparable: `lb` for produce, meat and most
  things sold by weight, `fl oz` for milk, cream and other liquids, `dozen` for eggs, `ct` or
  `each` for things sold by count
- a category for the dashboard, in the order the dashboard groups them: `meat` (meat and poultry,
  e.g. bacon, chicken, beef, pork), `seafood` (fish, shrimp, shellfish — including frozen ones),
  `vegetable` (vegetables, including tomatoes and mushrooms), `fruit` (fruit, including bananas),
  `dairy` (milk, cheese, eggs, cream, yogurt, butter), `pantry` (shelf-stable dry goods: rice,
  pasta, sauces, oil, spices, canned goods), or `other` (anything that doesn't fit the above:
  bakery, snacks, beverages, household)

Fix whatever is missing or wrong in one command, e.g.

```bash
python3 -m pricewatch set 9 --name Bacon --zh 培根 --unit lb --category meat
```

A product with no prices yet may show the placeholder unit `unit`; always replace it.

## 2. Record prices

For each store, find the product on the official site and record each item (brand/size) with

```bash
python3 -m pricewatch record <product_id> <store_code> <pack_price> --qty <units_in_pack> \
  --variant "<brand and size, e.g. Eggland's Best Large White 12ct>" --note "<site>官网, <M/D>查价"
```

Add `--unverified` when the price came from search results instead of the product page.

- `--qty` is the number of compare units in the pack, so unit prices are comparable:
  a 12 oz pack of bacon compared per `lb` is `--qty 0.75`; eggs are compared per `dozen`, so a
  12ct carton is `--qty 1`, an 18ct is `--qty 1.5` and a 24ct is `--qty 2`;
  a 32 fl oz carton per `fl oz` is `--qty 32`; a product sold per lb is `--qty 1`.
- `--note` uses today's date as month/day, e.g. `target.com官网, 11/6查价`.
- Match how broad the product name is, and never narrow it or rename the product to one type.
  - **A specific name** (`Rigatoni`, `Jasmine Rice`, `Boneless Skinless Chicken Thighs`) means
    only that type. Record 1–3 items per store: the store's own brand or most common item first,
    then another common brand if there is one.
  - **A general name** (`Pasta`, `Pasta Sauce`, `Rice`, `Cheese`, `Fish`, `Chicken Legs` / `鸡腿`)
    means every common type of it is acceptable. Record more items per store, up to about 6,
    covering the common types the store carries rather than picking one: e.g. for pasta,
    spaghetti, penne, rigatoni, fusilli; for pasta sauce, marinara, tomato basil, alfredo, vodka,
    pesto; for chicken legs, drumsticks, leg quarters and thighs, both bone-in and boneless,
    skin-on and skinless where sold.
  - A name is general in every detail it leaves out. `Chicken Thigh` fixes the cut but not the
    rest, so record bone-in and boneless, skin-on and skinless thighs; only
    `Boneless Skinless Chicken Thighs` limits it to that one form.
- `--variant` must say exactly what the item is, with every detail that tells it apart from the
  other items of the product: brand, type, size, and for meat the cut and whether it is bone-in
  or boneless and skin-on or skinless, e.g. `Perdue Bone-In Skin-On Chicken Drumsticks 3lb`,
  `Barilla Penne 16oz`, `Rao's Marinara 24oz`.
- Use the `--variant` text of an existing item exactly when re-pricing it, so its history
  continues instead of starting a new item.

Product selection rules:

- Never frozen meat (chicken, beef, pork, etc.); always fresh or refrigerated.
- Seafood (fish, shrimp, etc.) may be frozen; frozen seafood is a normal choice.
- Never organic unless it is the only option on the store's official site; then say so in the note.
- Standard, common varieties; not one-off deep sale prices or unusually premium items.
- Bananas: always the regular, non-organic variety.

Do not add new products; only work on the product(s) you were asked about.

## 3. Finish

Print a short summary: the product's names and unit, then each store with the item and price
recorded, or why it was skipped. Do not commit or push anything.
