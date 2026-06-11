import json
import os
from pathlib import Path
from typing import Dict, Any, List

DATA_DIR = Path("/mnt/soham/soham_code/Wardrobe AI/wardrobe_data")
ITEMS_DIR = DATA_DIR / "items"
IMAGES_DIR = DATA_DIR / "images"
PAIRINGS_DIR = DATA_DIR / "pairings"

# Ensure directories exist
ITEMS_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
PAIRINGS_DIR.mkdir(parents=True, exist_ok=True)

def load_item(item_id: str) -> Dict[str, Any]:
    file_path = ITEMS_DIR / f"{item_id}.json"
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_item(item_data: Dict[str, Any]) -> bool:
    item_id = item_data.get("id")
    if not item_id:
        return False
    file_path = ITEMS_DIR / f"{item_id}.json"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(item_data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving item {item_id}: {e}")
        return False

def load_all_items() -> Dict[str, Dict[str, Any]]:
    items = {}
    for file_path in ITEMS_DIR.glob("*.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "id" in data:
                    items[data["id"]] = data
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
    return items

def load_pairing(pairing_id: str) -> Dict[str, Any]:
    file_path = PAIRINGS_DIR / f"{pairing_id}.json"
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_pairing(pairing_data: Dict[str, Any]) -> bool:
    pairing_id = pairing_data.get("id")
    if not pairing_id:
        return False
    file_path = PAIRINGS_DIR / f"{pairing_id}.json"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(pairing_data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving pairing {pairing_id}: {e}")
        return False

def load_all_pairings() -> Dict[str, Dict[str, Any]]:
    pairings = {}
    for file_path in PAIRINGS_DIR.glob("*.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "id" in data:
                    pairings[data["id"]] = data
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
    return pairings

def delete_item(item_id: str) -> bool:
    file_path = ITEMS_DIR / f"{item_id}.json"
    if file_path.exists():
        file_path.unlink()
    # Remove image if exists
    for ext in [".jpg", ".png", ".webp", ".jpeg"]:
        img_path = IMAGES_DIR / f"{item_id}{ext}"
        if img_path.exists():
            img_path.unlink()
    return True

def delete_pairing(pairing_id: str) -> bool:
    file_path = PAIRINGS_DIR / f"{pairing_id}.json"
    if file_path.exists():
        file_path.unlink()
    return True
