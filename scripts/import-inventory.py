#!/usr/bin/env python3
"""Convert a Sortly-style inventory export (.xlsx) into field-guide JSON."""

from __future__ import annotations

import json
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("Termite", ["termite", "trelona", "bora care", "bore 8", "atbs", "premise foam"]),
    ("Rodent", ["rodent", "mouse", "rat", "final all weather", "protecta", "trapper", "victor", "tin cat", "multi catch", "glupac", "glue board", "glue trap"]),
    ("Ant baits", ["ant bait", "ant gel", "advance 375", "advance granular carpenter", "intice ant", "optiguard ant", "strike max", "sumari ant", "doxem plus fire ant", "maxforce fleet"]),
    ("Roach baits", ["roach", "alpine cockroach", "vendetta", "magnetic roach"]),
    ("Mosquito", ["mosquito", "b.t.i", "inzecto"]),
    ("Wasp / hornet", ["wasp", "hornet", "yellow jacket", "onslaught power shot", "stryker", "eco via wh"]),
    ("Bed bug / flea", ["bed", "flea", "cross fire", "bedlam", "steri-fab", "pt alpine flea"]),
    ("IGR", ["nyguard", "tekko", "igr"]),
    ("Traps & stations", ["station", "trap", "bait plate", "intice border", "bat valve"]),
]

SPRAY_KEYWORDS = [
    "dust", "wsg", "cs", "sc ", "sfr", "it", "l/p", "granular", "aerosol",
    "pressurized", "insecticide", "suspend", "demand", "dominion", "lambda",
    "bifen", "tempo", "fendona", "barricor", "duraflex", "essentria", "exciter",
    "conquer", "ridesco", "onslaught", "phantom", "shockwave", "tengard",
    "termidor", "taurus sc", "adjourn", "cyzmic", "d-fense", "doxem nxt",
    "pivot", "all purpose",
]


def col_to_idx(col: str) -> int:
    value = 0
    for char in col:
        value = value * 26 + (ord(char) - 64)
    return value - 1


def cell_ref_to_coords(ref: str) -> tuple[int, int]:
    col = "".join(char for char in ref if char.isalpha())
    row = "".join(char for char in ref if char.isdigit())
    return int(row) - 1, col_to_idx(col)


def parse_number(raw: str | None) -> float | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def categorize(name: str) -> str:
    lowered = name.lower()
    for category, keywords in CATEGORY_RULES:
        if any(keyword in lowered for keyword in keywords):
            return category
    if any(keyword in lowered for keyword in SPRAY_KEYWORDS):
        return "Sprays & concentrates"
    if any(keyword in lowered for keyword in ["fly", "maxforce"]):
        return "Fly control"
    if any(keyword in lowered for keyword in ["foam", "drain", "dsv", "ez sorb", "bio 5", "foam fresh"]):
        return "Sanitation & foam"
    if any(keyword in lowered for keyword in ["bulb", "plug", "super plug"]):
        return "Equipment & supplies"
    return "Other"


def read_xlsx(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        for item in shared_root.findall(".//m:si", NS):
            texts = [node.text or "" for node in item.findall(".//m:t", NS)]
            shared.append("".join(texts))

        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        rows: dict[int, dict[int, str]] = {}
        for row in sheet.findall(".//m:sheetData/m:row", NS):
            row_index = int(row.attrib["r"]) - 1
            rows[row_index] = {}
            for cell in row.findall("m:c", NS):
                ref = cell.attrib.get("r")
                if not ref:
                    continue
                _, column_index = cell_ref_to_coords(ref)
                value_node = cell.find("m:v", NS)
                if value_node is None:
                    continue
                value = value_node.text or ""
                if cell.attrib.get("t") == "s":
                    value = shared[int(value)]
                rows[row_index][column_index] = value

    max_column = max(max(row.keys()) for row in rows.values())
    headers = [rows[0].get(index, f"col{index}") for index in range(max_column + 1)]

    records: list[dict[str, str]] = []
    for row_index in sorted(rows.keys())[1:]:
        row = rows[row_index]
        if not row:
            continue
        record = {headers[index]: row.get(index, "") for index in range(max_column + 1)}
        if str(record.get("Entry Name", "")).strip():
            records.append(record)
    return records


def transform(records: list[dict[str, str]]) -> list[dict]:
    items = []
    for record in records:
        name = str(record.get("Entry Name", "")).strip()
        if not name:
            continue
        quantity = parse_number(record.get("Quantity"))
        price = parse_number(record.get("Price"))
        min_level = parse_number(record.get("Min Level"))
        items.append(
            {
                "id": str(record.get("SID", "")).strip(),
                "name": name,
                "category": categorize(name),
                "quantity": quantity,
                "unit": str(record.get("Unit", "")).strip(),
                "minLevel": min_level,
                "price": round(price, 2) if price is not None else None,
                "ordered": str(record.get("Ordered", "")).strip(),
                "notes": str(record.get("Notes", "")).strip(),
            }
        )
    return sorted(items, key=lambda item: item["name"].lower())


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/import-inventory.py <inventory-export.xlsx> [output.json]")
        return 1

    source = Path(sys.argv[1])
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/inventory.json")
    output.parent.mkdir(parents=True, exist_ok=True)

    items = transform(read_xlsx(source))
    output.write_text(json.dumps(items, indent=2), encoding="utf-8")
    print(f"Wrote {len(items)} products to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
