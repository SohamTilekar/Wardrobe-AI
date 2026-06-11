import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import storage
import recommender

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("wardrobe_main")

app = FastAPI(title="Smart Wardrobe Assistant", version="7.0")

WORKSPACE_DIR = Path("/mnt/soham/soham_code/Wardrobe AI")
SRC_DIR = WORKSPACE_DIR / "src"
STATIC_DIR = SRC_DIR / "static"
TEMPLATES_DIR = SRC_DIR / "templates"
DATA_DIR = WORKSPACE_DIR / "wardrobe_data"
IMAGES_DIR = DATA_DIR / "images"

STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ── Pages ────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


# ── Items CRUD ───────────────────────────────────────────────

@app.get("/api/items")
async def get_items():
    items = storage.load_all_items()
    res = []
    for item in items.values():
        item_copy = dict(item)
        item_copy["friend_votes"] = storage.get_votes(item["id"])
        res.append(item_copy)
    return res

@app.get("/api/items/{item_id}")
async def get_item(item_id: str):
    item = storage.load_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item["friend_votes"] = storage.get_votes(item_id)
    return item

@app.put("/api/items/{item_id}")
async def update_item(item_id: str, item_update: Dict[str, Any]):
    existing = storage.load_item(item_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Item not found")
    existing.update(item_update)
    storage.save_item(existing)
    return existing

@app.delete("/api/items/{item_id}")
async def delete_item(item_id: str):
    if storage.delete_item(item_id):
        return {"success": True}
    raise HTTPException(status_code=500, detail="Failed to delete")


# ── Item wear / wash / vote ──────────────────────────────────

@app.post("/api/items/{item_id}/wear")
async def log_wear(item_id: str, payload: Dict[str, Any]):
    item = storage.load_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    date_str = payload.get("date", datetime.today().strftime("%Y-%m-%d"))
    dest      = payload.get("destination", "Casual")
    dirt_level = payload.get("dirt_level", "light")
    force_status = payload.get("force_status")

    item.setdefault("wear_history", []).append({
        "date": date_str, "destination": dest, "dirt_level": dirt_level
    })
    item["wear_count"] = item.get("wear_count", 0) + 1
    item["last_worn"]  = date_str

    if force_status:
        item["status"] = force_status
    elif dirt_level == "dirty":
        item["status"] = "Dirty"
    elif dirt_level == "clean":
        pass
    else:
        limit = item.get("laundry_limit", 3)
        if item["wear_count"] >= limit:
            item["status"] = "Dirty"

    storage.save_item(item)
    return item

@app.post("/api/items/{item_id}/wash")
async def log_wash(item_id: str, payload: Dict[str, Any]):
    item = storage.load_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    status = payload.get("status", "Clean")
    item["status"] = status
    if status == "Clean":
        item["wear_count"] = 0
    storage.save_item(item)
    return item

@app.post("/api/items/{item_id}/vote")
async def vote_item(item_id: str, payload: Dict[str, Any]):
    entry = {
        "friend": payload.get("friend", "Anonymous"),
        "vote":   payload.get("vote", "liked"),
        "note":   payload.get("note"),
        "date":   payload.get("date", datetime.today().strftime("%Y-%m-%d")),
    }
    storage.save_vote(item_id, entry)
    return {"success": True}


# ── Pairings CRUD ────────────────────────────────────────────

@app.get("/api/pairings")
async def get_pairings():
    return list(storage.load_all_pairings().values())

@app.get("/api/pairings/{pairing_id}")
async def get_pairing(pairing_id: str):
    p = storage.load_pairing(pairing_id)
    if not p:
        raise HTTPException(status_code=404, detail="Pairing not found")
    p["friend_votes"] = storage.get_votes(pairing_id)
    return p


# ── Pairing wear / wash / vote ───────────────────────────────

@app.post("/api/pairings/{pairing_id}/wear")
async def log_pairing_wear(pairing_id: str, payload: Dict[str, Any]):
    pairing = storage.load_pairing(pairing_id)
    if not pairing:
        raise HTTPException(status_code=404, detail="Pairing not found")

    date_str    = payload.get("date", datetime.today().strftime("%Y-%m-%d"))
    dest        = payload.get("destination", "Casual")
    dirt_level  = payload.get("dirt_level", "light")
    force_status = payload.get("force_status")

    item_ids = _pairing_item_ids(pairing)
    updated_items = []

    for item_id in item_ids:
        item = storage.load_item(item_id)
        if not item:
            continue
        item.setdefault("wear_history", []).append({
            "date": date_str, "destination": dest, "dirt_level": dirt_level
        })
        item["wear_count"] = item.get("wear_count", 0) + 1
        item["last_worn"]  = date_str

        if force_status:
            item["status"] = force_status
        elif dirt_level == "dirty":
            item["status"] = "Dirty"
        elif dirt_level == "clean":
            pass
        else:
            limit = item.get("laundry_limit", 3)
            if item["wear_count"] >= limit:
                item["status"] = "Dirty"

        storage.save_item(item)
        updated_items.append(item)

    pairing.setdefault("wear_history", []).append({"date": date_str, "destination": dest, "dirt_level": dirt_level})
    pairing["last_worn"] = date_str
    storage.save_pairing(pairing)

    return {"pairing_id": pairing_id, "items_updated": updated_items}

@app.post("/api/pairings/{pairing_id}/wash")
async def log_pairing_wash(pairing_id: str, payload: Dict[str, Any]):
    pairing = storage.load_pairing(pairing_id)
    if not pairing:
        raise HTTPException(status_code=404, detail="Pairing not found")

    status   = payload.get("status", "Clean")
    item_ids = _pairing_item_ids(pairing)
    updated  = []
    for item_id in item_ids:
        item = storage.load_item(item_id)
        if not item:
            continue
        item["status"] = status
        if status == "Clean":
            item["wear_count"] = 0
        storage.save_item(item)
        updated.append(item)

    return {"pairing_id": pairing_id, "items_updated": updated}

@app.post("/api/pairings/{pairing_id}/vote")
async def vote_pairing(pairing_id: str, payload: Dict[str, Any]):
    entry = {
        "friend":  payload.get("friend", "Anonymous"),
        "vote":    payload.get("vote", "liked"),
        "note":    payload.get("note"),
        "item_id": payload.get("item_id"),
        "date":    payload.get("date", datetime.today().strftime("%Y-%m-%d")),
    }
    storage.save_vote(pairing_id, entry)
    return {"success": True}


# ── Helpers ──────────────────────────────────────────────────

def _pairing_item_ids(pairing: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    u = pairing.get("upper_half", {}) or {}
    tl = u.get("topest_layer")
    if tl: ids.append(tl)
    ul = u.get("upper_layer")
    if ul: ids.append(ul["id"] if isinstance(ul, dict) else ul)
    ml = u.get("medium_layer")
    if ml: ids.append(ml["id"] if isinstance(ml, dict) else ml)
    bl = u.get("bottom_layer")
    if bl: ids.append(bl)
    bh = pairing.get("bottom_half")
    if bh: ids.append(bh)
    fw = pairing.get("footwear")
    if fw: ids.append(fw)
    return ids


# ── Outfit suggestions (Streaming) ───────────────────────────

@app.get("/api/outfits")
async def get_outfit_suggestions(destination: str = "Casual"):
    all_items = storage.load_all_items()
    pairings  = storage.load_all_pairings().values()
    clean_items = {k: v for k, v in all_items.items() if v.get("status") == "Clean"}

    def outfit_generator():
        outfits = []
        for p in pairings:
            p_items = _pairing_item_ids(p)
            if not p_items or not all(i in clean_items for i in p_items):
                continue

            scores     = p.get("scores", {})
            dest_score = scores.get(destination, 0)
            if dest_score < 4:
                continue

            u = p.get("upper_half", {}) or {}

            def resolve_layer(layer_data):
                if not layer_data: return None
                if isinstance(layer_data, str):
                    obj = clean_items.get(layer_data)
                    return {**obj, "layer_id": layer_data} if obj else None
                if isinstance(layer_data, dict):
                    obj = clean_items.get(layer_data["id"])
                    if not obj: return None
                    return {**obj, "tuck": layer_data.get("tuck"), "sleeves": layer_data.get("sleeves")}
                return None

            last_worn = p.get("last_worn")
            if last_worn:
                days_ago = (datetime.today() - datetime.strptime(last_worn, "%Y-%m-%d")).days
                recency_bonus = min(1.5, days_ago * 0.05)
            else:
                recency_bonus = 2.0

            final_score = round(dest_score + recency_bonus, 2)

            outfits.append({
                "pairing_id":  p.get("id"),
                "score":       final_score,
                "dest_score":  dest_score,
                "scores":      scores,
                "last_worn":   last_worn,
                "friend_votes": storage.get_votes(p.get("id")),
                "topest_layer": resolve_layer(u.get("topest_layer")),
                "upper_layer":  resolve_layer(u.get("upper_layer")),
                "medium_layer": resolve_layer(u.get("medium_layer")),
                "bottom_layer": resolve_layer(u.get("bottom_layer")),
                "bottom_half":  resolve_layer(p.get("bottom_half")),
                "footwear":     resolve_layer(p.get("footwear")),
                "item_ids":    p_items,
            })

        outfits.sort(key=lambda x: x["score"], reverse=True)
        # Yield as NDJSON
        for out in outfits[:20]:
            yield json.dumps(out) + "\n"

    return StreamingResponse(outfit_generator(), media_type="application/x-ndjson")


# ── Today / Day Recommendations ───────────────────────────────

VALID_DAY_TYPES = {"college", "outing", "trek", "holiday"}
VALID_SLOTS     = {"casual", "home", "around_home"}
VALID_DIRT      = {"clean", "light", "dirty"}

@app.get("/api/today")
async def get_today_recommendations(day_type: str = "college"):
    """Get smart outfit recommendations for today by slot."""
    if day_type not in VALID_DAY_TYPES:
        raise HTTPException(400, f"day_type must be one of {sorted(VALID_DAY_TYPES)}")
    result = recommender.recommend_today(day_type)
    return result


@app.get("/api/days")
async def get_day_log(date: str = None):
    """Get logged outfits for a specific date (default: today)."""
    date_str = date or datetime.today().strftime("%Y-%m-%d")
    log = recommender.load_day_log(date_str)
    return log or {"date": date_str, "day_type": None, "slots": []}


@app.post("/api/days/log")
async def log_day_outfit(payload: Dict[str, Any]):
    """Log a worn pairing for a slot on a day. Also logs wear on all items."""
    date_str   = payload.get("date", datetime.today().strftime("%Y-%m-%d"))
    day_type   = payload.get("day_type", "college")
    slot       = payload.get("slot")
    pairing_id = payload.get("pairing_id")
    dirt_level = payload.get("dirt_level", "light")
    notes      = payload.get("notes", "")

    if not slot or slot not in VALID_SLOTS:
        raise HTTPException(400, f"slot must be one of {sorted(VALID_SLOTS)}")
    if not pairing_id:
        raise HTTPException(400, "pairing_id is required")
    if dirt_level not in VALID_DIRT:
        raise HTTPException(400, f"dirt_level must be one of {sorted(VALID_DIRT)}")

    # Verify pairing exists
    pairing = storage.load_pairing(pairing_id)
    if not pairing:
        raise HTTPException(404, "Pairing not found")

    # Revert existing wear log for this slot to avoid double-counting
    recommender.revert_slot_wear(date_str, slot)

    # Map slot → destination for wear logging
    slot_dest_map = {"casual": "Casual", "home": "Home", "around_home": "around home"}
    dest = slot_dest_map.get(slot, "Casual")

    # Log wear on each item in the pairing
    item_ids = _pairing_item_ids(pairing)
    for item_id in item_ids:
        item = storage.load_item(item_id)
        if not item:
            continue
        item.setdefault("wear_history", []).append({
            "date": date_str, "destination": dest,
            "dirt_level": dirt_level, "slot": slot
        })
        item["wear_count"] = item.get("wear_count", 0) + 1
        item["last_worn"] = date_str
        if dirt_level == "dirty":
            item["status"] = "Dirty"
        elif item["wear_count"] >= item.get("laundry_limit", 3):
            item["status"] = "Dirty"
        storage.save_item(item)

    # Log wear on pairing
    pairing.setdefault("wear_history", []).append({
        "date": date_str, "destination": dest, "slot": slot, "dirt_level": dirt_level
    })
    pairing["last_worn"] = date_str
    storage.save_pairing(pairing)

    # Save day log
    day_log = recommender.log_day_wear(date_str, day_type, slot, pairing_id, dirt_level, notes)
    return {"success": True, "day_log": day_log}


@app.get("/api/days/history")
async def get_day_history(days: int = 14):
    """Return recent day logs (default last 14 days)."""
    return recommender.get_day_history(min(days, 60))


@app.delete("/api/days/{date}/slot/{slot}")
async def delete_day_slot(date: str, slot: str):
    """Remove a slot entry from a day log."""
    if slot not in VALID_SLOTS:
        raise HTTPException(400, f"slot must be one of {sorted(VALID_SLOTS)}")
    log = recommender.load_day_log(date)
    if not log:
        raise HTTPException(404, "No log for that date")
    
    # Revert item/pairing stats first
    recommender.revert_slot_wear(date, slot)
    
    log["slots"] = [s for s in log.get("slots", []) if s.get("slot") != slot]
    recommender.save_day_log(log)
    return {"success": True, "day_log": log}


@app.post("/api/pairings/custom")
async def create_custom_pairing(payload: Dict[str, Any]):
    """Creates a custom pairing, scores it using styling guidelines, and saves it."""
    upper_half = payload.get("upper_half", {})
    bottom_half = payload.get("bottom_half")
    footwear = payload.get("footwear")
    
    if not bottom_half:
        raise HTTPException(400, "bottom_half is required")
        
    pairing_data = {
        "upper_half": upper_half,
        "bottom_half": bottom_half,
        "footwear": footwear
    }
    
    try:
        new_pairing = recommender.score_and_save_custom_pairing(pairing_data)
        
        # Verify via programmatic validator to maintain safety
        import subprocess
        res = subprocess.run(["python3", "validate_wardrobe.py"], capture_output=True, text=True)
        if res.returncode != 0:
            # Revert saving if validation fails
            storage.delete_pairing(new_pairing["id"])
            # Remove from items pairing_ids as well
            item_ids = _pairing_item_ids(new_pairing)
            for iid in item_ids:
                item = storage.load_item(iid)
                if item and new_pairing["id"] in item.get("pairing_ids", []):
                    item["pairing_ids"].remove(new_pairing["id"])
                    storage.save_item(item)
            storage.force_reload()
            raise HTTPException(400, f"Invalid pairing according to validator: {res.stdout or res.stderr}")
            
        return new_pairing
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(500, f"Failed to create custom pairing: {str(e)}")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
