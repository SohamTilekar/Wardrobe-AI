# Wardrobe AI

Wardrobe AI is a smart, local-first styling and cataloging coordinator. It digitizes your physical clothing inventory, tracks laundry cycles, scores outfit compatibility using structural fashion principles, and generates personalized, scenario-based daily recommendations.

The application combines a lightweight, high-performance **FastAPI backend** with a **responsive, modern glassmorphism web interface** to manage your wardrobe without relying on external cloud databases.

---

## 🚀 Key Features

- **Smart Cataloging:** Store clothing items with detailed metadata including fabric texture, daylight-corrected colors, condition tiers, laundry limits, comfort ratings, and aging factors.
- **Wear & Wash Cycle Tracking:** Logs wear history, dirt levels, and laundry statuses (`Clean`, `Dirty`, `Washing`) to automate laundry alerts.
- **Styling Engine:** Evaluates clothing combinations across 5 scenario-based destinations (`Casual`, `Sleep`, `Home`, `around home`, and `Full formal`) and calculates real-time compatibility scores.
- **Dynamic Daily Slots:** Tailors daily outfit recommendations based on the schedule type (e.g., `🎓 College`, `🛍️ Outing`, `🥾 Trek`, `🏠 Holiday`) and maps them to specific slots (`casual`, `home`, `around_home`).
- **Programmatic Validation:** Uses a built-in strict validator script to audit schemas, broken references, image files, and illegal combinations.
- **Local & Private:** Everything runs locally with files stored in JSON and standard image formats.

---

## 📂 Project Directory Structure

```
Wardrobe AI/
├── wardrobe_data/            # Local-only Database (Git Ignored)
│   ├── items/                # Clothing inventory: [item_id].json files
│   ├── images/               # Clothing photos: [item_id].jpg/.png/.webp
│   ├── pairings/             # Outfit pairings: [pairing_id].json files
│   └── votes/                # Social logs / friend votes: [item_id].json
├── src/
│   ├── main.py               # FastAPI backend & endpoints
│   ├── storage.py            # Local JSON database reader/writer
│   ├── recommender.py        # Styling engine, scoring rules, and suggestion algorithm
│   ├── templates/
│   │   └── index.html        # Jinja2 template for web app
│   └── static/
│       ├── app.js            # Frontend orchestrator & streaming suggestions
│       └── style.css         # UI styles (glassmorphism theme)
├── requirements.txt          # Python dependencies
├── validate_wardrobe.py      # Programmatic database integrity checker
└── README.md                 # Project guide
```

---

## 📋 Data Schemas

### 1. Clothing Item Schema (`wardrobe_data/items/[id].json`)
Each item in your wardrobe must have a dedicated JSON file in `wardrobe_data/items/`.

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique slug matching the filename, e.g. `"item_tshirt_white_cotton"` |
| `name` | string | Descriptive name, e.g. `"White Cotton Crew Neck T-Shirt"` |
| `category` | string | Must match one of the canonical categories |
| `color_hex` | string | Standard hex color code, e.g. `"#F5F5F5"` |
| `color_name` | string | Common color name, e.g. `"Off-White"` |
| `fabric` | string | Fabric/Material type, e.g. `"Jersey Cotton"`, `"Ribbed Knit"` |
| `image_name` | string | Photo filename inside `/images/`, e.g. `"item_tshirt_white_cotton.jpg"` |
| `condition` | string | Usage tier: `"New"`, `"Good"`, `"Worn"`, or `"Aged"` |
| `status` | string | Laundry status: `"Clean"`, `"Dirty"`, or `"Washing"` |
| `wear_count` | integer | Number of wears in the current laundry cycle |
| `laundry_limit` | integer | Max wears allowed before item becomes `Dirty` |
| `comfort` | string | Comfort tier: `"High"`, `"Medium"`, or `"Low"` |
| `aging_factor` | float | Speed of fabric degradation (`0.1` to `5.0`). High numbers invoke scoring penalties |
| `wear_history` | array | Log entries: `[{"date": "YYYY-MM-DD", "destination": "...", "dirt_level": "..."}]` |
| `pairing_ids` | array | List of outfit pairing IDs containing this item |
| `usage_notes` | string | AI-written notes outlining styling recommendations, layers, or aging concerns |

### 2. Outfit Pairing Schema (`wardrobe_data/pairings/[id].json`)
Outfits represent styled pairings of multiple clothing items.

```json
{
  "id": "pairing_smart_1",
  "scores": {
    "Casual": 8,
    "Sleep": 1,
    "Home": 5,
    "around home": 7,
    "Full formal": 2
  },
  "upper_half": {
    "topest_layer": null,
    "upper_layer": null,
    "medium_layer": {
      "id": "item_tshirt_white_cotton",
      "tuck": "untucked",
      "sleeves": "down"
    },
    "bottom_layer": null
  },
  "bottom_half": "item_pants_beige_cargo_cotton",
  "footwear": "item_sneakers_white_canvas"
}
```

- **Layer Objects:** `upper_layer` and `medium_layer` support custom parameters:
  - `tuck`: `"untucked"` | `"french tuck"` | `"fully tucked"`
  - `sleeves`: `"down"` | `"rolled"` | `"up"`
- **Destination Scores:** Must provide a rating (0 to 10) for all 5 destinations: `Casual`, `Sleep`, `Home`, `around home`, and `Full formal`.

---

