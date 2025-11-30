# BeerXML Recipe Import & Batch Tracking Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement BeerXML recipe import and batch tracking to display fermentation progress against recipe targets.

**Architecture:** SQLAlchemy models (Style, Recipe, Batch) with FastAPI endpoints. BeerXML parser extracts yeast temp ranges and gravity targets. Readings auto-link to active batches. Frontend shows progress and temp warnings.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, Pydantic, defusedxml, SvelteKit, Svelte 5 runes

**Reference Design:** `docs/plans/2025-11-30-beerxml-recipe-import-design.md`

---

## Task 1: Database Schema - Add Style, Recipe, Batch Tables

**Files:**
- Modify: `backend/database.py` (add migration functions)
- Modify: `backend/models.py` (add new SQLAlchemy models + Pydantic schemas)

**Step 1: Write failing test for Style model**

Create file: `backend/tests/test_recipe_models.py`

```python
"""Tests for recipe and batch models."""

import pytest
import pytest_asyncio
from sqlalchemy import select

from backend.models import Style


@pytest.mark.asyncio
async def test_style_model_exists(test_db):
    """Style model should exist and be queryable."""
    result = await test_db.execute(select(Style))
    styles = result.scalars().all()
    assert styles == []  # Empty but table exists
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_recipe_models.py::test_style_model_exists -v`

Expected: FAIL with "cannot import name 'Style' from 'backend.models'"

**Step 3: Add Style SQLAlchemy model to models.py**

Add after `class Config(Base):` in `backend/models.py`:

```python
class Style(Base):
    """BJCP Style Guidelines reference data."""
    __tablename__ = "styles"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # e.g., "bjcp-2021-18b"
    guide: Mapped[str] = mapped_column(String(50), nullable=False)  # "BJCP 2021"
    category_number: Mapped[str] = mapped_column(String(10), nullable=False)  # "18"
    style_letter: Mapped[Optional[str]] = mapped_column(String(5))  # "B"
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # "American Pale Ale"
    category: Mapped[str] = mapped_column(String(100), nullable=False)  # "Pale American Ale"
    type: Mapped[Optional[str]] = mapped_column(String(20))  # "Ale", "Lager", etc.
    og_min: Mapped[Optional[float]] = mapped_column()
    og_max: Mapped[Optional[float]] = mapped_column()
    fg_min: Mapped[Optional[float]] = mapped_column()
    fg_max: Mapped[Optional[float]] = mapped_column()
    ibu_min: Mapped[Optional[float]] = mapped_column()
    ibu_max: Mapped[Optional[float]] = mapped_column()
    srm_min: Mapped[Optional[float]] = mapped_column()
    srm_max: Mapped[Optional[float]] = mapped_column()
    abv_min: Mapped[Optional[float]] = mapped_column()
    abv_max: Mapped[Optional[float]] = mapped_column()
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    # Relationships
    recipes: Mapped[list["Recipe"]] = relationship(back_populates="style")
```

**Step 4: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_recipe_models.py::test_style_model_exists -v`

Expected: PASS

**Step 5: Write failing test for Recipe model**

Add to `backend/tests/test_recipe_models.py`:

```python
from backend.models import Style, Recipe


@pytest.mark.asyncio
async def test_recipe_model_exists(test_db):
    """Recipe model should exist and be queryable."""
    result = await test_db.execute(select(Recipe))
    recipes = result.scalars().all()
    assert recipes == []
```

**Step 6: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_recipe_models.py::test_recipe_model_exists -v`

Expected: FAIL with "cannot import name 'Recipe' from 'backend.models'"

**Step 7: Add Recipe SQLAlchemy model to models.py**

Add after `class Style(Base):` in `backend/models.py`:

```python
class Recipe(Base):
    """Recipes imported from BeerXML or created manually."""
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(100))
    style_id: Mapped[Optional[str]] = mapped_column(ForeignKey("styles.id"))
    type: Mapped[Optional[str]] = mapped_column(String(50))  # "All Grain", "Extract", etc.

    # Gravity targets
    og_target: Mapped[Optional[float]] = mapped_column()
    fg_target: Mapped[Optional[float]] = mapped_column()

    # Yeast info (extracted from BeerXML)
    yeast_name: Mapped[Optional[str]] = mapped_column(String(100))
    yeast_lab: Mapped[Optional[str]] = mapped_column(String(100))
    yeast_product_id: Mapped[Optional[str]] = mapped_column(String(50))
    yeast_temp_min: Mapped[Optional[float]] = mapped_column()  # Celsius
    yeast_temp_max: Mapped[Optional[float]] = mapped_column()  # Celsius
    yeast_attenuation: Mapped[Optional[float]] = mapped_column()  # Percent

    # Other targets
    ibu_target: Mapped[Optional[float]] = mapped_column()
    srm_target: Mapped[Optional[float]] = mapped_column()
    abv_target: Mapped[Optional[float]] = mapped_column()
    batch_size: Mapped[Optional[float]] = mapped_column()  # Liters

    # Raw BeerXML for future re-parsing
    beerxml_content: Mapped[Optional[str]] = mapped_column(Text)

    # Metadata
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    style: Mapped[Optional["Style"]] = relationship(back_populates="recipes")
    batches: Mapped[list["Batch"]] = relationship(back_populates="recipe")
```

**Step 8: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_recipe_models.py::test_recipe_model_exists -v`

Expected: PASS

**Step 9: Write failing test for Batch model**

Add to `backend/tests/test_recipe_models.py`:

```python
from backend.models import Style, Recipe, Batch


@pytest.mark.asyncio
async def test_batch_model_exists(test_db):
    """Batch model should exist and be queryable."""
    result = await test_db.execute(select(Batch))
    batches = result.scalars().all()
    assert batches == []
```

**Step 10: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_recipe_models.py::test_batch_model_exists -v`

Expected: FAIL with "cannot import name 'Batch' from 'backend.models'"

**Step 11: Add Batch SQLAlchemy model to models.py**

Add after `class Recipe(Base):` in `backend/models.py`:

