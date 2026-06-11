#!/usr/bin/env python3
"""
Wardrobe AI — Data Validator v2
Checks all items/ and pairings/ for:
  - Schema completeness
  - Cross-reference integrity
  - Image file existence
  - Status / wear_count / laundry_limit coherence
  - Pairing layer logic (at least one upper + one lower)
  - No-layering rule for Home / Sleep / around_home pairings
  - comfort field validity
  - aging_factor field range
"""

import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).parent / "wardrobe_data"
ITEMS_DIR = BASE / "items"
PAIRINGS_DIR = BASE / "pairings"
IMAGES_DIR = BASE / "images"

VALID_CATEGORIES = {
    # Tops
    "T-Shirt",
    "Button-down",
    "Polo",
    "Sweater",
    "Hoodie",
    "Jacket",
    "Blazer",
    "Coat",
    "Tank Top",
    "Vest",
    "Dress Shirt",
    "Shirt",
    # Bottoms
    "Jeans",
    "Chinos",
    "Trousers",
    "Shorts",
    "Sweatpants",
    "Cargo Pants",
    "Pants",
    "Night Pants",
    # Footwear
    "Sneakers",
    "Formal Shoes",
    "Boots",
    "Sandals",
    "Loafers",
    # Other
    "Socks",
    "Belt",
    "Underwear",
    "Accessories",
}

VALID_STATUSES = {"Clean", "Dirty", "Washing"}
VALID_CONDITIONS = {"New", "Good", "Worn", "Aged"}
VALID_DESTS = {"Casual", "Sleep", "Home", "around home", "Full formal"}

ITEM_REQUIRED = [
    "id",
    "name",
    "category",
    "color_hex",
    "color_name",
    "fabric",
    "image_name",
    "condition",
    "status",
    "wear_count",
    "laundry_limit",
    "wear_history",
    "pairing_ids",
    "comfort",
    "aging_factor",
]

VALID_COMFORT = {"High", "Medium", "Low"}

# Destinations where layering is NOT allowed (only medium_layer allowed)
NO_LAYER_DEST_PREFIXES = ("home", "sleep", "aroundhome")

PAIRING_REQUIRED = ["id", "scores", "upper_half", "bottom_half"]
UPPER_HALF_KEYS = ["topest_layer", "upper_layer", "medium_layer", "bottom_layer"]

# ── Helpers ───────────────────────────────────────────────────────────────────

errors = []  # (file, message)
warnings = []  # (file, message)


def err(fname, msg):
    errors.append((fname, msg))


def warn(fname, msg):
    warnings.append((fname, msg))


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        err(path.name, f"JSON parse error: {e}")
        return None


# ── Load all data ─────────────────────────────────────────────────────────────

item_files = sorted(ITEMS_DIR.glob("*.json"))
pairing_files = sorted(PAIRINGS_DIR.glob("*.json"))

all_items = {}  # id → data
all_pairings = {}  # id → data

for f in item_files:
    d = load_json(f)
    if d:
        all_items[d.get("id", f.stem)] = (f.name, d)

for f in pairing_files:
    d = load_json(f)
    if d:
        all_pairings[d.get("id", f.stem)] = (f.name, d)

# ── Validate Items ────────────────────────────────────────────────────────────

print("\n" + "═" * 60)
print("  WARDROBE AI — VALIDATOR")
print("═" * 60)
print(f"\n📦 Items found:    {len(all_items)}")
print(f"🔗 Pairings found: {len(all_pairings)}\n")

for item_id, (fname, item) in all_items.items():
    tag = f"[item] {fname}"

    # Required fields
    for field in ITEM_REQUIRED:
        if field not in item:
            err(tag, f"Missing required field: '{field}'")

    # id matches filename
    if item.get("id") != fname.replace(".json", ""):
        warn(tag, f"id '{item.get('id')}' doesn't match filename '{fname}'")

    # Category
    if item.get("category") not in VALID_CATEGORIES:
        warn(tag, f"Unknown category: '{item.get('category')}' — not in allowed set")

    # Status
    if item.get("status") not in VALID_STATUSES:
        err(
            tag, f"Invalid status: '{item.get('status')}' — must be Clean/Dirty/Washing"
        )

    # Condition
    if item.get("condition") not in VALID_CONDITIONS:
        warn(tag, f"Unknown condition: '{item.get('condition')}'")

    # color_hex format
    hex_val = item.get("color_hex", "")
    if not (hex_val.startswith("#") and len(hex_val) in (4, 7)):
        warn(tag, f"Suspicious color_hex: '{hex_val}'")

    # wear_count vs laundry_limit coherence
    wear_count = item.get("wear_count", 0)
    laundry_limit = item.get("laundry_limit", 0)
    status = item.get("status", "")
    if wear_count > laundry_limit and status == "Clean":
        warn(
            tag,
            f"wear_count ({wear_count}) > laundry_limit ({laundry_limit}) but status is 'Clean'",
        )

    # Image existence
    img = item.get("image_name")
    if img and not (IMAGES_DIR / img).exists():
        err(tag, f"Image not found: '{img}'")

    # pairing_ids cross-reference
    for pid in item.get("pairing_ids", []):
        if pid not in all_pairings:
            err(tag, f"pairing_id '{pid}' not found in pairings/")

    # wear_history entries
    for i, entry in enumerate(item.get("wear_history", [])):
        if "date" not in entry:
            warn(tag, f"wear_history[{i}] missing 'date'")
        if "destination" not in entry:
            warn(tag, f"wear_history[{i}] missing 'destination'")

    # comfort field
    comfort = item.get("comfort")
    if not comfort:
        warn(tag, "Missing 'comfort' field (High/Medium/Low)")
    elif comfort not in VALID_COMFORT:
        warn(tag, f"Invalid comfort value '{comfort}' — must be High/Medium/Low")

    # aging_factor field
    af = item.get("aging_factor")
    if af is None:
        warn(tag, "Missing 'aging_factor' field")
    elif not isinstance(af, (int, float)) or not (0.1 <= af <= 5.0):
        warn(tag, f"aging_factor={af} out of expected range 0.1–5.0")

