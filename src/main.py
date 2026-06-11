import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("wardrobe_main")

app = FastAPI(title="Smart Wardrobe Assistant")

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
    return list(items.values())

@app.get("/api/items/{item_id}")
async def get_item(item_id: str):
    item = storage.load_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
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
    dirt_level = payload.get("dirt_level", "light")   # clean | light | dirty
    force_status = payload.get("force_status")        # "Dirty" or None

    item.setdefault("wear_history", []).append({
        "date": date_str, "destination": dest, "dirt_level": dirt_level
    })
    item["wear_count"] = item.get("wear_count", 0) + 1
    item["last_worn"]  = date_str

    # Determine new status
    if force_status:
        item["status"] = force_status
    elif dirt_level == "dirty":
        item["status"] = "Dirty"
    elif dirt_level == "clean":
        pass  # keep current status, don't change
    else:
        # "light" — auto-dirty if hit laundry limit
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
    item = storage.load_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    entry = {
        "friend": payload.get("friend", "Anonymous"),
        "vote":   payload.get("vote", "liked"),
        "note":   payload.get("note"),
        "date":   payload.get("date", datetime.today().strftime("%Y-%m-%d")),
    }
    item.setdefault("friend_votes", []).append(entry)
    storage.save_item(item)
    return item


# ── Pairings CRUD ────────────────────────────────────────────

@app.get("/api/pairings")
async def get_pairings():
    return list(storage.load_all_pairings().values())

@app.get("/api/pairings/{pairing_id}")
async def get_pairing(pairing_id: str):
    p = storage.load_pairing(pairing_id)
    if not p:
        raise HTTPException(status_code=404, detail="Pairing not found")
    return p


# ── Pairing wear / wash / vote ───────────────────────────────

@app.post("/api/pairings/{pairing_id}/wear")
async def log_pairing_wear(pairing_id: str, payload: Dict[str, Any]):
    """Log wear for every item in a pairing."""
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
    """Mark all items in a pairing clean."""
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
    """Record a friend vote on a pairing."""
    pairing = storage.load_pairing(pairing_id)
    if not pairing:
        raise HTTPException(status_code=404, detail="Pairing not found")

    entry = {
        "friend":  payload.get("friend", "Anonymous"),
        "vote":    payload.get("vote", "liked"),
        "note":    payload.get("note"),
        "item_id": payload.get("item_id"),
        "date":    payload.get("date", datetime.today().strftime("%Y-%m-%d")),
    }
    pairing.setdefault("friend_votes", []).append(entry)
    storage.save_pairing(pairing)
    return pairing


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


# ── Outfit suggestions ───────────────────────────────────────

@app.get("/api/outfits")
async def get_outfit_suggestions(destination: str = "Casual"):
    all_items = storage.load_all_items()
    pairings  = storage.load_all_pairings().values()
    clean_items = {k: v for k, v in all_items.items() if v.get("status") == "Clean"}
    outfits: List[Dict[str, Any]] = []

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

        # Recency bonus
        last_worn = p.get("last_worn")
        if last_worn:
            days_ago = (datetime.today() - datetime.strptime(last_worn, "%Y-%m-%d")).days
            recency_bonus = min(1.5, days_ago * 0.05)
        else:
            recency_bonus = 2.0  # Never worn

        final_score = round(dest_score + recency_bonus, 2)

        outfits.append({
            "pairing_id":  p.get("id"),
            "score":       final_score,
            "dest_score":  dest_score,
            "scores":      scores,
            "last_worn":   last_worn,
            "friend_votes": p.get("friend_votes", []),
            "topest_layer": resolve_layer(u.get("topest_layer")),
            "upper_layer":  resolve_layer(u.get("upper_layer")),
            "medium_layer": resolve_layer(u.get("medium_layer")),
            "bottom_layer": resolve_layer(u.get("bottom_layer")),
            "bottom_half":  resolve_layer(p.get("bottom_half")),
            "footwear":     resolve_layer(p.get("footwear")),
            "item_ids":    p_items,
        })

    outfits.sort(key=lambda x: x["score"], reverse=True)
    return outfits[:20]


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