```python
class Batch(Base):
    """Instances of brewing a recipe on a device."""
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[Optional[int]] = mapped_column(ForeignKey("recipes.id"))
    device_id: Mapped[Optional[str]] = mapped_column(ForeignKey("devices.id"))

    # Batch identification
    batch_number: Mapped[Optional[int]] = mapped_column()
    name: Mapped[Optional[str]] = mapped_column(String(200))  # Optional override

    # Status tracking
    status: Mapped[str] = mapped_column(String(20), default="planning")  # planning, fermenting, conditioning, completed, archived

    # Timeline
    brew_date: Mapped[Optional[datetime]] = mapped_column()
    start_time: Mapped[Optional[datetime]] = mapped_column()  # Fermentation start
    end_time: Mapped[Optional[datetime]] = mapped_column()  # Fermentation end

    # Measured values
    measured_og: Mapped[Optional[float]] = mapped_column()
    measured_fg: Mapped[Optional[float]] = mapped_column()
    measured_abv: Mapped[Optional[float]] = mapped_column()
    measured_attenuation: Mapped[Optional[float]] = mapped_column()

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    recipe: Mapped[Optional["Recipe"]] = relationship(back_populates="batches")
    device: Mapped[Optional["Device"]] = relationship()
    readings: Mapped[list["Reading"]] = relationship(back_populates="batch")
```

**Step 12: Add batch_id FK to Reading model**

In `backend/models.py`, modify the `Reading` class to add:

```python
# Add this field after device_id line
batch_id: Mapped[Optional[int]] = mapped_column(ForeignKey("batches.id"), nullable=True, index=True)

# Add this relationship after the device relationship
batch: Mapped[Optional["Batch"]] = relationship(back_populates="readings")
```

Also add to `__table_args__`:
```python
Index("ix_readings_batch_timestamp", "batch_id", "timestamp"),
```

**Step 13: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_recipe_models.py::test_batch_model_exists -v`

Expected: PASS

**Step 14: Write test for Reading-Batch relationship**

Add to `backend/tests/test_recipe_models.py`:

```python
@pytest.mark.asyncio
async def test_reading_batch_relationship(test_db):
    """Reading should have optional batch_id foreign key."""
    from backend.models import Reading

    # Create a reading without batch_id
    reading = Reading(
        tilt_id=None,
        sg_raw=1.050,
        temp_raw=68.0,
        batch_id=None  # Should be allowed
    )
    test_db.add(reading)
    await test_db.commit()

    # Verify reading was created
    result = await test_db.execute(select(Reading).where(Reading.id == reading.id))
    saved_reading = result.scalar_one()
    assert saved_reading.batch_id is None
```

**Step 15: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_recipe_models.py::test_reading_batch_relationship -v`

Expected: PASS

**Step 16: Commit**

```bash
git add backend/models.py backend/tests/test_recipe_models.py
git commit -m "feat: add Style, Recipe, Batch models with Reading FK

- Style: BJCP reference data (og/fg/ibu/srm/abv ranges)
- Recipe: BeerXML import target (yeast temps, gravity targets)
- Batch: Links recipe to device with status workflow
- Reading.batch_id: Optional FK for tracking readings per batch

Part of #22"
```

---

## Task 2: Database Migration for Existing Installations

**Files:**
- Modify: `backend/database.py` (add migration for batch_id column)

**Step 1: Write failing test for migration**

Add to `backend/tests/test_recipe_models.py`:

```python
@pytest.mark.asyncio
async def test_batch_id_column_in_readings(test_db):
    """Readings table should have batch_id column after migration."""
    from sqlalchemy import text

    # Get column names from readings table
    result = await test_db.execute(text("PRAGMA table_info(readings)"))
    columns = [row[1] for row in result.fetchall()]

    assert "batch_id" in columns
```