# ── Validate Pairings ─────────────────────────────────────────────────────────


def resolve_layer(val):
    """Return item id string from a layer value (str, dict, or None)."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("id")
    return None


for pair_id, (fname, pair) in all_pairings.items():
    tag = f"[pairing] {fname}"

    # Required fields
    for field in PAIRING_REQUIRED:
        if field not in pair:
            err(tag, f"Missing required field: '{field}'")

    # id matches filename
    if pair.get("id") != fname.replace(".json", ""):
        warn(tag, f"id '{pair.get('id')}' doesn't match filename '{fname}'")

    # Scores completeness
    scores = pair.get("scores", {})
    for dest in VALID_DESTS:
        if dest not in scores:
            warn(tag, f"scores missing destination: '{dest}'")
        elif not isinstance(scores[dest], (int, float)) or not (
            0 <= scores[dest] <= 10
        ):
            err(tag, f"scores['{dest}'] = {scores[dest]} — must be 0–10 numeric")

    # upper_half structure
    upper = pair.get("upper_half", {})
    upper_ids = []
    for key in UPPER_HALF_KEYS:
        val = upper.get(key)
        iid = resolve_layer(val)
        if iid:
            upper_ids.append(iid)
            if iid not in all_items:
                err(tag, f"upper_half.{key} references unknown item: '{iid}'")

    # At least one upper item
    if not upper_ids:
        err(tag, "No upper-half items defined — outfit has no top garment")

    # bottom_half
    bot = pair.get("bottom_half")
    if bot:
        if bot not in all_items:
            err(tag, f"bottom_half references unknown item: '{bot}'")
    else:
        err(tag, "bottom_half is null/missing — outfit has no lower garment")

    # footwear (optional, but if present must exist)
    fw = pair.get("footwear")
    if fw and fw not in all_items:
        err(tag, f"footwear references unknown item: '{fw}'")

    # Back-reference: does each referenced item list this pairing?
    referenced_ids = upper_ids + ([bot] if bot else []) + ([fw] if fw else [])
    for iid in referenced_ids:
        if iid in all_items:
            item_fname, item_data = all_items[iid]
            if pair_id not in item_data.get("pairing_ids", []):
                warn(tag, f"item '{iid}' doesn't list this pairing in its pairing_ids")

    # No-layering rule for Home / Sleep / around_home pairings
    pair_prefix = pair_id.lower().replace("pairing_", "").replace(" ", "")
    is_no_layer = any(pair_prefix.startswith(p) for p in ("home", "sleep", "aroundhome"))
    if is_no_layer:
        if upper.get("topest_layer"):
            err(tag, "Home/Sleep/AroundHome pairing must NOT have topest_layer (no layering)")
        if upper.get("upper_layer"):
            err(tag, "Home/Sleep/AroundHome pairing must NOT have upper_layer (no layering)")
        if upper.get("bottom_layer"):
            err(tag, "Home/Sleep/AroundHome pairing must NOT have bottom_layer (no layering)")

# ── Orphan check: items with no pairings ─────────────────────────────────────

for item_id, (fname, item) in all_items.items():
    if not item.get("pairing_ids"):
        warn(f"[item] {fname}", "No pairings — item never used in any outfit")

# ── Image orphans ─────────────────────────────────────────────────────────────

known_images = {
    d.get("image_name") for _, (_, d) in all_items.items() if d.get("image_name")
}
for img_file in IMAGES_DIR.iterdir():
    if img_file.name not in known_images:
        warn("[images]", f"Orphan image (no item references it): '{img_file.name}'")

# ── Report ────────────────────────────────────────────────────────────────────

print("─" * 60)
if errors:
    print(f"\n❌  ERRORS ({len(errors)}):\n")
    for f, m in errors:
        print(f"   ✗ {f}\n     → {m}\n")
else:
    print("\n✅  No errors found!\n")

if warnings:
    print(f"⚠️   WARNINGS ({len(warnings)}):\n")
    for f, m in warnings:
        print(f"   ⚠ {f}\n     → {m}\n")
else:
    print("✅  No warnings.\n")

print("─" * 60)
total_issues = len(errors) + len(warnings)
if total_issues == 0:
    print("\n🎉 All data valid. Wardrobe is clean.\n")
else:
    print(
        f"\n🔍 {len(errors)} error(s), {len(warnings)} warning(s) across {len(all_items)} items & {len(all_pairings)} pairings.\n"
    )

sys.exit(1 if errors else 0)
