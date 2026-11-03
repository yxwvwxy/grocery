# Grocery Price Compare

Compare the price of the same product across ShopRite, H Mart, Costco, 99 Ranch, Target and Walmart. Prices are compared by **unit price** (per lb, per dozen eggs, per fl oz…), so different pack sizes compare directly. Prices are looked up by Claude on each store's official website.

Uses only the Python standard library, so there is nothing to install. Data is stored in `data/prices.db` (SQLite), which is tracked in git.

**Read-only copy:** https://claude.ai/artifact/HwPtu6CjfP1PjPv2wsx3Vz — the same comparison table, item lists and price history, viewable without running anything (no tracking or lookups). It is a snapshot: it is republished after each price check with `python3 -m pricewatch export`. Only people it has been shared with can open it.

## Web dashboard

```bash
python3 -m pricewatch serve
```

This opens http://127.0.0.1:8765 in your browser. The page is served by a server running on your own computer: the link only works while the command above is running. If you close that terminal (or press Ctrl+C), the link stops working; run the command again to bring it back.

What the dashboard does:

- **Comparison table**: one row per tracked product (English and Chinese name), one column per store, with the cheapest store highlighted. Products are grouped under Meat (including seafood), Vegetables and Other
- **Reorder**: drag a row by the ⠿ handle on its left; rows move within their own group and the order is saved
- **Click a product** to see every item (store × brand/size) ranked cheapest first, and a collapsible price history chart (each store's average unit price at each price check)
- **Track a new product**: type its name in English or Chinese and click Track. Claude then looks up that product on each store's official site in the background, filling in its English and Chinese names, the unit to compare by, and the prices. The row shows "Looking up prices…" and updates by itself when done
- **Look up prices now**: re-runs the lookup for one product
- **Stop tracking** (the crossed-out eye at the end of a row, or the button in a product's details): hides a product from the list but keeps its price history. Track the same name again to bring it back with its history
- **General vs specific names**: a general name (`Pasta`, `Chicken Legs`) gets several common types at each store, each labeled with its brand, type and size; a specific name (`Rigatoni`, `Boneless Skinless Chicken Thighs`) gets only that type

## How prices get updated

- **When you track a product**: a lookup for that one product, started from the dashboard.
- **Every Friday at 8:00 AM (Eastern)**: a scheduled task in the Claude desktop app refreshes every tracked product. It runs while the app is open; if the app is closed at that time, it runs the next time the app opens. Manage it under "Scheduled" in the app's sidebar.

Both follow the rules in [pricewatch/LOOKUP.md](pricewatch/LOOKUP.md): official store sites only, no frozen meat, no organic unless it is the only option, and so on.

The dashboard's lookup runs Claude Code on this Mac, which must be signed in once. In a terminal, run Claude Code's sign-in, then follow the browser prompt:

```bash
"$(ls -d ~/Library/Application\ Support/Claude/claude-code/*/*/claude.app/Contents/MacOS/claude | tail -1)" auth login
```

## Command line

```bash
python3 -m pricewatch add Eggs --zh "<Chinese name>" --unit dozen --target 3   # new product, compared per dozen
python3 -m pricewatch set 9 --name Bacon --zh "<Chinese name>" --unit lb        # change names or compare unit
python3 -m pricewatch record 1 costco 7.49 --qty 2 --variant "Kirkland Large 24ct"    # $7.49 for 2 dozen at Costco
python3 -m pricewatch compare                                                   # unit prices across stores
python3 -m pricewatch remove 1                                                  # delete a product and its history
python3 -m pricewatch refresh                                                   # look up every tracked product again with Claude
python3 -m pricewatch export                                                    # write the read-only copy to data/share.html
```

Store codes: `shoprite` `hmart` `costco` `ranch99` `target` `walmart`