**Step 2: Run test to verify it passes (should pass already from model definition)**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_recipe_models.py::test_batch_id_column_in_readings -v`

Expected: PASS (test_db creates tables from models)

**Step 3: Add migration function for existing databases**

In `backend/database.py`, add new migration function before `async def init_db()`:

```python
def _migrate_add_batch_id_to_readings(conn):
    """Add batch_id column to readings table if not present."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "readings" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("readings")]
    if "batch_id" not in columns:
        conn.execute(text("ALTER TABLE readings ADD COLUMN batch_id INTEGER REFERENCES batches(id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_batch_id ON readings(batch_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_batch_timestamp ON readings(batch_id, timestamp)"))
        print("Migration: Added batch_id column to readings table")
```

**Step 4: Add migration call to init_db()**

In `backend/database.py`, modify `init_db()` to call the new migration:

```python
async def init_db():
    """Initialize database with migrations."""
    async with engine.begin() as conn:
        # Step 1: Schema migrations for existing DBs
        await conn.run_sync(_migrate_add_original_gravity)
        await conn.run_sync(_migrate_create_devices_table)
        await conn.run_sync(_migrate_add_reading_columns)
        await conn.run_sync(_migrate_readings_nullable_tilt_id)
        await conn.run_sync(_migrate_add_batch_id_to_readings)  # Add this line

        # Step 2: Create any missing tables
        await conn.run_sync(Base.metadata.create_all)

        # Step 3: Data migrations
        await conn.run_sync(_migrate_tilts_to_devices)
```

**Step 5: Run all model tests**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_recipe_models.py -v`

Expected: All PASS

**Step 6: Commit**

```bash
git add backend/database.py
git commit -m "feat: add migration for batch_id column in readings

Existing databases will have batch_id column added automatically
on startup via init_db() migration chain.

Part of #22"
```

---

## Task 3: Add Pydantic Schemas for API

**Files:**
- Modify: `backend/models.py` (add Pydantic schemas at bottom)

**Step 1: Write failing test for StyleResponse schema**

Add to `backend/tests/test_recipe_models.py`:

```python
def test_style_response_schema():
    """StyleResponse schema should serialize Style model."""
    from backend.models import StyleResponse

    style_data = {
        "id": "bjcp-2021-18b",
        "guide": "BJCP 2021",
        "category_number": "18",
        "style_letter": "B",
        "name": "American Pale Ale",
        "category": "Pale American Ale",
        "type": "Ale",
        "og_min": 1.045,
        "og_max": 1.060,
    }

    schema = StyleResponse(**style_data)
    assert schema.id == "bjcp-2021-18b"
    assert schema.og_min == 1.045
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_recipe_models.py::test_style_response_schema -v`

Expected: FAIL with "cannot import name 'StyleResponse'"

**Step 3: Add Pydantic schemas to models.py**

Add at the bottom of `backend/models.py`:

```python
# Recipe & Batch Pydantic Schemas
class StyleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    guide: str
    category_number: str
    style_letter: Optional[str]
    name: str
    category: str
    type: Optional[str]
    og_min: Optional[float]
    og_max: Optional[float]
    fg_min: Optional[float]
    fg_max: Optional[float]
    ibu_min: Optional[float]
    ibu_max: Optional[float]
    srm_min: Optional[float]
    srm_max: Optional[float]
    abv_min: Optional[float]
    abv_max: Optional[float]
    description: Optional[str]


class RecipeCreate(BaseModel):
    name: str
    author: Optional[str] = None
    style_id: Optional[str] = None
    type: Optional[str] = None
    og_target: Optional[float] = None
    fg_target: Optional[float] = None
    yeast_name: Optional[str] = None
    yeast_temp_min: Optional[float] = None
    yeast_temp_max: Optional[float] = None
    yeast_attenuation: Optional[float] = None
    ibu_target: Optional[float] = None
    abv_target: Optional[float] = None
    batch_size: Optional[float] = None
    notes: Optional[str] = None


class RecipeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    author: Optional[str]
    style_id: Optional[str]
    type: Optional[str]
    og_target: Optional[float]
    fg_target: Optional[float]
    yeast_name: Optional[str]
    yeast_lab: Optional[str]
    yeast_product_id: Optional[str]
    yeast_temp_min: Optional[float]
    yeast_temp_max: Optional[float]
    yeast_attenuation: Optional[float]
    ibu_target: Optional[float]
    srm_target: Optional[float]
    abv_target: Optional[float]
    batch_size: Optional[float]
    notes: Optional[str]
    created_at: datetime
    style: Optional[StyleResponse] = None


class BatchCreate(BaseModel):
    recipe_id: Optional[int] = None
    device_id: Optional[str] = None
    name: Optional[str] = None
    status: str = "planning"
    brew_date: Optional[datetime] = None
    measured_og: Optional[float] = None
    notes: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        valid = ["planning", "fermenting", "conditioning", "completed", "archived"]
        if v not in valid:
            raise ValueError(f"status must be one of: {', '.join(valid)}")
        return v


class BatchUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    device_id: Optional[str] = None
    brew_date: Optional[datetime] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    measured_og: Optional[float] = None
    measured_fg: Optional[float] = None
    notes: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        valid = ["planning", "fermenting", "conditioning", "completed", "archived"]
        if v not in valid:
            raise ValueError(f"status must be one of: {', '.join(valid)}")
        return v


class BatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    recipe_id: Optional[int]
    device_id: Optional[str]
    batch_number: Optional[int]
    name: Optional[str]
    status: str
    brew_date: Optional[datetime]
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    measured_og: Optional[float]
    measured_fg: Optional[float]
    measured_abv: Optional[float]
    measured_attenuation: Optional[float]
    notes: Optional[str]
    created_at: datetime
    recipe: Optional[RecipeResponse] = None


class BatchProgressResponse(BaseModel):
    """Fermentation progress response."""
    batch_id: int
    recipe_name: Optional[str]
    status: str
    targets: dict  # og, fg, attenuation, abv
    measured: dict  # og, current_sg, attenuation, abv
    progress: dict  # percent_complete, sg_remaining, estimated_days_remaining
    temperature: dict  # current, yeast_min, yeast_max, status
```

**Step 4: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_recipe_models.py::test_style_response_schema -v`

Expected: PASS

**Step 5: Write tests for other schemas**

Add to `backend/tests/test_recipe_models.py`:

```python
def test_recipe_response_schema():
    """RecipeResponse schema should serialize Recipe model."""
    from backend.models import RecipeResponse

    recipe_data = {
        "id": 1,
        "name": "Test IPA",
        "author": "Brewer",
        "style_id": None,
        "type": "All Grain",
        "og_target": 1.065,
        "fg_target": 1.012,
        "yeast_name": "US-05",
        "yeast_lab": "Fermentis",
        "yeast_product_id": "US-05",
        "yeast_temp_min": 15.0,
        "yeast_temp_max": 22.0,
        "yeast_attenuation": 77.0,
        "ibu_target": 60.0,
        "srm_target": 8.0,
        "abv_target": 7.0,
        "batch_size": 19.0,
        "notes": None,
        "created_at": "2025-11-30T00:00:00Z",
    }

    schema = RecipeResponse(**recipe_data)
    assert schema.name == "Test IPA"
    assert schema.yeast_temp_min == 15.0


def test_batch_create_validates_status():
    """BatchCreate should validate status values."""
    from backend.models import BatchCreate
    import pytest

    # Valid status
    batch = BatchCreate(status="fermenting")
    assert batch.status == "fermenting"

    # Invalid status
    with pytest.raises(ValueError, match="status must be one of"):
        BatchCreate(status="invalid")


def test_batch_response_schema():
    """BatchResponse schema should serialize Batch model."""
    from backend.models import BatchResponse

    batch_data = {
        "id": 1,
        "recipe_id": 1,
        "device_id": "tilt-red",
        "batch_number": 12,
        "name": "Batch 12",
        "status": "fermenting",
        "brew_date": "2025-11-30T00:00:00Z",
        "start_time": "2025-11-30T12:00:00Z",
        "end_time": None,
        "measured_og": 1.048,
        "measured_fg": None,
        "measured_abv": None,
        "measured_attenuation": None,
        "notes": "Test batch",
        "created_at": "2025-11-30T00:00:00Z",
    }

    schema = BatchResponse(**batch_data)
    assert schema.status == "fermenting"
    assert schema.measured_og == 1.048
```

**Step 6: Run all schema tests**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_recipe_models.py -v`

Expected: All PASS

**Step 7: Commit**

```bash
git add backend/models.py backend/tests/test_recipe_models.py
git commit -m "feat: add Pydantic schemas for Style, Recipe, Batch

- StyleResponse, RecipeResponse, BatchResponse for API output
- RecipeCreate, BatchCreate, BatchUpdate for API input
- BatchProgressResponse for fermentation progress endpoint
- Status validation for batch lifecycle states

Part of #22"
```

---

## Task 4: BeerXML Parser Service

**Files:**
- Create: `backend/services/beerxml_parser.py`
- Create: `backend/tests/test_beerxml_parser.py`

**Step 1: Write failing test for parser**

Create file: `backend/tests/test_beerxml_parser.py`

```python
"""Tests for BeerXML parser service."""

import pytest


SAMPLE_BEERXML = """<?xml version="1.0" encoding="UTF-8"?>
<RECIPES>
  <RECIPE>
    <NAME>Test IPA</NAME>
    <TYPE>All Grain</TYPE>
    <BREWER>Test Brewer</BREWER>
    <BATCH_SIZE>19.0</BATCH_SIZE>
    <OG>1.065</OG>
    <FG>1.012</FG>
    <IBU>60.0</IBU>
    <EST_ABV>7.0</EST_ABV>
    <STYLE>
      <NAME>American IPA</NAME>
      <CATEGORY>IPA</CATEGORY>
      <CATEGORY_NUMBER>21</CATEGORY_NUMBER>
      <STYLE_LETTER>A</STYLE_LETTER>
      <STYLE_GUIDE>BJCP 2021</STYLE_GUIDE>
    </STYLE>
    <YEASTS>
      <YEAST>
        <NAME>Safale US-05</NAME>
        <LABORATORY>Fermentis</LABORATORY>
        <PRODUCT_ID>US-05</PRODUCT_ID>
        <MIN_TEMPERATURE>15.0</MIN_TEMPERATURE>
        <MAX_TEMPERATURE>22.0</MAX_TEMPERATURE>
        <ATTENUATION>77.0</ATTENUATION>
      </YEAST>
    </YEASTS>
  </RECIPE>