## 📐 Styling & Scoring Engine

The styling algorithms defined in `src/recommender.py` calculate compatibility scores based on fabric, condition, style guidelines, and laundry recency:

### 1. Destination Scoring Logic
Custom pairings are evaluated on a `0–10` scale using several rules:
- **Sleep Heuristics:** High scores require loose/soft tops (`T-Shirt`, `Tank Top`, etc.) paired with comfort-oriented bottoms (`Night Pants`, `Shorts`). If both items have `High` comfort, score jumps to `9`.
- **Home Heuristics:** Layering is strictly forbidden (`topest_layer`, `upper_layer`, `bottom_layer` must be `null`). Comfort ratings drive the baseline score (up to `8` for dual-`High` comfort). Formal pieces (e.g. `Trousers`, `Blazers`) receive a `-3` penalty.
- **Around Home Heuristics:** No layering allowed. Capped at a maximum score of `3` if any of the items are in `Aged` condition.
- **Casual Heuristics:** Looks look at classic coordinates (e.g., `Jeans` / `Chinos` + `Hoodie` / `Button-down` / `Polo`). Clean footwear boosts the score.
- **Full Formal Heuristics:** Requires structured pairings (`Trousers`/`Chinos` + `Dress Shirt`/`Blazer`). Fully tucked shirts and formal footwear earn bonuses.

### 2. Recency & Laundry Biases
To promote natural rotation of your clothes, the recommender shifts pairing scores on the fly:
- **Recency Bonus:** Earn up to `+3.0` points for outfits that haven't been worn recently (0.25 points per day since last worn).
- **Dirt Penalty:** Subtracts up to `-2.0` points as items get closer to their laundry limit.
- **Aging Factor Penalty:** Outfits incorporating delicate fabrics (high `aging_factor`) receive a penalty to limit frequency of use.
- **Finish-the-Cycle Bias:** Pushes partially worn items sitting in your closet for more than 2 days (up to `+5.0` bonus) so you wash them together instead of wearing clean shirts.
- **Unworn Item Bias:** Grants up to `+3.0` points for clean items ignored for over 7 days, or `+3.5` points for items recently purchased but never worn.

### 3. Special Styling Rules
- **Oversized T-Shirts (`item_tshirt_black_cotton`):** Must be placed as a `bottom_layer` under an open outer layer (e.g. a jacket or open button-down). Standalone wears are penalized to `1` across all destinations.
- **Thick T-Shirts (`item_tshirt_pista_thick`):** Must be layered for `Casual` outings. Standalone wear is only approved for `around home` or `Home` environments.

---

## 🛠️ Programmatic Data Validation

To prevent formatting errors, broken references, or invalid outfit styling, the repository features a dedicated validator: `validate_wardrobe.py`.

### Audited Rules:
1. **JSON Syntax:** Catches formatting mistakes in item or pairing files.
2. **Missing Fields:** Enforces all schema parameters (including `comfort` and `aging_factor`).
3. **Cross-References:** Ensures item `pairing_ids` exist in the pairings folder, and vice versa.
4. **Category Integrity:** Verifies categories against the allowed list of Tops, Bottoms, Footwear, and Accessories.
5. **Rule Constraints:** Enforces styling constraints like the **No-Layering rule** for Home, Sleep, and Around Home outfits.
6. **Orphan Warnings:** Flags images not attached to items, or items with zero pairings.

### Run the Validator:
```bash
python3 validate_wardrobe.py
```
*Note: Always ensure the script returns exit code `0` (indicating no errors) before running the application.*

---

## 🤖 Wardrobe Operations Guide (For Users & AI Agents)

Because Wardrobe AI relies on complex JSON structures, bidirectional references (`pairing_ids`), and strict styling guidelines, **manually updating files is highly discouraged**. 

Instead, you should use the **Antigravity CLI** or delegate to AI agents to add, rename, edit, or delete items and outfits.

### 1. Adding a New Item
When you want to add a new garment, prompt your agent with the photo file (e.g., `item_jacket_denim.jpg`). The agent will:
1. Copy the photo to `wardrobe_data/images/`.
2. Analyze the image to populate the metadata (detecting texture for `fabric`, calculating true `color_hex`, checking `condition`, and choosing the closest canonical `category`).
3. Set appropriate values for `comfort`, `laundry_limit`, and `aging_factor`.
4. Generate new compatible pairings using the **5-Point Versatility Test** and **Smart Generation Protocol**.
5. Save the item JSON and run `validate_wardrobe.py` to confirm everything is safe.

### 2. Deleting or Renaming an Item
If you rename or remove an item, tell your agent. The agent will:
- Safely delete/rename the JSON and image.
- Traversal the pairings list and clean up references inside the pairing JSONs.
- Clean up the `pairing_ids` lists of other related items.
- Run the validator to ensure no broken links remain.

---

## 💻 Local Setup & Execution

### 1. Install Dependencies
Make sure you have Python 3 installed. Navigate to the project root and install the dependencies:
```bash
pip install -r requirements.txt
```

### 2. Run the Development Server
Launch the FastAPI server using `uvicorn`:
```bash
python3 src/main.py
```
Or run directly via `uvicorn`:
```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Open the Dashboard
Open your web browser and navigate to:
```
http://localhost:8000
```
Use the tabs on the header to select **Today's Schedule**, view **Wear History**, explore **Suggested Outfits**, or audit your **Wardrobe Status**.
