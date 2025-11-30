# BeerXML Recipe Import & Batch Tracking Design

**Date:** 2025-11-30
**Status:** Draft
**Related Issue:** #22 (BeerXML recipe import and fermentation tracking)

## Overview

Import BeerXML recipes to automatically populate fermentation parameters and track progress against recipe targets. This design establishes a foundational architecture that enables future Brewfather-like functionality (recipe designer, inventory, style guides, etc.).

## Goals

1. Parse BeerXML 1.0 files and extract fermentation-relevant data
2. Store recipes with OG/FG targets and yeast temperature ranges
3. Create batch tracking to link devices with recipes over time periods
4. Display fermentation progress against recipe targets
5. Warn when temperature is outside yeast's recommended range
6. Lay foundation for future recipe/batch management features

## Non-Goals (Future Phases)

- Full recipe designer/calculator
- Ingredient inventory management
- Mash/fermentation profile management
- Equipment profiles
- Recipe scaling

## Architecture

### Data Model

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│     Style       │     │     Recipe      │     │     Batch       │
│  (BJCP 2021)    │◄────│                 │◄────│                 │
├─────────────────┤     ├─────────────────┤     ├─────────────────┤
│ id (PK)         │     │ id (PK)         │     │ id (PK)         │
│ guide           │     │ name            │     │ recipe_id (FK)  │
│ category_number │     │ style_id (FK)   │     │ device_id (FK)  │
│ style_letter    │     │ author          │     │ batch_number    │
│ name            │     │ og_target       │     │ status          │
│ category        │     │ fg_target       │     │ brew_date       │
│ og_min/max      │     │ yeast_name      │     │ start_time      │
│ fg_min/max      │     │ yeast_temp_min  │     │ end_time        │
│ ibu_min/max     │     │ yeast_temp_max  │     │ measured_og     │
│ srm_min/max     │     │ yeast_attenuation│    │ measured_fg     │
│ abv_min/max     │     │ beerxml_content │     │ notes           │
│ description     │     │ created_at      │     │ created_at      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
                                                ┌─────────────────┐
                                                │    Reading      │
                                                │   (existing)    │
                                                ├─────────────────┤
                                                │ + batch_id (FK) │
                                                │   (nullable)    │
                                                └─────────────────┘
```

### Entity Relationships

- **Style** → Reference data (BJCP 2021 guidelines, pre-seeded)
- **Recipe** → Template for brewing, can reference a Style
- **Batch** → Instance of brewing a Recipe on a Device
- **Reading** → Optionally linked to a Batch (new readings auto-linked)

### Batch Status Workflow

```
Planning → Fermenting → Conditioning → Completed → Archived
    │           │            │             │
    │           │            │             └── Historical record
    │           │            └── Cold crash / carbonation
    │           └── Active fermentation (readings collected)
    └── Scheduled but not started