</RECIPES>
"""


def test_parse_beerxml_extracts_recipe_name():
    """Parser should extract recipe name from BeerXML."""
    from backend.services.beerxml_parser import parse_beerxml

    recipes = parse_beerxml(SAMPLE_BEERXML)

    assert len(recipes) == 1
    assert recipes[0].name == "Test IPA"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_beerxml_parser.py::test_parse_beerxml_extracts_recipe_name -v`

Expected: FAIL with "No module named 'backend.services.beerxml_parser'"

**Step 3: Create parser service**

Create file: `backend/services/beerxml_parser.py`

```python
"""BeerXML 1.0 parser service.

Parses BeerXML files and extracts fermentation-relevant data:
- Recipe name, author, type
- OG/FG targets
- Yeast name, temp range, attenuation
- Style information
"""

from dataclasses import dataclass, field
from typing import Optional

import defusedxml.ElementTree as ET


@dataclass
class ParsedYeast:
    """Yeast data extracted from BeerXML."""
    name: Optional[str] = None
    lab: Optional[str] = None
    product_id: Optional[str] = None
    temp_min: Optional[float] = None  # Celsius
    temp_max: Optional[float] = None  # Celsius
    attenuation: Optional[float] = None


@dataclass
class ParsedStyle:
    """Style data extracted from BeerXML."""
    name: Optional[str] = None
    category: Optional[str] = None
    category_number: Optional[str] = None
    style_letter: Optional[str] = None
    guide: Optional[str] = None


@dataclass
class ParsedRecipe:
    """Recipe data extracted from BeerXML."""
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
    """Parse BeerXML content and return list of recipes.

    Args:
        xml_content: BeerXML 1.0 formatted XML string

    Returns:
        List of ParsedRecipe dataclasses with extracted data

    Raises:
        ET.ParseError: If XML is malformed
    """
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
        srm=_get_float(elem, 'EST_COLOR'),
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

**Step 4: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_beerxml_parser.py::test_parse_beerxml_extracts_recipe_name -v`

Expected: PASS

**Step 5: Add more parser tests**

Add to `backend/tests/test_beerxml_parser.py`:

```python
def test_parse_beerxml_extracts_gravity_targets():
    """Parser should extract OG and FG targets."""
    from backend.services.beerxml_parser import parse_beerxml

    recipes = parse_beerxml(SAMPLE_BEERXML)

    assert recipes[0].og == 1.065
    assert recipes[0].fg == 1.012


def test_parse_beerxml_extracts_yeast_data():
    """Parser should extract yeast name and temp range."""
    from backend.services.beerxml_parser import parse_beerxml

    recipes = parse_beerxml(SAMPLE_BEERXML)

    yeast = recipes[0].yeast
    assert yeast is not None
    assert yeast.name == "Safale US-05"
    assert yeast.lab == "Fermentis"
    assert yeast.temp_min == 15.0
    assert yeast.temp_max == 22.0
    assert yeast.attenuation == 77.0


def test_parse_beerxml_extracts_style():
    """Parser should extract style information."""
    from backend.services.beerxml_parser import parse_beerxml

    recipes = parse_beerxml(SAMPLE_BEERXML)

    style = recipes[0].style
    assert style is not None
    assert style.name == "American IPA"
    assert style.category_number == "21"
    assert style.style_letter == "A"
    assert style.guide == "BJCP 2021"


def test_parse_beerxml_handles_missing_fields():
    """Parser should handle missing optional fields gracefully."""
    from backend.services.beerxml_parser import parse_beerxml

    minimal_xml = """<?xml version="1.0"?>
    <RECIPES>
      <RECIPE>
        <NAME>Minimal Recipe</NAME>
      </RECIPE>
    </RECIPES>
    """

    recipes = parse_beerxml(minimal_xml)

    assert len(recipes) == 1
    assert recipes[0].name == "Minimal Recipe"
    assert recipes[0].og is None
    assert recipes[0].yeast is None
    assert recipes[0].style is None


def test_parse_beerxml_handles_multiple_recipes():
    """Parser should handle files with multiple recipes."""
    from backend.services.beerxml_parser import parse_beerxml

    multi_xml = """<?xml version="1.0"?>
    <RECIPES>
      <RECIPE><NAME>Recipe One</NAME></RECIPE>
      <RECIPE><NAME>Recipe Two</NAME></RECIPE>
    </RECIPES>
    """

    recipes = parse_beerxml(multi_xml)

    assert len(recipes) == 2
    assert recipes[0].name == "Recipe One"
    assert recipes[1].name == "Recipe Two"


def test_parse_beerxml_rejects_malformed_xml():
    """Parser should raise error for malformed XML."""
    from backend.services.beerxml_parser import parse_beerxml
    import defusedxml.ElementTree as ET

    with pytest.raises(ET.ParseError):
        parse_beerxml("<invalid><xml>")
```

**Step 6: Run all parser tests**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_beerxml_parser.py -v`

Expected: All PASS

**Step 7: Commit**

```bash
git add backend/services/beerxml_parser.py backend/tests/test_beerxml_parser.py
git commit -m "feat: add BeerXML 1.0 parser service

Extracts fermentation-relevant data from BeerXML:
- Recipe name, author, type, batch size
- OG/FG/IBU/SRM/ABV targets
- Yeast name, lab, temp range, attenuation
- Style name, category, guide

Uses defusedxml for security against XXE attacks.

Part of #22"
```

---

## Task 5: Recipe API Endpoints

**Files:**
- Create: `backend/routers/recipes.py`
- Create: `backend/tests/test_recipes_api.py`
- Modify: `backend/main.py` (register router)

**Step 1: Write failing test for list recipes endpoint**

Create file: `backend/tests/test_recipes_api.py`

```python
"""Tests for recipes API endpoints."""

import pytest


@pytest.mark.asyncio
async def test_list_recipes_empty(client):
    """GET /api/recipes should return empty list when no recipes exist."""
    response = await client.get("/api/recipes")

    assert response.status_code == 200
    assert response.json() == []
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_recipes_api.py::test_list_recipes_empty -v`

Expected: FAIL with 404 (route not found)

**Step 3: Create recipes router**

Create file: `backend/routers/recipes.py`

```python
"""Recipe API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models import Recipe, RecipeCreate, RecipeResponse
from ..services.beerxml_parser import parse_beerxml

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


