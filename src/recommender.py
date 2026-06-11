"""
Wardrobe AI — Smart Day Recommender
Reads wear history + day logs to recommend what to wear TODAY.

Day log schema (wardrobe_data/days/YYYY-MM-DD.json):
{
  "date": "2026-06-11",
  "day_type": "college",        # college | outing | trek | holiday
  "slots": [
    {
      "slot": "casual",         # casual | home | around_home
      "pairing_id": "...",
      "dirt_level": "light",    # clean | light | dirty
      "notes": ""
    },
    ...
  ]
}
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE = Path("/mnt/soham/soham_code/Wardrobe AI/wardrobe_data")
ITEMS_DIR = BASE / "items"
PAIRINGS_DIR = BASE / "pairings"
DAYS_DIR = BASE / "days"

DAYS_DIR.mkdir(exist_ok=True)

# Slots needed per day_type
DAY_TYPE_SLOTS = {
    "college": ["casual", "home", "around_home"],
    "outing": ["casual", "home", "around_home"],
    "trek": ["casual", "home", "around_home"],  # casual = outdoorsy score
    "holiday": ["home", "around_home"],
}

# Map slot → destination score key used in pairing scores
SLOT_TO_DEST = {
    "casual": "Casual",
    "home": "Home",
    "around_home": "around home",
}

# Minimum score to consider a pairing for a slot
MIN_SCORE: Dict[str, int] = {
    "casual": 6,
    "home": 6,
    "around_home": 6,
}

# ── Day log I/O ────────────────────────────────────────────────────────────────


def load_day_log(date_str: str) -> Optional[Dict]:
    p = DAYS_DIR / f"{date_str}.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return None
    return None


def save_day_log(log: Dict) -> bool:
    p = DAYS_DIR / f"{log['date']}.json"
    try:
        p.write_text(json.dumps(log, indent=2))
        return True
    except Exception:
        return False


def load_recent_day_logs(days: int = 30) -> List[Dict]:
    """Load up to `days` most recent day logs."""
    logs = []
    today = datetime.today()
    for i in range(days):
        d = today - timedelta(days=i)
        log = load_day_log(d.strftime("%Y-%m-%d"))
        if log:
            logs.append(log)
    return logs


# ── Core recommender ───────────────────────────────────────────────────────────


def _load_items() -> Dict[str, Dict]:
    items = {}
    for f in ITEMS_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text())
            items[d["id"]] = d
        except Exception:
            pass
    return items


def _load_pairings() -> Dict[str, Dict]:
    pairings = {}
    for f in PAIRINGS_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text())
            pairings[d["id"]] = d
        except Exception:
            pass
    return pairings


def _pairing_item_ids(pairing: Dict) -> List[str]:
    ids = []
    u = pairing.get("upper_half", {}) or {}
    for key in ["topest_layer", "bottom_layer"]:
        v = u.get(key)
        if v:
            ids.append(v)
    for key in ["upper_layer", "medium_layer"]:
        v = u.get(key)
        if v:
            ids.append(v["id"] if isinstance(v, dict) else v)
    bh = pairing.get("bottom_half")
    if bh:
        ids.append(bh)
    fw = pairing.get("footwear")
    if fw:
        ids.append(fw)
    return ids


def _days_since_pairing_last_worn(pairing_id: str, recent_logs: List[Dict], today_str: Optional[str] = None) -> int:
    """Returns how many calendar days ago this pairing was last worn (9999 if never)."""
    if today_str is None:
        today_str = datetime.today().strftime("%Y-%m-%d")
    try:
        today_dt = datetime.strptime(today_str, "%Y-%m-%d")
        for log in recent_logs:
            log_date_str = log.get("date")
            if not log_date_str:
                continue
            log_dt = datetime.strptime(log_date_str, "%Y-%m-%d")
            diff = (today_dt - log_dt).days
            for slot in log.get("slots", []):
                if slot.get("pairing_id") == pairing_id:
                    return max(0, diff)
    except Exception:
        for i, log in enumerate(recent_logs):
            for slot in log.get("slots", []):
                if slot.get("pairing_id") == pairing_id:
                    return i
    return 9999


def _item_current_dirt(item_id: str, items: Dict) -> float:
    """
    Returns projected dirt ratio for an item (0.0=clean, 1.0=at limit, >1.0=over).
    Uses actual wear_count from item JSON (the source of truth).
    """
    item = items.get(item_id)
    if not item:
        return 0.0
    limit = max(item.get("laundry_limit", 3), 1)
    count = item.get("wear_count", 0)
    return count / limit


def _pairing_is_wearable(pairing: Dict, items: Dict) -> Tuple[bool, str]:
    """
    Check if all items in a pairing are clean enough to wear.
    Returns (wearable, reason).
    """
    for item_id in _pairing_item_ids(pairing):
        item = items.get(item_id)
        if not item:
            return False, f"item {item_id} not found"
        status = item.get("status", "Clean")
        if status == "Dirty":
            return False, f"{item_id} is Dirty"
        if status == "Washing":
            return False, f"{item_id} is Washing"
    return True, "ok"


def _no_layer_violation(pairing: Dict, slot: str) -> bool:
    """
    For home/around_home/sleep slots: no layering allowed.
    Returns True if it's clean (no violation).
    """
    if slot not in ("home", "around_home"):
        return True  # casual can layer
    u = pairing.get("upper_half", {}) or {}
    if u.get("topest_layer"):
        return False
    if u.get("upper_layer"):
        return False
    if u.get("bottom_layer"):
        return False
    return True


def _score_pairing_for_slot(
    pairing: Dict,
    slot: str,
    items: Dict,
    recent_logs: List[Dict],
    today_str: str,
    day_type: str = "college",
) -> Optional[float]:
    """
    Score a pairing for a given slot. Returns None if ineligible.
    Higher = better recommendation.
    """
    dest = SLOT_TO_DEST[slot]
    dest_score = pairing.get("scores", {}).get(dest, 0)
    if dest_score < MIN_SCORE[slot]:
        return None

    # Wearability
    wearable, _ = _pairing_is_wearable(pairing, items)
    if not wearable:
        return None

    # No-layer rule for home/around_home
    if not _no_layer_violation(pairing, slot):
        return None

    # Recency penalty: recently worn = lower score
    days_ago = _days_since_pairing_last_worn(pairing["id"], recent_logs, today_str)
    if days_ago == 0:
        return None  # worn today already
    recency_bonus = min(3.0, days_ago * 0.25)  # up to +3 for not wearing in 12 days

    # Dirt penalty: items that are getting close to their limit
    max_dirt = 0.0
    for item_id in _pairing_item_ids(pairing):
        dirt = _item_current_dirt(item_id, items)
        max_dirt = max(max_dirt, dirt)

    if max_dirt >= 1.0:
        return None  # over limit
    dirt_penalty = max_dirt * 2.0  # 0.0 to ~2.0 penalty

    # Aging factor penalty
    aging_sum = sum(
        items[iid].get("aging_factor", 1.0)
        for iid in _pairing_item_ids(pairing)
        if iid in items
    )
    aging_penalty = (aging_sum / max(1, len(_pairing_item_ids(pairing))) - 1.0) * 1.5

    # Item-level recency and laundry cycle biases
    item_laundry_recency_bonus = 0.0
    item_unworn_bonus = 0.0

    try:
        today_date = datetime.strptime(today_str, "%Y-%m-%d")
        for item_id in _pairing_item_ids(pairing):
            item = items.get(item_id)
            if not item:
                continue

            count = item.get("wear_count", 0)
            limit = max(item.get("laundry_limit", 3), 1)
            last_worn_str = item.get("last_worn")

            if last_worn_str:
                try:
                    lw_date = datetime.strptime(last_worn_str, "%Y-%m-%d")
                    days_since_worn = (today_date - lw_date).days

                    # 1. Finish-the-cycle bias: push partially worn items sitting unworn > 2 days
                    if 0 < count < limit:
                        if days_since_worn > 2:
                            item_laundry_recency_bonus += min(
                                5.0, (days_since_worn - 2) * 1.0
                            )

                    # 2. Unworn item bias: push clean items ignored > 7 days
                    elif count == 0:
                        if days_since_worn > 7:
                            item_unworn_bonus += min(3.0, (days_since_worn - 7) * 0.25)
                except Exception:
                    pass
            else:
                # Never worn before
                purchased_str = item.get("purchase_date")
                if purchased_str:
                    try:
                        p_date = datetime.strptime(purchased_str, "%Y-%m-%d")
                        days_since_purchase = (today_date - p_date).days
                        if days_since_purchase > 5:
                            item_unworn_bonus += min(3.5, days_since_purchase * 0.15)
                        else:
                            item_unworn_bonus += 1.5
                    except Exception:
                        item_unworn_bonus += 2.0
                else:
                    item_unworn_bonus += 2.0
    except Exception:
        pass

    final = (
        dest_score
        + recency_bonus
        - dirt_penalty
        - aging_penalty
        + item_laundry_recency_bonus
        + item_unworn_bonus
    )

    # Day-type specific adjustments for the casual slot
    if slot == "casual":
        p_items = [items[iid] for iid in _pairing_item_ids(pairing) if iid in items]
        categories = [it.get("category", "") for it in p_items]
        conditions = [it.get("condition", "Good") for it in p_items]
        comforts = [it.get("comfort", "Medium") for it in p_items]
        fabrics = [it.get("fabric", "").lower() for it in p_items]

        if day_type == "college":
            # College needs comfort and student-casual outfits
            comfort_bonus = sum(
                0.75 if c == "High" else 0.25 if c == "Medium" else -0.75
                for c in comforts
            )
            college_cats = {
                "T-Shirt",
                "Polo",
                "Hoodie",
                "Sweater",
                "Button-down",
                "Jeans",
                "Chinos",
                "Cargo Pants",
                "Sneakers",
            }
            cat_match = sum(0.5 for cat in categories if cat in college_cats)
            formal_penalty = sum(
                -1.5 if cat in {"Blazer", "Dress Shirt", "Formal Shoes"} else 0
                for cat in categories
            )
            final += comfort_bonus + cat_match + formal_penalty

        elif day_type == "outing":
            # Outing needs style and good condition
            cond_bonus = sum(
                0.75 if cond == "New" else 0.5 if cond == "Good" else -1.0
                for cond in conditions
            )
            u = pairing.get("upper_half", {}) or {}
            layer_bonus = 0.5 if (u.get("topest_layer") or u.get("upper_layer")) else 0
            style_cats = {
                "Button-down",
                "Jacket",
                "Blazer",
                "Chinos",
                "Trousers",
                "Loafers",
                "Boots",
            }
            cat_match = sum(0.5 for cat in categories if cat in style_cats)
            loungewear_penalty = sum(
                -1.5
                if cat in {"Sweatpants", "Night Pants", "Socks"} or "track" in fabric
                else 0
                for cat, fabric in zip(categories, fabrics)
            )
            final += cond_bonus + layer_bonus + cat_match + loungewear_penalty

        elif day_type == "trek":
            # Trek needs ruggedness and outdoor suitability
            trek_cats = {
                "Cargo Pants",
                "Jeans",
                "T-Shirt",
                "Hoodie",
                "Jacket",
                "Sneakers",
                "Boots",
            }
            cat_match = sum(1.0 for cat in categories if cat in trek_cats)
            cargo_boost = sum(1.5 if cat == "Cargo Pants" else 0 for cat in categories)
            delicate_penalty = sum(
                -1.5
                if cat
                in {"Blazer", "Trousers", "Formal Shoes", "Loafers", "Dress Shirt"}
                or "blend" in fabric
                else 0
                for cat, fabric in zip(categories, fabrics)
            )
            new_penalty = sum(-1.5 if cond == "New" else 0 for cond in conditions)
            final += cat_match + cargo_boost + delicate_penalty + new_penalty

    return round(final, 3)


def recommend_today(day_type: str, date_str: Optional[str] = None) -> Dict:
    """
    Main recommendation function. Returns:
    {
      "date": "...",
      "day_type": "college",
      "slots": {
        "casual": [ranked list of outfit dicts],
        "home": [...],
        "around_home": [...]
      }
    }
    """
    if date_str is None:
        date_str = datetime.today().strftime("%Y-%m-%d")

    items = _load_items()
    pairings = _load_pairings()
    recent_logs = load_recent_day_logs(30)

    # Find currently logged pairings for today
    day_log = load_day_log(date_str)
    logged_pids = {}
    if day_log:
        for slot_entry in day_log.get("slots", []):
            logged_pids[slot_entry["slot"]] = slot_entry

    slots_needed = DAY_TYPE_SLOTS.get(day_type, ["home", "around_home"])
    result_slots = {}

    for slot in slots_needed:
        candidates = []
        logged_entry = logged_pids.get(slot)
        logged_pid = logged_entry.get("pairing_id") if logged_entry else None

        for pairing in pairings.values():
            is_logged_this_slot = pairing["id"] == logged_pid
            score = _score_pairing_for_slot(
                pairing, slot, items, recent_logs, date_str, day_type
            )

            # If it's the logged outfit, we must show it even if items became dirty
            if score is None and not is_logged_this_slot:
                continue

            if is_logged_this_slot:
                score = score or pairing.get("scores", {}).get(SLOT_TO_DEST[slot], 0.0)

            # Resolve full item data for response
            u = pairing.get("upper_half", {}) or {}

            def resolve(layer_data):
                if not layer_data:
                    return None
                if isinstance(layer_data, str):
                    item = items.get(layer_data)
                    return {**item, "layer_id": layer_data} if item else None
                if isinstance(layer_data, dict):
                    item = items.get(layer_data["id"])
                    if not item:
                        return None
                    return {
                        **item,
                        "tuck": layer_data.get("tuck"),
                        "sleeves": layer_data.get("sleeves"),
                    }
                return None

            # Build pairing dirt summary
            item_ids = _pairing_item_ids(pairing)
            dirt_info = {}
            for iid in item_ids:
                item = items.get(iid)
                if item:
                    limit = max(item.get("laundry_limit", 3), 1)
                    count = item.get("wear_count", 0)
                    dirt_info[iid] = {
                        "wear_count": count,
                        "laundry_limit": limit,
                        "dirt_ratio": round(count / limit, 2),
                        "status": item.get("status", "Clean"),
                    }

            candidate = {
                "pairing_id": pairing["id"],
                "score": score,
                "dest_score": pairing.get("scores", {}).get(SLOT_TO_DEST[slot], 0),
                "scores": pairing.get("scores", {}),
                "last_worn": pairing.get("last_worn"),
                "days_since_worn": _days_since_pairing_last_worn(
                    pairing["id"], recent_logs, date_str
                ),
                "topest_layer": resolve(u.get("topest_layer")),
                "upper_layer": resolve(u.get("upper_layer")),
                "medium_layer": resolve(u.get("medium_layer")),
                "bottom_layer": resolve(u.get("bottom_layer")),
                "bottom_half": resolve(pairing.get("bottom_half")),
                "footwear": resolve(pairing.get("footwear")),
                "item_ids": item_ids,
                "dirt_summary": dirt_info,
            }

            if is_logged_this_slot:
                candidate["logged"] = True
                candidate["dirt_level"] = logged_entry.get("dirt_level", "light")
                candidate["notes"] = logged_entry.get("notes", "")

            candidates.append(candidate)

        # Sort candidates - logged one is always first, then by score descending
        candidates.sort(
            key=lambda x: (x.get("logged", False), x["score"]), reverse=True
        )
        result_slots[slot] = candidates[:10]  # top 10 per slot

    return {
        "date": date_str,
        "day_type": day_type,
        "slots": result_slots,
    }


def log_day_wear(
    date_str: str,
    day_type: str,
    slot: str,
    pairing_id: str,
    dirt_level: str,
    notes: str = "",
) -> Dict:
    """
    Log a worn pairing for a slot on a given day.
    Updates the day log file.
    """
    log = load_day_log(date_str) or {
        "date": date_str,
        "day_type": day_type,
        "slots": [],
    }
    if day_type:
        log["day_type"] = day_type

    log["slots"] = [s for s in log["slots"] if s.get("slot") != slot]

    log["slots"].append(
        {
            "slot": slot,
            "pairing_id": pairing_id,
            "dirt_level": dirt_level,
            "notes": notes,
            "logged_at": datetime.now().isoformat(),
        }
    )
    save_day_log(log)
    return log


def revert_slot_wear(date_str: str, slot: str):
    """
    Reverts wear counts and status of items when an outfit is unlogged or changed.
    """
    import storage

    log = load_day_log(date_str)
    if not log:
        return

    slot_entry = None
    for s in log.get("slots", []):
        if s.get("slot") == slot:
            slot_entry = s
            break

    if not slot_entry:
        return

    pairing_id = slot_entry.get("pairing_id")
    pairing = storage.load_pairing(pairing_id)
    if not pairing:
        return

    # Remove entry from pairing wear history
    if "wear_history" in pairing:
        pairing["wear_history"] = [
            w
            for w in pairing["wear_history"]
            if not (w.get("date") == date_str and w.get("slot") == slot)
        ]
        if pairing["wear_history"]:
            pairing["last_worn"] = pairing["wear_history"][-1]["date"]
        else:
            pairing["last_worn"] = None
        storage.save_pairing(pairing)

    # Revert item stats
    item_ids = _pairing_item_ids(pairing)
    for item_id in item_ids:
        item = storage.load_item(item_id)
        if not item:
            continue

        history = item.get("wear_history", [])
        matching_entries = [
            w for w in history if w.get("date") == date_str and w.get("slot") == slot
        ]
        if not matching_entries:
            continue

        # Remove matching entries
        history = [
            w
            for w in history
            if not (w.get("date") == date_str and w.get("slot") == slot)
        ]
        item["wear_history"] = history
        item["wear_count"] = max(0, item.get("wear_count", 0) - len(matching_entries))

        if history:
            item["last_worn"] = history[-1]["date"]
        else:
            item["last_worn"] = None

        limit = max(item.get("laundry_limit", 3), 1)
        has_dirty_wear = any(w.get("dirt_level") == "dirty" for w in history)
        if item["wear_count"] >= limit or has_dirty_wear:
            item["status"] = "Dirty"
        else:
            item["status"] = "Clean"

        storage.save_item(item)


def get_day_history(days: int = 14) -> List[Dict]:
    """Return recent day logs with resolved pairing data."""
    items = _load_items()
    pairings = _load_pairings()
    logs = load_recent_day_logs(days)

    enriched = []
    for log in logs:
        enriched_log = dict(log)
        enriched_slots = []
        for slot_entry in log.get("slots", []):
            pid = slot_entry.get("pairing_id")
            pairing = pairings.get(pid, {})
            enriched_slots.append(
                {
                    **slot_entry,
                    "pairing_name": _pairing_display_name(pairing, items),
                }
            )
        enriched_log["slots"] = enriched_slots
        enriched.append(enriched_log)
    return enriched


def _pairing_display_name(pairing: Dict, items: Dict) -> str:
    """Generate a short human-readable name for a pairing."""
    parts = []
    u = pairing.get("upper_half", {}) or {}
    for key in ["topest_layer", "upper_layer", "medium_layer"]:
        v = u.get(key)
        if v:
            iid = v["id"] if isinstance(v, dict) else v
            item = items.get(iid)
            if item:
                parts.append(item.get("name", iid))
                break
    bh = pairing.get("bottom_half")
    if bh:
        item = items.get(bh)
        if item:
            parts.append(item.get("name", bh))
    return " + ".join(parts) if parts else pairing.get("id", "?")


def score_custom_pairing(
    upper_half: Dict[str, Any],
    bottom_half: str,
    footwear: Optional[str],
    items: Dict[str, Any],
) -> Dict[str, int]:
    """
    Scores a custom pairing for the 5 destinations: Casual, Sleep, Home, around home, Full formal.
    Reflects the architectural guidelines of fit, comfort, layering, and condition.
    """
    # 1. Category checks
    bh_item = items.get(bottom_half)
    if not bh_item:
        return {"Casual": 1, "Sleep": 1, "Home": 1, "around home": 1, "Full formal": 1}

    # Get active item IDs
    item_ids = []
    u = upper_half or {}
    tl = u.get("topest_layer")
    if tl:
        item_ids.append(tl)
    ul = u.get("upper_layer")
    if ul:
        item_ids.append(ul["id"] if isinstance(ul, dict) else ul)
    ml = u.get("medium_layer")
    if ml:
        item_ids.append(ml["id"] if isinstance(ml, dict) else ml)
    bl = u.get("bottom_layer")
    if bl:
        item_ids.append(bl)
    item_ids.append(bottom_half)
    if footwear:
        item_ids.append(footwear)

    # All items must exist
    for iid in item_ids:
        if iid not in items:
            return {
                "Casual": 1,
                "Sleep": 1,
                "Home": 1,
                "around home": 1,
                "Full formal": 1,
            }

    # Category checks: Must have at least one upper half garment
    if not (tl or ul or ml or bl):
        return {"Casual": 1, "Sleep": 1, "Home": 1, "around home": 1, "Full formal": 1}

    # Initialize base scores
    scores = {"Casual": 6, "Sleep": 2, "Home": 5, "around home": 5, "Full formal": 2}

    bh_cat = bh_item.get("category", "")
    bh_cond = bh_item.get("condition", "Good")
    bh_comfort = bh_item.get("comfort", "Medium")

    # Top item (primary upper garment)
    top_item = None
    if ml:
        top_item = items.get(ml["id"] if isinstance(ml, dict) else ml)
    elif ul:
        top_item = items.get(ul["id"] if isinstance(ul, dict) else ul)
    elif tl:
        top_item = items.get(tl)
    elif bl:
        top_item = items.get(bl)

    top_cat = top_item.get("category", "") if top_item else ""
    top_cond = top_item.get("condition", "Good") if top_item else ""
    top_comfort = top_item.get("comfort", "Medium") if top_item else ""

    fw_item = items.get(footwear) if footwear else None
    fw_cat = fw_item.get("category", "") if fw_item else ""

    # --- Sleep Heuristics ---
    if bh_cat in ["Night Pants", "Sweatpants", "Shorts"] and top_cat in [
        "T-Shirt",
        "Tank Top",
        "Hoodie",
        "Shirt",
    ]:
        if bh_comfort == "High" and top_comfort == "High":
            scores["Sleep"] = 9
        elif bh_comfort in ["High", "Medium"] and top_comfort in ["High", "Medium"]:
            scores["Sleep"] = 8
        else:
            scores["Sleep"] = 6
    else:
        scores["Sleep"] = 1

    # --- Home Heuristics ---
    # No layering for Home
    if tl or ul or bl:
        scores["Home"] = 1
        scores["around home"] = 1
    else:
        # Comfort-based
        if bh_comfort == "High" and top_comfort == "High":
            scores["Home"] = 8
        elif bh_comfort in ["High", "Medium"] and top_comfort in ["High", "Medium"]:
            scores["Home"] = 7
        else:
            scores["Home"] = 5

        # Night pants / Track pants are great for Home
        if bh_cat in ["Night Pants", "Sweatpants", "Shorts"]:
            scores["Home"] += 1

        # Formal items are bad for Home
        if bh_cat in ["Trousers"] or top_cat in ["Dress Shirt", "Blazer"]:
            scores["Home"] -= 3

        scores["Home"] = max(1, min(10, scores["Home"]))

    # --- Around Home Heuristics ---
    if not (tl or ul or bl):
        # Decent look required, but comfortable
        scores["around home"] = scores["Home"]
        if bh_cat in ["Chinos", "Jeans", "Cargo Pants"]:
            scores["around home"] = max(scores["around home"], 7)
        if any(items[iid].get("condition") == "Aged" for iid in item_ids):
            scores["around home"] = min(scores["around home"], 3)
    else:
        scores["around home"] = 1

    # --- Full formal Heuristics ---
    if bh_cat in ["Trousers", "Chinos"] and top_cat in [
        "Dress Shirt",
        "Button-down",
        "Blazer",
    ]:
        scores["Full formal"] = 7
        if top_cat == "Blazer":
            scores["Full formal"] += 1
        if fw_cat in ["Formal Shoes", "Loafers"]:
            scores["Full formal"] += 1
        if ml and isinstance(ml, dict) and ml.get("tuck") == "fully tucked":
            scores["Full formal"] += 1
    else:
        scores["Full formal"] = 1

    # --- Casual Heuristics ---
    if bh_cat in ["Jeans", "Chinos", "Cargo Pants", "Shorts"] and top_cat in [
        "T-Shirt",
        "Button-down",
        "Polo",
        "Sweater",
        "Hoodie",
        "Jacket",
        "Blazer",
        "Coat",
    ]:
        scores["Casual"] = 8
        if fw_cat in ["Sneakers", "Boots", "Sandals", "Loafers"]:
            scores["Casual"] += 1
    elif bh_cat in ["Trousers"] and top_cat in [
        "Button-down",
        "Polo",
        "Blazer",
        "Jacket",
    ]:
        scores["Casual"] = 7
    else:
        scores["Casual"] = 4

    # Condition rules
    has_aged = any(items[iid].get("condition") == "Aged" for iid in item_ids)
    has_new = any(items[iid].get("condition") == "New" for iid in item_ids)
    has_worn = any(items[iid].get("condition") == "Worn" for iid in item_ids)

    if has_aged:
        scores["Casual"] = min(scores["Casual"], 2)
        scores["Full formal"] = min(scores["Full formal"], 1)
        scores["around home"] = min(scores["around home"], 4)
    if has_new:
        scores["Sleep"] = min(scores["Sleep"], 2)
        scores["Home"] = min(scores["Home"], 2)
    if has_worn:
        scores["Casual"] = min(scores["Casual"], 5)
        scores["Full formal"] = min(scores["Full formal"], 3)

    # Special layering rules
    if "item_tshirt_black_cotton" in item_ids:
        # Must be bottom layer under open upper layer (jacket/coat or open button-down)
        is_bottom_layer = u.get("bottom_layer") == "item_tshirt_black_cotton"
        has_outer = tl is not None or ul is not None
        if not (is_bottom_layer and has_outer):
            for k in scores:
                scores[k] = 1

    if "item_tshirt_pista_thick" in item_ids:
        is_layered = u.get("bottom_layer") == "item_tshirt_pista_thick" or (
            ml
            and isinstance(ml, dict)
            and ml.get("id") == "item_tshirt_pista_thick"
            and (tl or ul)
        )
        if not is_layered:
            scores["Casual"] = min(scores["Casual"], 4)

    for k in scores:
        scores[k] = max(1, min(10, scores[k]))

    return scores


def score_and_save_custom_pairing(pairing_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Saves a custom pairing, updates referenced items, and registers in-memory caches.
    """
    import time

    import storage

    pid = f"pairing_custom_{int(time.time())}"
    pairing_data["id"] = pid

    items = _load_items()
    scores = score_custom_pairing(
        pairing_data.get("upper_half"),
        pairing_data.get("bottom_half"),
        pairing_data.get("footwear"),
        items,
    )
    pairing_data["scores"] = scores

    storage.save_pairing(pairing_data)

    item_ids = _pairing_item_ids(pairing_data)
    for iid in item_ids:
        item = storage.load_item(iid)
        if item:
            pids = item.get("pairing_ids", [])
            if pid not in pids:
                pids.append(pid)
                item["pairing_ids"] = pids
                storage.save_item(item)

    # force cache reload to align recommender with storage cache
    storage.force_reload()
    return pairing_data
