# Wardrobe AI

Wardrobe AI is your intelligent styling and cataloging partner. It digitizes your physical clothing inventory into a decentralized database (JSON per item), tracks laundry cycles, scores outfit compatibility, and generates stylish coordinations.

## Features
- **Smart Cataloging:** Add clothes via image. AI auto-tags fabric, color, condition, and laundry limits.
- **Wear Tracking:** Monitor times worn, log destinations, and know exactly what's clean or dirty.
- **AI Styling & Scoring:** Generate multi-layer outfits. AI evaluates color harmony, texture contrast, and destination logic to score pairs (1-10).
- **Bidirectional Linking:** Outfits are fully cross-referenced. If you look at your denim jacket, you see the exact jeans and shoes it was paired with.

## Pairing System Schema

Wardrobe AI uses a highly structured, layer-based pairing system. All combinations are stored in a centralized database at `/wardrobe_data/pairings.json`. Each item JSON simply stores a `pairing_ids` list containing the IDs of outfits it belongs to. This allows you to traverse from any single item to its full, recommended look via the centralized file.

An outfit consists of:

### 1. Upper Half
The upper body is split into 4 possible layers, each handling specific tucking properties:
- **Topest Layer**: Outermost layer (Jacket, Coat, Blazer). Can be `null` if N/A.
- **Upper Layer**: Over-shirt (e.g., Flannel worn open over a tee). Includes `tuck` property (`tuck in`, `no tuck`, `french tuck`) and `sleeves` state (`rolled up`, `down`). Can be `null`.
- **Medium Layer**: Core shirt/t-shirt. Includes `tuck` property and `sleeves` state.
- **Bottom Layer**: Innermost layer (Sleeveless undershirt, thermal). Can be `null`.

### 2. Bottom Half
The primary leg-wear (Jeans, Pants, Shorts, Chinos).

### 3. Footwear
The exact shoes, boots, or slippers (can be `null` if barefoot/NA).

### Example JSON Entry
When the AI generates a pairing, it injects this structure into `pairings.json`:
```json
[
  {
    "id": "pairing_1",
    "score": 9,
    "upper_half": {
      "topest_layer": "item_jacket_denim",
      "upper_layer": null,
      "medium_layer": {
        "id": "item_tshirt_white",
        "tuck": "french tuck",
        "sleeves": "down"
      },
      "bottom_layer": null
    },
    "bottom_half": "item_jeans_blue",
    "footwear": "item_sneakers_white",
    "friend_votes": []
  }
]
```

And each participating item gets updated:
```json
"pairing_ids": ["pairing_1"]
```

## Setup
Data is stored locally under `/wardrobe_data/items/` (JSON files), `/wardrobe_data/images/` (Photos), and `/wardrobe_data/pairings.json` (Outfits).

## How to Run

Wardrobe AI is built as a FastAPI web application. To run the application locally:

1. Ensure you have Python and `venv` set up, and your dependencies installed (e.g. `fastapi`, `uvicorn`, `jinja2`).
2. Run the development server:
```bash
uvicorn main:app --reload
```
3. Open your browser and navigate to `http://localhost:8000`.