```

## Database Schema

### New Tables

```sql
-- BJCP Style Guidelines (reference data)
CREATE TABLE styles (
    id TEXT PRIMARY KEY,  -- e.g., "bjcp-2021-18b"
    guide TEXT NOT NULL,  -- "BJCP 2021", "BJCP 2015", "BA 2023"
    category_number TEXT NOT NULL,  -- "18"
    style_letter TEXT,  -- "B"
    name TEXT NOT NULL,  -- "American Pale Ale"
    category TEXT NOT NULL,  -- "Pale American Ale"
    type TEXT,  -- "Ale", "Lager", "Mixed", "Wheat", "Cider", "Mead"
    og_min REAL,
    og_max REAL,
    fg_min REAL,
    fg_max REAL,
    ibu_min REAL,
    ibu_max REAL,
    srm_min REAL,
    srm_max REAL,
    abv_min REAL,
    abv_max REAL,
    description TEXT,
    aroma TEXT,
    appearance TEXT,
    flavor TEXT,
    mouthfeel TEXT,
    history TEXT,
    ingredients TEXT,
    examples TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_styles_guide ON styles(guide);
CREATE INDEX idx_styles_category ON styles(category_number, style_letter);

-- Recipes (imported from BeerXML or created manually)
CREATE TABLE recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    author TEXT,
    style_id TEXT REFERENCES styles(id),
    type TEXT,  -- "All Grain", "Extract", "Partial Mash"

    -- Gravity targets
    og_target REAL,
    fg_target REAL,

    -- Yeast info (extracted from BeerXML)
    yeast_name TEXT,
    yeast_lab TEXT,
    yeast_product_id TEXT,
    yeast_temp_min REAL,  -- Celsius
    yeast_temp_max REAL,  -- Celsius
    yeast_attenuation REAL,  -- Percent

    -- Other targets
    ibu_target REAL,
    srm_target REAL,
    abv_target REAL,
    batch_size REAL,  -- Liters

    -- Raw BeerXML for future parsing
    beerxml_content TEXT,

    -- Metadata
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_recipes_name ON recipes(name);
CREATE INDEX idx_recipes_style ON recipes(style_id);

-- Batches (instances of brewing a recipe)
CREATE TABLE batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER REFERENCES recipes(id),
    device_id TEXT REFERENCES devices(id),

    -- Batch identification
    batch_number INTEGER,  -- Auto-incremented per user
    name TEXT,  -- Optional override, defaults to recipe name

    -- Status tracking
    status TEXT NOT NULL DEFAULT 'planning',  -- planning, fermenting, conditioning, completed, archived

    -- Timeline
    brew_date DATE,
    start_time TIMESTAMP,  -- When fermentation started (readings begin)
    end_time TIMESTAMP,  -- When fermentation ended

    -- Measured values (actual vs recipe targets)
    measured_og REAL,
    measured_fg REAL,
    measured_abv REAL,
    measured_attenuation REAL,

    -- Notes and metadata
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_batches_device ON batches(device_id);
CREATE INDEX idx_batches_recipe ON batches(recipe_id);
CREATE INDEX idx_batches_status ON batches(status);
CREATE INDEX idx_batches_dates ON batches(start_time, end_time);
```

### Schema Migrations

```sql
-- Add batch_id to readings table
ALTER TABLE readings ADD COLUMN batch_id INTEGER REFERENCES batches(id);
CREATE INDEX idx_readings_batch ON readings(batch_id);
```

## BeerXML Parser

### Supported Fields (BeerXML 1.0)

From `<RECIPE>`:
- `NAME` → recipe.name
- `TYPE` → recipe.type
- `BREWER` → recipe.author
- `OG` → recipe.og_target
- `FG` → recipe.fg_target
- `IBU` → recipe.ibu_target
- `EST_COLOR` → recipe.srm_target
- `EST_ABV` → recipe.abv_target
- `BATCH_SIZE` → recipe.batch_size (convert from liters)

From `<STYLE>`:
- `NAME` → lookup/create style reference
- `CATEGORY_NUMBER` + `STYLE_LETTER` → style lookup

From `<YEAST>` (first entry):
- `NAME` → recipe.yeast_name
- `LABORATORY` → recipe.yeast_lab
- `PRODUCT_ID` → recipe.yeast_product_id
- `MIN_TEMPERATURE` → recipe.yeast_temp_min (already Celsius)
- `MAX_TEMPERATURE` → recipe.yeast_temp_max (already Celsius)
- `ATTENUATION` → recipe.yeast_attenuation

### Parser Implementation

```python
# backend/services/beerxml_parser.py

from dataclasses import dataclass
from typing import Optional
import xml.etree.ElementTree as ET

@dataclass
class ParsedYeast:
    name: Optional[str] = None
    lab: Optional[str] = None
    product_id: Optional[str] = None
    temp_min: Optional[float] = None  # Celsius
    temp_max: Optional[float] = None  # Celsius
    attenuation: Optional[float] = None

@dataclass
class ParsedStyle:
    name: Optional[str] = None
    category: Optional[str] = None
    category_number: Optional[str] = None
    style_letter: Optional[str] = None
    guide: Optional[str] = None

@dataclass
class ParsedRecipe:
    name: str
    author: Optional[str] = None
    type: Optional[str] = None
    og: Optional[float] = None
    fg: Optional[float] = None
    ibu: Optional[float] = None
    srm: Optional[float] = None
    abv: Optional[float] = None
    batch_size: Optional[float] = None  # Liters
    style: Optional[ParsedStyle] = None
    yeast: Optional[ParsedYeast] = None
    raw_xml: str = ""

def parse_beerxml(xml_content: str) -> list[ParsedRecipe]:
    """Parse BeerXML content and return list of recipes."""
    root = ET.fromstring(xml_content)
    recipes = []

    for recipe_elem in root.findall('.//RECIPE'):
        recipe = _parse_recipe(recipe_elem, xml_content)
        recipes.append(recipe)

    return recipes

def _get_text(elem, tag: str) -> Optional[str]:
    """Get text content of child element."""
    child = elem.find(tag)
    return child.text.strip() if child is not None and child.text else None

def _get_float(elem, tag: str) -> Optional[float]:
    """Get float value of child element."""
    text = _get_text(elem, tag)
    if text:
        try:
            return float(text)
        except ValueError:
            return None
    return None

def _parse_recipe(elem, raw_xml: str) -> ParsedRecipe:
    """Parse a single RECIPE element."""
    recipe = ParsedRecipe(
        name=_get_text(elem, 'NAME') or "Unnamed Recipe",
        author=_get_text(elem, 'BREWER'),
        type=_get_text(elem, 'TYPE'),
        og=_get_float(elem, 'OG'),
        fg=_get_float(elem, 'FG'),
        ibu=_get_float(elem, 'IBU'),
        abv=_get_float(elem, 'EST_ABV'),
        batch_size=_get_float(elem, 'BATCH_SIZE'),
        raw_xml=raw_xml
    )

    # Parse style
    style_elem = elem.find('.//STYLE')
    if style_elem is not None:
        recipe.style = ParsedStyle(
            name=_get_text(style_elem, 'NAME'),
            category=_get_text(style_elem, 'CATEGORY'),
            category_number=_get_text(style_elem, 'CATEGORY_NUMBER'),
            style_letter=_get_text(style_elem, 'STYLE_LETTER'),
            guide=_get_text(style_elem, 'STYLE_GUIDE'),
        )

    # Parse first yeast
    yeast_elem = elem.find('.//YEASTS/YEAST')
    if yeast_elem is not None:
        recipe.yeast = ParsedYeast(
            name=_get_text(yeast_elem, 'NAME'),
            lab=_get_text(yeast_elem, 'LABORATORY'),
            product_id=_get_text(yeast_elem, 'PRODUCT_ID'),
            temp_min=_get_float(yeast_elem, 'MIN_TEMPERATURE'),
            temp_max=_get_float(yeast_elem, 'MAX_TEMPERATURE'),
            attenuation=_get_float(yeast_elem, 'ATTENUATION'),
        )

    return recipe
```

## API Endpoints

### Recipes

```
POST   /api/recipes/import          Upload BeerXML file, returns created recipe(s)
GET    /api/recipes                 List all recipes
GET    /api/recipes/{id}            Get recipe details
PUT    /api/recipes/{id}            Update recipe
DELETE /api/recipes/{id}            Delete recipe
```

### Batches

```
POST   /api/batches                 Create batch (from recipe + device)
GET    /api/batches                 List batches (filter by status, device)
GET    /api/batches/{id}            Get batch details
PUT    /api/batches/{id}            Update batch (status, measured values, notes)
DELETE /api/batches/{id}            Delete batch
GET    /api/batches/{id}/progress   Get fermentation progress vs targets
GET    /api/batches/{id}/readings   Get readings for this batch
```

### Styles

```
GET    /api/styles                  List styles (filter by guide, category)
GET    /api/styles/{id}             Get style details
```

### Request/Response Examples

**Import Recipe:**
```http
POST /api/recipes/import
Content-Type: multipart/form-data

file: <beerxml file>
```

```json
{
  "recipes": [
    {
      "id": 1,
      "name": "DrSmurto's Landlord II",
      "og_target": 1.046,
      "fg_target": 1.012,
      "yeast_name": "Wyeast 1469 - West Yorkshire Ale",
      "yeast_temp_min": 18.0,
      "yeast_temp_max": 22.0,
      "style": {
        "name": "Special/Best/Premium Bitter",
        "category": "British Bitter"
      }
    }
  ]
}
```

**Create Batch:**
```http
POST /api/batches
Content-Type: application/json

{
  "recipe_id": 1,
  "device_id": "tilt-red",
  "brew_date": "2025-11-30",
  "status": "fermenting",
  "measured_og": 1.048
}
```

**Get Progress:**
```http
GET /api/batches/1/progress
```

```json
{
  "batch_id": 1,
  "recipe_name": "DrSmurto's Landlord II",
  "status": "fermenting",
  "targets": {
    "og": 1.046,
    "fg": 1.012,
    "attenuation": 73.2,
    "abv": 4.5
  },
  "measured": {
    "og": 1.048,
    "current_sg": 1.018,
    "attenuation": 62.5,
    "abv": 3.9
  },
  "progress": {
    "percent_complete": 83.3,
    "sg_remaining": 0.006,
    "estimated_days_remaining": 2.5
  },
  "temperature": {
    "current": 19.5,
    "yeast_min": 18.0,
    "yeast_max": 22.0,
    "status": "in_range"
  }
}
```

## Frontend Components

### New Routes

- `/recipes` - Recipe list and import
- `/recipes/{id}` - Recipe detail view
- `/batches` - Batch list with status filters
- `/batches/{id}` - Batch detail with fermentation chart

### UI Changes

1. **Dashboard** - Show active batch info on TiltCard
   - Recipe name and style
   - Progress bar (current SG vs target FG)
   - Temperature status indicator (in range / warning)

2. **TiltChart** - Enhanced with batch context
   - Target FG line
   - Yeast temp range shading
   - Batch timeline markers

3. **Recipe Import** - New page
   - Drag & drop BeerXML upload
   - Preview parsed data before saving
   - Style matching/selection

4. **Batch Management** - New page
   - Create batch from recipe
   - Assign to device
   - Track status through lifecycle
   - Enter measured values (OG, FG)

### Mockup: Dashboard with Active Batch

```
┌─────────────────────────────────────────────────────────┐
│ DrSmurto's Landlord II              ▓▓▓▓ [RSSI: -65]   │
│ British Bitter • Batch #12                              │
├─────────────────────────────────────────────────────────┤
│                                                         │
│    ┌─────────┐        ┌─────────┐                      │
│    │  1.018  │        │  19.5°C │                      │
│    │ Gravity │        │  Temp   │                      │
│    └─────────┘        └─────────┘                      │
│                                                         │
│  Progress to FG ████████████░░░░ 83%                   │
│  Target: 1.012  |  ETA: ~2.5 days                      │
│                                                         │
│  Temp: ✓ In range (18-22°C)                            │
│                                                         │
│  [═══════════════ Chart ═══════════════]               │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## BJCP Style Data

### Seeding Strategy

Pre-seed BJCP 2021 styles from official guidelines. Data available from:
- https://github.com/brewpoo/BeerXML-Standard (XML format)
- Manual JSON conversion from BJCP guidelines PDF

### Sample Style Entry

```json
{
  "id": "bjcp-2021-18b",
  "guide": "BJCP 2021",
  "category_number": "18",
  "style_letter": "B",
  "name": "American Pale Ale",
  "category": "Pale American Ale",
  "type": "Ale",
  "og_min": 1.045,
  "og_max": 1.060,
  "fg_min": 1.010,
  "fg_max": 1.015,
  "ibu_min": 30,
  "ibu_max": 50,
  "srm_min": 5,
  "srm_max": 10,
  "abv_min": 4.5,
  "abv_max": 6.2,
  "description": "An average-strength, hop-forward, pale American craft beer..."
}
```

## WebSocket Integration

### New Message Types

```json
// Batch started - notify clients to refresh
{
  "type": "batch_started",
  "batch_id": 1,
  "device_id": "tilt-red",
  "recipe_name": "DrSmurto's Landlord II"
}

// Batch status changed
{
  "type": "batch_status",
  "batch_id": 1,
  "status": "conditioning"
}

// Temperature warning
{
  "type": "temp_warning",
  "batch_id": 1,
  "current_temp": 24.5,
  "yeast_max": 22.0,
  "message": "Temperature above yeast range!"
}
```

## Reading-Batch Linking

### Auto-linking Logic

When a new reading arrives:
1. Find active batch for the device (status = 'fermenting')
2. If found and batch.start_time <= reading.timestamp:
   - Set reading.batch_id = batch.id
3. If no active batch, reading.batch_id = NULL

### Batch Reading Queries

```python
# Get readings for a batch by explicit link
SELECT * FROM readings
WHERE batch_id = :batch_id
ORDER BY timestamp;

# Or by time range (fallback for historical)
SELECT * FROM readings
WHERE device_id = :device_id
  AND timestamp BETWEEN :start_time AND :end_time
ORDER BY timestamp;
```

## Implementation Phases

### Phase 1: Core Schema & Parser (Issue #22)
1. Database migrations (styles, recipes, batches)
2. BeerXML parser service
3. Recipe API endpoints
4. Batch API endpoints
5. Basic frontend (import, list, detail views)

### Phase 2: Integration & UI
1. Dashboard integration (batch context on TiltCard)
2. Enhanced TiltChart with targets
3. Temperature warnings
4. WebSocket notifications

### Phase 3: BJCP Styles
1. Style data seeding script
2. Style API endpoints
3. Recipe-style linking
4. Style browser UI

### Future: Full Recipe Management
- Ingredient tables (hops, fermentables, yeasts, miscs)
- Recipe designer
- Inventory tracking
- Recipe scaling
- Full Brewfather feature parity

## Testing Strategy

1. **Unit Tests**
   - BeerXML parser with various file samples
   - Progress calculations
   - Temperature range checks

2. **Integration Tests**
   - Recipe import flow
   - Batch lifecycle
   - Reading-batch linking

3. **Sample Files**
   - Export from Brewfather, BeerSmith, Brewer's Friend
   - Edge cases (missing fields, multiple recipes)

## Security Considerations

1. **File Upload** - Validate XML, limit file size (1MB)
2. **XML Parsing** - Use defusedxml to prevent XXE attacks
3. **Input Validation** - Sanitize recipe names, notes

## References

- [BeerXML 1.0 Specification](https://www.beerxml.com/beerxml.htm)
- [BJCP 2021 Style Guidelines](https://www.bjcp.org/style/2021/beer/)
- [Brewfather API Documentation](https://docs.brewfather.app/api)
- [brewpoo/BeerXML-Standard](https://github.com/brewpoo/BeerXML-Standard)