@router.get("", response_model=list[RecipeResponse])
async def list_recipes(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List all recipes."""
    query = (
        select(Recipe)
        .options(selectinload(Recipe.style))
        .order_by(Recipe.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{recipe_id}", response_model=RecipeResponse)
async def get_recipe(recipe_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific recipe by ID."""
    query = (
        select(Recipe)
        .options(selectinload(Recipe.style))
        .where(Recipe.id == recipe_id)
    )
    result = await db.execute(query)
    recipe = result.scalar_one_or_none()

    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@router.post("", response_model=RecipeResponse, status_code=201)
async def create_recipe(
    recipe: RecipeCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new recipe manually."""
    db_recipe = Recipe(
        name=recipe.name,
        author=recipe.author,
        style_id=recipe.style_id,
        type=recipe.type,
        og_target=recipe.og_target,
        fg_target=recipe.fg_target,
        yeast_name=recipe.yeast_name,
        yeast_temp_min=recipe.yeast_temp_min,
        yeast_temp_max=recipe.yeast_temp_max,
        yeast_attenuation=recipe.yeast_attenuation,
        ibu_target=recipe.ibu_target,
        abv_target=recipe.abv_target,
        batch_size=recipe.batch_size,
        notes=recipe.notes,
    )
    db.add(db_recipe)
    await db.commit()
    await db.refresh(db_recipe)
    return db_recipe


@router.post("/import", response_model=list[RecipeResponse])
async def import_beerxml(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Import recipes from a BeerXML file."""
    # Validate file size (1MB max)
    content = await file.read()
    if len(content) > 1_000_000:
        raise HTTPException(status_code=400, detail="File too large (max 1MB)")

    # Validate content type
    if file.content_type and file.content_type not in ["text/xml", "application/xml"]:
        # Allow if no content type (some clients don't send it)
        if file.content_type != "application/octet-stream":
            raise HTTPException(status_code=400, detail="File must be XML")

    # Parse BeerXML
    try:
        xml_content = content.decode("utf-8")
        parsed_recipes = parse_beerxml(xml_content)
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid BeerXML: {str(e)}")

    if not parsed_recipes:
        raise HTTPException(status_code=400, detail="No recipes found in file")

    # Create Recipe models
    created_recipes = []
    for parsed in parsed_recipes:
        recipe = Recipe(
            name=parsed.name,
            author=parsed.author,
            type=parsed.type,
            og_target=parsed.og,
            fg_target=parsed.fg,
            ibu_target=parsed.ibu,
            srm_target=parsed.srm,
            abv_target=parsed.abv,
            batch_size=parsed.batch_size,
            beerxml_content=parsed.raw_xml,
        )

        # Add yeast data
        if parsed.yeast:
            recipe.yeast_name = parsed.yeast.name
            recipe.yeast_lab = parsed.yeast.lab
            recipe.yeast_product_id = parsed.yeast.product_id
            recipe.yeast_temp_min = parsed.yeast.temp_min
            recipe.yeast_temp_max = parsed.yeast.temp_max
            recipe.yeast_attenuation = parsed.yeast.attenuation

        db.add(recipe)
        created_recipes.append(recipe)

    await db.commit()

    # Refresh all to get IDs
    for recipe in created_recipes:
        await db.refresh(recipe)

    return created_recipes


@router.delete("/{recipe_id}")
async def delete_recipe(recipe_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a recipe."""
    recipe = await db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    await db.delete(recipe)
    await db.commit()
    return {"status": "deleted"}
```

**Step 4: Register router in main.py**

In `backend/main.py`, add import and include:

```python
from .routers import recipes  # Add to imports

app.include_router(recipes.router)  # Add after other routers
```

**Step 5: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_recipes_api.py::test_list_recipes_empty -v`

Expected: PASS

**Step 6: Add more API tests**

Add to `backend/tests/test_recipes_api.py`:

```python
@pytest.mark.asyncio
async def test_create_recipe(client):
    """POST /api/recipes should create a new recipe."""
    recipe_data = {
        "name": "Test Recipe",
        "author": "Tester",
        "og_target": 1.050,
        "fg_target": 1.010,
        "yeast_name": "US-05",
        "yeast_temp_min": 15.0,
        "yeast_temp_max": 22.0,
    }

    response = await client.post("/api/recipes", json=recipe_data)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Recipe"
    assert data["og_target"] == 1.050
    assert data["yeast_temp_min"] == 15.0
    assert "id" in data


@pytest.mark.asyncio
async def test_get_recipe(client):
    """GET /api/recipes/{id} should return specific recipe."""
    # Create recipe first
    recipe_data = {"name": "Get Test Recipe"}
    create_response = await client.post("/api/recipes", json=recipe_data)
    recipe_id = create_response.json()["id"]

    # Get it
    response = await client.get(f"/api/recipes/{recipe_id}")

    assert response.status_code == 200
    assert response.json()["name"] == "Get Test Recipe"


@pytest.mark.asyncio
async def test_get_recipe_not_found(client):
    """GET /api/recipes/{id} should return 404 for non-existent recipe."""
    response = await client.get("/api/recipes/99999")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_import_beerxml(client):
    """POST /api/recipes/import should import BeerXML file."""
    beerxml = """<?xml version="1.0"?>
    <RECIPES>
      <RECIPE>
        <NAME>Imported IPA</NAME>
        <OG>1.065</OG>
        <FG>1.012</FG>
        <YEASTS>
          <YEAST>
            <NAME>US-05</NAME>
            <MIN_TEMPERATURE>15.0</MIN_TEMPERATURE>
            <MAX_TEMPERATURE>22.0</MAX_TEMPERATURE>
          </YEAST>
        </YEASTS>
      </RECIPE>
    </RECIPES>
    """

    response = await client.post(
        "/api/recipes/import",
        files={"file": ("recipe.xml", beerxml, "text/xml")},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Imported IPA"
    assert data[0]["og_target"] == 1.065
    assert data[0]["yeast_name"] == "US-05"


@pytest.mark.asyncio
async def test_delete_recipe(client):
    """DELETE /api/recipes/{id} should remove recipe."""
    # Create recipe first
    create_response = await client.post("/api/recipes", json={"name": "Delete Me"})
    recipe_id = create_response.json()["id"]

    # Delete it
    response = await client.delete(f"/api/recipes/{recipe_id}")
    assert response.status_code == 200

    # Verify deleted
    get_response = await client.get(f"/api/recipes/{recipe_id}")
    assert get_response.status_code == 404
```

**Step 7: Run all API tests**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_recipes_api.py -v`

Expected: All PASS

**Step 8: Commit**

```bash
git add backend/routers/recipes.py backend/tests/test_recipes_api.py backend/main.py
git commit -m "feat: add recipe API endpoints

- GET /api/recipes - list all recipes
- POST /api/recipes - create recipe manually
- GET /api/recipes/{id} - get specific recipe
- POST /api/recipes/import - import from BeerXML file
- DELETE /api/recipes/{id} - delete recipe

Includes file size validation (1MB max) and XML parsing.

Part of #22"
```

---

## Task 6: Batch API Endpoints

**Files:**
- Create: `backend/routers/batches.py`
- Create: `backend/tests/test_batches_api.py`
- Modify: `backend/main.py` (register router)

**Step 1: Write failing test for list batches endpoint**

Create file: `backend/tests/test_batches_api.py`

```python
"""Tests for batches API endpoints."""

import pytest


@pytest.mark.asyncio
async def test_list_batches_empty(client):
    """GET /api/batches should return empty list when no batches exist."""
    response = await client.get("/api/batches")

    assert response.status_code == 200
    assert response.json() == []
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_batches_api.py::test_list_batches_empty -v`

Expected: FAIL with 404

**Step 3: Create batches router**

Create file: `backend/routers/batches.py`

```python
"""Batch API endpoints."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models import (
    Batch,
    BatchCreate,
    BatchProgressResponse,
    BatchResponse,
    BatchUpdate,
    Reading,
    Recipe,
)
from ..state import latest_readings

router = APIRouter(prefix="/api/batches", tags=["batches"])


@router.get("", response_model=list[BatchResponse])
async def list_batches(
    status: Optional[str] = Query(None, description="Filter by status"),
    device_id: Optional[str] = Query(None, description="Filter by device"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List batches with optional filters."""
    query = (
        select(Batch)
        .options(selectinload(Batch.recipe))
        .order_by(Batch.created_at.desc())
    )

    if status:
        query = query.where(Batch.status == status)
    if device_id:
        query = query.where(Batch.device_id == device_id)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{batch_id}", response_model=BatchResponse)
async def get_batch(batch_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific batch by ID."""
    query = (
        select(Batch)
        .options(selectinload(Batch.recipe).selectinload(Recipe.style))
        .where(Batch.id == batch_id)
    )
    result = await db.execute(query)
    batch = result.scalar_one_or_none()

    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@router.post("", response_model=BatchResponse, status_code=201)
async def create_batch(
    batch: BatchCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new batch."""
    # Get next batch number
    result = await db.execute(select(func.max(Batch.batch_number)))
    max_num = result.scalar() or 0

    # Get recipe name for batch name default
    batch_name = batch.name
    if batch.recipe_id and not batch_name:
        recipe = await db.get(Recipe, batch.recipe_id)
        if recipe:
            batch_name = recipe.name

    db_batch = Batch(
        recipe_id=batch.recipe_id,
        device_id=batch.device_id,
        batch_number=max_num + 1,
        name=batch_name,
        status=batch.status,
        brew_date=batch.brew_date,
        measured_og=batch.measured_og,
        notes=batch.notes,
    )

    # Auto-set start_time if status is fermenting
    if batch.status == "fermenting":
        db_batch.start_time = datetime.now(timezone.utc)

    db.add(db_batch)
    await db.commit()
    await db.refresh(db_batch)

    # Load recipe relationship for response
    if db_batch.recipe_id:
        await db.refresh(db_batch, ["recipe"])

    return db_batch


@router.put("/{batch_id}", response_model=BatchResponse)
async def update_batch(
    batch_id: int,
    update: BatchUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a batch."""
    batch = await db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Update fields if provided
    if update.name is not None:
        batch.name = update.name
    if update.status is not None:
        old_status = batch.status
        batch.status = update.status
        # Auto-set timestamps on status change
        if update.status == "fermenting" and old_status != "fermenting":
            batch.start_time = datetime.now(timezone.utc)
        elif update.status in ["conditioning", "completed"] and old_status == "fermenting":
            batch.end_time = datetime.now(timezone.utc)
    if update.device_id is not None:
        batch.device_id = update.device_id
    if update.brew_date is not None:
        batch.brew_date = update.brew_date
    if update.start_time is not None:
        batch.start_time = update.start_time
    if update.end_time is not None:
        batch.end_time = update.end_time
    if update.measured_og is not None:
        batch.measured_og = update.measured_og
    if update.measured_fg is not None:
        batch.measured_fg = update.measured_fg
        # Calculate ABV and attenuation when FG is set
        if batch.measured_og:
            batch.measured_abv = (batch.measured_og - update.measured_fg) * 131.25
            batch.measured_attenuation = ((batch.measured_og - update.measured_fg) / (batch.measured_og - 1.0)) * 100
    if update.notes is not None:
        batch.notes = update.notes

    await db.commit()
    await db.refresh(batch)

    # Load recipe relationship for response
    if batch.recipe_id:
        await db.refresh(batch, ["recipe"])

    return batch


@router.delete("/{batch_id}")
async def delete_batch(batch_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a batch."""
    batch = await db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    await db.delete(batch)
    await db.commit()
    return {"status": "deleted"}


@router.get("/{batch_id}/progress", response_model=BatchProgressResponse)
async def get_batch_progress(batch_id: int, db: AsyncSession = Depends(get_db)):
    """Get fermentation progress for a batch."""
    # Get batch with recipe
    query = (
        select(Batch)
        .options(selectinload(Batch.recipe))
        .where(Batch.id == batch_id)
    )
    result = await db.execute(query)
    batch = result.scalar_one_or_none()

    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Get current SG from latest reading
    current_sg = None
    current_temp = None
    if batch.device_id and batch.device_id in latest_readings:
        reading = latest_readings[batch.device_id]
        current_sg = reading.get("sg")
        current_temp = reading.get("temp")

    # Calculate targets from recipe
    targets = {}
    if batch.recipe:
        targets = {
            "og": batch.recipe.og_target,
            "fg": batch.recipe.fg_target,
            "attenuation": None,
            "abv": batch.recipe.abv_target,
        }
        if batch.recipe.og_target and batch.recipe.fg_target:
            targets["attenuation"] = round(
                ((batch.recipe.og_target - batch.recipe.fg_target) / (batch.recipe.og_target - 1.0)) * 100, 1
            )

    # Calculate measured values
    measured = {
        "og": batch.measured_og,
        "current_sg": current_sg,
        "attenuation": None,
        "abv": None,
    }
    if batch.measured_og and current_sg:
        measured["attenuation"] = round(
            ((batch.measured_og - current_sg) / (batch.measured_og - 1.0)) * 100, 1
        )
        measured["abv"] = round((batch.measured_og - current_sg) * 131.25, 1)

    # Calculate progress
    progress = {
        "percent_complete": None,
        "sg_remaining": None,
        "estimated_days_remaining": None,
    }
    og = batch.measured_og or (targets.get("og") if targets else None)
    fg = targets.get("fg") if targets else None
    if og and fg and current_sg:
        total_drop = og - fg
        current_drop = og - current_sg
        if total_drop > 0:
            progress["percent_complete"] = round(min(100, (current_drop / total_drop) * 100), 1)
            progress["sg_remaining"] = round(current_sg - fg, 4)

    # Temperature status
    temperature = {
        "current": current_temp,
        "yeast_min": batch.recipe.yeast_temp_min if batch.recipe else None,
        "yeast_max": batch.recipe.yeast_temp_max if batch.recipe else None,
        "status": "unknown",
    }
    if current_temp and batch.recipe:
        ymin = batch.recipe.yeast_temp_min
        ymax = batch.recipe.yeast_temp_max
        if ymin and ymax:
            if ymin <= current_temp <= ymax:
                temperature["status"] = "in_range"
            elif current_temp < ymin:
                temperature["status"] = "too_cold"
            else:
                temperature["status"] = "too_hot"

    return BatchProgressResponse(
        batch_id=batch.id,
        recipe_name=batch.recipe.name if batch.recipe else batch.name,
        status=batch.status,
        targets=targets,
        measured=measured,
        progress=progress,
        temperature=temperature,
    )
```

**Step 4: Register router in main.py**

In `backend/main.py`, add import and include:

```python
from .routers import batches  # Add to imports

app.include_router(batches.router)  # Add after other routers
```

**Step 5: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_batches_api.py::test_list_batches_empty -v`

Expected: PASS

**Step 6: Add more API tests**

Add to `backend/tests/test_batches_api.py`:

```python
@pytest.mark.asyncio
async def test_create_batch(client):
    """POST /api/batches should create a new batch."""
    batch_data = {
        "status": "planning",
        "name": "Test Batch",
    }

    response = await client.post("/api/batches", json=batch_data)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Batch"
    assert data["status"] == "planning"
    assert data["batch_number"] == 1


@pytest.mark.asyncio
async def test_create_batch_with_recipe(client):
    """POST /api/batches should link to recipe and auto-name."""
    # Create recipe first
    recipe_response = await client.post("/api/recipes", json={"name": "IPA Recipe"})
    recipe_id = recipe_response.json()["id"]

    # Create batch linked to recipe
    batch_data = {
        "recipe_id": recipe_id,
        "status": "planning",
    }

    response = await client.post("/api/batches", json=batch_data)

    assert response.status_code == 201
    data = response.json()
    assert data["recipe_id"] == recipe_id
    assert data["name"] == "IPA Recipe"  # Auto-named from recipe


@pytest.mark.asyncio
async def test_update_batch_status(client):
    """PUT /api/batches/{id} should update status and set timestamps."""
    # Create batch
    create_response = await client.post("/api/batches", json={"name": "Update Test"})
    batch_id = create_response.json()["id"]

    # Update to fermenting
    response = await client.put(
        f"/api/batches/{batch_id}",
        json={"status": "fermenting"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "fermenting"
    assert data["start_time"] is not None  # Auto-set


@pytest.mark.asyncio
async def test_get_batch_not_found(client):
    """GET /api/batches/{id} should return 404 for non-existent batch."""
    response = await client.get("/api/batches/99999")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_batch_progress(client):
    """GET /api/batches/{id}/progress should return progress data."""
    # Create recipe with targets
    recipe_response = await client.post("/api/recipes", json={
        "name": "Progress Test",
        "og_target": 1.050,
        "fg_target": 1.010,
        "yeast_temp_min": 18.0,
        "yeast_temp_max": 22.0,
    })
    recipe_id = recipe_response.json()["id"]

    # Create batch
    batch_response = await client.post("/api/batches", json={
        "recipe_id": recipe_id,
        "status": "fermenting",
        "measured_og": 1.052,
    })
    batch_id = batch_response.json()["id"]

    # Get progress
    response = await client.get(f"/api/batches/{batch_id}/progress")

    assert response.status_code == 200
    data = response.json()
    assert data["batch_id"] == batch_id
    assert data["recipe_name"] == "Progress Test"
    assert data["targets"]["og"] == 1.050
    assert data["targets"]["fg"] == 1.010
    assert data["measured"]["og"] == 1.052
```

**Step 7: Run all API tests**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_batches_api.py -v`

Expected: All PASS

**Step 8: Commit**

```bash
git add backend/routers/batches.py backend/tests/test_batches_api.py backend/main.py
git commit -m "feat: add batch API endpoints

- GET /api/batches - list batches (filter by status, device)
- POST /api/batches - create batch (auto batch number, auto name)
- GET /api/batches/{id} - get specific batch
- PUT /api/batches/{id} - update batch (auto timestamps on status)
- DELETE /api/batches/{id} - delete batch
- GET /api/batches/{id}/progress - fermentation progress vs targets

Auto-calculates ABV and attenuation when measured_fg is set.

Part of #22"
```

---

## Task 7: Auto-link Readings to Active Batches

**Files:**
- Modify: `backend/scanner.py` (or wherever readings are created)
- Create: `backend/services/batch_linker.py`
- Create: `backend/tests/test_batch_linker.py`

**Step 1: Write failing test for batch linker**

Create file: `backend/tests/test_batch_linker.py`

```python
"""Tests for batch reading linker service."""

import pytest
from datetime import datetime, timezone

from backend.models import Batch, Device, Reading


@pytest.mark.asyncio
async def test_get_active_batch_for_device(test_db):
    """Should find active batch for device."""
    from backend.services.batch_linker import get_active_batch_for_device

    # Create device
    device = Device(id="tilt-red", device_type="tilt", name="Red")
    test_db.add(device)

    # Create active batch
    batch = Batch(
        device_id="tilt-red",
        status="fermenting",
        start_time=datetime.now(timezone.utc),
    )
    test_db.add(batch)
    await test_db.commit()

    # Find active batch
    active_batch = await get_active_batch_for_device(test_db, "tilt-red")

    assert active_batch is not None
    assert active_batch.id == batch.id


@pytest.mark.asyncio
async def test_no_active_batch_for_device(test_db):
    """Should return None when no active batch exists."""
    from backend.services.batch_linker import get_active_batch_for_device

    # Create device with no batches
    device = Device(id="tilt-blue", device_type="tilt", name="Blue")
    test_db.add(device)
    await test_db.commit()

    # Should return None
    active_batch = await get_active_batch_for_device(test_db, "tilt-blue")

    assert active_batch is None
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_batch_linker.py -v`

Expected: FAIL with "No module named 'backend.services.batch_linker'"

**Step 3: Create batch linker service**

Create file: `backend/services/batch_linker.py`

```python
"""Service for linking readings to active batches."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Batch


async def get_active_batch_for_device(
    db: AsyncSession,
    device_id: str,
) -> Optional[Batch]:
    """Find the active (fermenting) batch for a device.

    Args:
        db: Database session
        device_id: Device ID to find batch for

    Returns:
        Active Batch if found, None otherwise
    """
    query = (
        select(Batch)
        .where(Batch.device_id == device_id)
        .where(Batch.status == "fermenting")
        .order_by(Batch.start_time.desc())
        .limit(1)
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def link_reading_to_batch(
    db: AsyncSession,
    device_id: str,
) -> Optional[int]:
    """Get batch_id to link a new reading to.

    Args:
        db: Database session
        device_id: Device ID of the reading

    Returns:
        batch_id if active batch exists, None otherwise
    """
    batch = await get_active_batch_for_device(db, device_id)
    return batch.id if batch else None
```

**Step 4: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/test_batch_linker.py -v`

Expected: All PASS

**Step 5: Commit**

```bash
git add backend/services/batch_linker.py backend/tests/test_batch_linker.py
git commit -m "feat: add batch linker service

Provides functions to:
- Find active (fermenting) batch for a device
- Get batch_id to link new readings to

Will be used by scanner/ingest to auto-link readings.

Part of #22"
```

---

## Task 8: Run All Tests and Verify

**Step 1: Run full test suite**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest backend/tests/ -v`

Expected: All PASS

**Step 2: Run type checking (if mypy is available)**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m mypy backend/ --ignore-missing-imports || true`

**Step 3: Start server and verify endpoints**

Run: `cd /home/ladmin/Projects/tilt_ui && timeout 5 python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 || true`

Verify: Server starts without import errors

**Step 4: Commit any final fixes**

If needed, commit any type fixes or minor adjustments.

---

## Summary

This plan implements the core backend for BeerXML recipe import and batch tracking:

1. **Task 1-2**: Database models (Style, Recipe, Batch) with migrations
2. **Task 3**: Pydantic schemas for API serialization
3. **Task 4**: BeerXML parser service
4. **Task 5**: Recipe API endpoints
5. **Task 6**: Batch API endpoints with progress calculations
6. **Task 7**: Batch linker service for auto-linking readings
7. **Task 8**: Full test verification

**Next Phase (not in this plan):**
- Frontend routes for recipes and batches
- Dashboard integration showing batch progress on TiltCard
- WebSocket notifications for temperature warnings
- BJCP style seeding script
