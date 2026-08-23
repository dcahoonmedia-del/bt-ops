# B&T Ops — Field Guide Tools

Internal tools for B&T Pest Control, starting with a **product inventory reference** for technicians.

## Product inventory reference

A mobile-friendly lookup page built from your Sortly (or similar) inventory export.

**What it shows today**

- 110 products from your current warehouse export
- Search by product name
- Filter by category (sprays, ant baits, termite, rodent, etc.)
- Stock status: in stock, low stock, out of stock
- Tap any product for quantity, price, SKU, and notes

**Open it locally**

```bash
cd /workspace
python3 -m http.server 8080
```

Then visit: [http://localhost:8080/inventory/](http://localhost:8080/inventory/)

## Update inventory after a new Sortly export

1. Export your inventory from Sortly as `.xlsx`
2. Run:

```bash
python3 scripts/import-inventory.py path/to/your-export.xlsx data/inventory.json
```

3. Refresh the inventory page — no other changes needed

## How this fits your field guide

Your live chemical rotation guide is at:

[https://bt-technician-field-guide.dcahoon10.chatgpt.site/](https://bt-technician-field-guide.dcahoon10.chatgpt.site/)

This repo is the long-term home for features that outgrow ChatGPT Sites — starting with inventory. Next steps could include:

- Hosting this on a custom URL (e.g. `guide.btpestcontrol.com/inventory`)
- Merging it into the main field guide as the **Products** tab
- Adding label/SDS links, MOA groups, and target pest tags per product

## Project structure

```
data/inventory.json          # product data (generated from Excel)
inventory/index.html         # inventory reference page
inventory/styles.css
inventory/app.js
scripts/import-inventory.py  # Excel → JSON converter
```
