import json
import os
from pathlib import Path
from typing import Dict, Any, List

DATA_DIR = Path("/mnt/soham/soham_code/Wardrobe AI/wardrobe_data")
ITEMS_DIR = DATA_DIR / "items"
IMAGES_DIR = DATA_DIR / "images"
PAIRINGS_DIR = DATA_DIR / "pairings"
VOTES_DIR = DATA_DIR / "votes"

# Ensure directories exist
ITEMS_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
PAIRINGS_DIR.mkdir(parents=True, exist_ok=True)
VOTES_DIR.mkdir(parents=True, exist_ok=True)

# In-memory cache
_items_cache: Dict[str, Dict[str, Any]] = {}
_pairings_cache: Dict[str, Dict[str, Any]] = {}
_loaded = False

def force_reload():
    """Invalidate the in-memory cache so next access re-reads from disk."""
    global _loaded
    _loaded = False
    _items_cache.clear()
    _pairings_cache.clear()

def _init_cache():
    global _loaded
    if _loaded: return
    for file_path in ITEMS_DIR.glob("*.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "id" in data:
                    _items_cache[data["id"]] = data
        except Exception:
            pass
    for file_path in PAIRINGS_DIR.glob("*.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "id" in data:
                    _pairings_cache[data["id"]] = data
        except Exception:
            pass
    _loaded = True

def load_item(item_id: str) -> Dict[str, Any]:
    _init_cache()
    return _items_cache.get(item_id, {})

def save_item(item_data: Dict[str, Any]) -> bool:
    _init_cache()
    item_id = item_data.get("id")
    if not item_id:
        return False
    file_path = ITEMS_DIR / f"{item_id}.json"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(item_data, f, indent=2)
        _items_cache[item_id] = item_data
        return True
    except Exception:
        return False

def load_all_items() -> Dict[str, Dict[str, Any]]:
    _init_cache()
    return _items_cache

def load_pairing(pairing_id: str) -> Dict[str, Any]:
    _init_cache()
    return _pairings_cache.get(pairing_id, {})

def save_pairing(pairing_data: Dict[str, Any]) -> bool:
    _init_cache()
    pairing_id = pairing_data.get("id")
    if not pairing_id:
        return False
    file_path = PAIRINGS_DIR / f"{pairing_id}.json"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(pairing_data, f, indent=2)
        _pairings_cache[pairing_id] = pairing_data
        return True
    except Exception:
        return False

def load_all_pairings() -> Dict[str, Dict[str, Any]]:
    _init_cache()
    return _pairings_cache

def delete_item(item_id: str) -> bool:
    _init_cache()
    file_path = ITEMS_DIR / f"{item_id}.json"
    if file_path.exists():
        file_path.unlink()
    if item_id in _items_cache:
        del _items_cache[item_id]
    for ext in [".jpg", ".png", ".webp", ".jpeg"]:
        img_path = IMAGES_DIR / f"{item_id}{ext}"
        if img_path.exists():
            img_path.unlink()
    return True

def delete_pairing(pairing_id: str) -> bool:
    _init_cache()
    file_path = PAIRINGS_DIR / f"{pairing_id}.json"
    if file_path.exists():
        file_path.unlink()
    if pairing_id in _pairings_cache:
        del _pairings_cache[pairing_id]
    return True

def save_vote(target_id: str, vote_data: Dict[str, Any]) -> bool:
    # Append to target_id.json in votes dir
    file_path = VOTES_DIR / f"{target_id}.json"
    votes = []
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                votes = json.load(f)
        except Exception:
            pass
    votes.append(vote_data)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(votes, f, indent=2)
        return True
    except Exception:
        return False

def get_votes(target_id: str) -> List[Dict[str, Any]]:
    file_path = VOTES_DIR / f"{target_id}.json"
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []
