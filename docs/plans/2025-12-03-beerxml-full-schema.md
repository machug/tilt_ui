# BeerXML Full Relational Schema Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement full relational database schema for BeerXML 1.0 data including fermentables, hops, yeasts, mash profiles, and water chemistry.

**Architecture:** Expand existing Recipe model with proper relational tables for all BeerXML components. Use SQLAlchemy ORM with async support. Follow existing migration pattern (manual migrations in database.py). Parse complete BeerXML data into normalized tables.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.0 (async), defusedxml, FastAPI, Svelte

---

## Phase 1: Database Schema & Models

### Task 1: Create Fermentables Model and Table

**Files:**
- Modify: `backend/models.py:316` (after Batch model)
- Modify: `backend/database.py:56` (add migration function)

**Step 1: Write test for Fermentable model**

Create: `backend/tests/test_fermentables_model.py`

```python
import pytest
from backend.models import Recipe, RecipeFermentable
from backend.database import get_db, init_db


@pytest.mark.asyncio
async def test_create_fermentable_with_recipe():
    """Test creating a fermentable linked to a recipe."""
    await init_db()

    async for db in get_db():
        # Create a recipe
        recipe = Recipe(name="Test IPA", og_target=1.060)
        db.add(recipe)
        await db.commit()
        await db.refresh(recipe)

        # Create fermentable
        fermentable = RecipeFermentable(
            recipe_id=recipe.id,
            name="Pale Malt 2-Row",
            type="Grain",
            amount_kg=5.0,
            yield_percent=80.0,
            color_lovibond=2.0,
            origin="US",
            supplier="Briess"
        )
        db.add(fermentable)
        await db.commit()
        await db.refresh(fermentable)

        assert fermentable.id is not None
        assert fermentable.recipe_id == recipe.id
        assert fermentable.name == "Pale Malt 2-Row"
        assert fermentable.amount_kg == 5.0
        break
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_fermentables_model.py::test_create_fermentable_with_recipe -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'backend.tests'"

Create test directory first:
```bash
mkdir -p backend/tests
touch backend/tests/__init__.py
```

Run again: `python -m pytest tests/test_fermentables_model.py::test_create_fermentable_with_recipe -v`
Expected: FAIL with "cannot import name 'RecipeFermentable'"

**Step 3: Create Fermentable model**

Add to `backend/models.py` after Batch model (line ~316):

```python
class RecipeFermentable(Base):
    """Fermentable ingredients (grains, extracts, sugars) in a recipe."""
    __tablename__ = "recipe_fermentables"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # BeerXML fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50))  # Grain, Sugar, Extract, Dry Extract, Adjunct
    amount_kg: Mapped[float] = mapped_column()  # Amount in kilograms
    yield_percent: Mapped[Optional[float]] = mapped_column()  # % yield (0-100)
    color_lovibond: Mapped[Optional[float]] = mapped_column()  # SRM/Lovibond

    # Additional metadata
    origin: Mapped[Optional[str]] = mapped_column(String(50))
    supplier: Mapped[Optional[str]] = mapped_column(String(100))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Advanced BeerXML fields (optional)
    add_after_boil: Mapped[Optional[bool]] = mapped_column(default=False)
    coarse_fine_diff: Mapped[Optional[float]] = mapped_column()  # %
    moisture: Mapped[Optional[float]] = mapped_column()  # %
    diastatic_power: Mapped[Optional[float]] = mapped_column()  # Lintner
    protein: Mapped[Optional[float]] = mapped_column()  # %
    max_in_batch: Mapped[Optional[float]] = mapped_column()  # %
    recommend_mash: Mapped[Optional[bool]] = mapped_column()

    # Relationship
    recipe: Mapped["Recipe"] = relationship(back_populates="fermentables")
```

Update Recipe model to add relationship (around line 274):

```python
# In Recipe class, add to relationships section:
fermentables: Mapped[list["RecipeFermentable"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")
```

**Step 4: Create migration for fermentables table**

Add to `backend/database.py` after line 56 in init_db():

```python
await conn.run_sync(_migrate_create_recipe_fermentables_table)
```

Add migration function at end of file (before get_db):

```python
def _migrate_create_recipe_fermentables_table(conn):
    """Create recipe_fermentables table if it doesn't exist."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "recipe_fermentables" in inspector.get_table_names():
        return  # Table exists

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS recipe_fermentables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            type VARCHAR(50),
            amount_kg REAL,
            yield_percent REAL,
            color_lovibond REAL,
            origin VARCHAR(50),
            supplier VARCHAR(100),
            notes TEXT,
            add_after_boil INTEGER DEFAULT 0,
            coarse_fine_diff REAL,
            moisture REAL,
            diastatic_power REAL,
            protein REAL,
            max_in_batch REAL,
            recommend_mash INTEGER
        )
    """))

    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fermentables_recipe ON recipe_fermentables(recipe_id)"))
    print("Migration: Created recipe_fermentables table")
```

**Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_fermentables_model.py::test_create_fermentable_with_recipe -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/models.py backend/database.py backend/tests/
git commit -m "feat: add RecipeFermentable model and migration"
```

---

### Task 2: Create Hops Model and Table

**Files:**
- Modify: `backend/models.py` (after RecipeFermentable)
- Modify: `backend/database.py` (add migration)

**Step 1: Write test for Hop model**

Create: `backend/tests/test_hops_model.py`

```python
import pytest
from backend.models import Recipe, RecipeHop
from backend.database import get_db, init_db


@pytest.mark.asyncio
async def test_create_hop_with_recipe():
    """Test creating a hop addition linked to a recipe."""
    await init_db()

    async for db in get_db():
        recipe = Recipe(name="Test IPA", og_target=1.065)
        db.add(recipe)
        await db.commit()
        await db.refresh(recipe)

        hop = RecipeHop(
            recipe_id=recipe.id,
            name="Cascade",
            alpha_percent=5.5,
            amount_kg=0.028,  # 28g = 1oz
            use="Boil",
            time_min=60,
            form="Pellet",
            type="Bittering"
        )
        db.add(hop)
        await db.commit()
        await db.refresh(hop)

        assert hop.id is not None
        assert hop.name == "Cascade"
        assert hop.use == "Boil"
        assert hop.time_min == 60
        break
```

**Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_hops_model.py::test_create_hop_with_recipe -v`
Expected: FAIL with "cannot import name 'RecipeHop'"

**Step 3: Create Hop model**

Add to `backend/models.py` after RecipeFermentable:

```python
class RecipeHop(Base):
    """Hop additions in a recipe."""
    __tablename__ = "recipe_hops"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # BeerXML fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    alpha_percent: Mapped[Optional[float]] = mapped_column()  # AA% (0-100)
    amount_kg: Mapped[float] = mapped_column()  # Amount in kilograms
    use: Mapped[str] = mapped_column(String(20))  # Boil, Dry Hop, Mash, First Wort, Aroma
    time_min: Mapped[Optional[float]] = mapped_column()  # Minutes (0 for dry hop timing, or days)

    # Hop characteristics
    form: Mapped[Optional[str]] = mapped_column(String(20))  # Pellet, Plug, Leaf
    type: Mapped[Optional[str]] = mapped_column(String(20))  # Bittering, Aroma, Both
    origin: Mapped[Optional[str]] = mapped_column(String(50))
    substitutes: Mapped[Optional[str]] = mapped_column(String(200))

    # Advanced BeerXML fields
    beta_percent: Mapped[Optional[float]] = mapped_column()  # Beta acids %
    hsi: Mapped[Optional[float]] = mapped_column()  # Hop Storage Index
    humulene: Mapped[Optional[float]] = mapped_column()  # %
    caryophyllene: Mapped[Optional[float]] = mapped_column()  # %
    cohumulone: Mapped[Optional[float]] = mapped_column()  # %
    myrcene: Mapped[Optional[float]] = mapped_column()  # %

    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationship
    recipe: Mapped["Recipe"] = relationship(back_populates="hops")
```

Update Recipe model relationships:

```python
hops: Mapped[list["RecipeHop"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")
```

**Step 4: Create migration**

Add to init_db:
```python
await conn.run_sync(_migrate_create_recipe_hops_table)
```

Add migration function:

```python
def _migrate_create_recipe_hops_table(conn):
    """Create recipe_hops table if it doesn't exist."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "recipe_hops" in inspector.get_table_names():
        return

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS recipe_hops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            alpha_percent REAL,
            amount_kg REAL,
            use VARCHAR(20),
            time_min REAL,
            form VARCHAR(20),
            type VARCHAR(20),
            origin VARCHAR(50),
            substitutes VARCHAR(200),
            beta_percent REAL,
            hsi REAL,
            humulene REAL,
            caryophyllene REAL,
            cohumulone REAL,
            myrcene REAL,
            notes TEXT
        )
    """))

    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_hops_recipe ON recipe_hops(recipe_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_hops_use ON recipe_hops(use)"))  # For dry hop queries
    print("Migration: Created recipe_hops table")
```

**Step 5: Run test**

Run: `python -m pytest tests/test_hops_model.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/models.py backend/database.py backend/tests/test_hops_model.py
git commit -m "feat: add RecipeHop model and migration"
```

---

### Task 3: Create Yeasts Model and Table

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/database.py`

**Step 1: Write test**

Create: `backend/tests/test_yeasts_model.py`

```python
import pytest
from backend.models import Recipe, RecipeYeast
from backend.database import get_db, init_db


@pytest.mark.asyncio
async def test_create_yeast_with_recipe():
    """Test creating yeast linked to a recipe."""
    await init_db()

    async for db in get_db():
        recipe = Recipe(name="Test Ale")
        db.add(recipe)
        await db.commit()
        await db.refresh(recipe)

        yeast = RecipeYeast(
            recipe_id=recipe.id,
            name="Safale US-05",
            lab="Fermentis",
            product_id="US-05",
            type="Ale",
            form="Dry",
            attenuation_percent=81.0,
            temp_min_c=15.0,
            temp_max_c=24.0,
            flocculation="Medium"
        )
        db.add(yeast)
        await db.commit()
        await db.refresh(yeast)

        assert yeast.id is not None
        assert yeast.name == "Safale US-05"
        break
```

**Step 2: Run test (expect fail)**

Run: `python -m pytest tests/test_yeasts_model.py -v`
Expected: FAIL "cannot import RecipeYeast"

**Step 3: Create model**

Add to `backend/models.py`:

```python
class RecipeYeast(Base):
    """Yeast strains in a recipe."""
    __tablename__ = "recipe_yeasts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # BeerXML fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    lab: Mapped[Optional[str]] = mapped_column(String(100))
    product_id: Mapped[Optional[str]] = mapped_column(String(50))
    type: Mapped[Optional[str]] = mapped_column(String(20))  # Ale, Lager, Wheat, Wine, Champagne
    form: Mapped[Optional[str]] = mapped_column(String(20))  # Liquid, Dry, Slant, Culture

    # Fermentation characteristics
    attenuation_percent: Mapped[Optional[float]] = mapped_column()  # % (0-100)
    temp_min_c: Mapped[Optional[float]] = mapped_column()  # Celsius
    temp_max_c: Mapped[Optional[float]] = mapped_column()  # Celsius
    flocculation: Mapped[Optional[str]] = mapped_column(String(20))  # Low, Medium, High, Very High

    # Pitching
    amount_l: Mapped[Optional[float]] = mapped_column()  # Liters (if liquid)
    amount_kg: Mapped[Optional[float]] = mapped_column()  # Kg (if dry)
    add_to_secondary: Mapped[Optional[bool]] = mapped_column(default=False)

    # Advanced fields
    best_for: Mapped[Optional[str]] = mapped_column(Text)
    times_cultured: Mapped[Optional[int]] = mapped_column()
    max_reuse: Mapped[Optional[int]] = mapped_column()
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationship
    recipe: Mapped["Recipe"] = relationship(back_populates="yeasts")
```

Update Recipe:
```python
yeasts: Mapped[list["RecipeYeast"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")
```

**Step 4: Create migration**

Add to init_db:
```python
await conn.run_sync(_migrate_create_recipe_yeasts_table)
```

Migration function:

```python
def _migrate_create_recipe_yeasts_table(conn):
    """Create recipe_yeasts table."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "recipe_yeasts" in inspector.get_table_names():
        return

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS recipe_yeasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            lab VARCHAR(100),
            product_id VARCHAR(50),
            type VARCHAR(20),
            form VARCHAR(20),
            attenuation_percent REAL,
            temp_min_c REAL,
            temp_max_c REAL,
            flocculation VARCHAR(20),
            amount_l REAL,
            amount_kg REAL,
            add_to_secondary INTEGER DEFAULT 0,
            best_for TEXT,
            times_cultured INTEGER,
            max_reuse INTEGER,
            notes TEXT
        )
    """))

    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_yeasts_recipe ON recipe_yeasts(recipe_id)"))
    print("Migration: Created recipe_yeasts table")
```

**Step 5: Run test**

Run: `python -m pytest tests/test_yeasts_model.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/models.py backend/database.py backend/tests/
git commit -m "feat: add RecipeYeast model and migration"
```

---

### Task 4: Create Misc Ingredients Model

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/database.py`

**Step 1: Write test**

Create: `backend/tests/test_misc_model.py`

```python
import pytest
from backend.models import Recipe, RecipeMisc
from backend.database import get_db, init_db


@pytest.mark.asyncio
async def test_create_misc_with_recipe():
    await init_db()

    async for db in get_db():
        recipe = Recipe(name="Test Beer")
        db.add(recipe)
        await db.commit()
        await db.refresh(recipe)

        misc = RecipeMisc(
            recipe_id=recipe.id,
            name="Irish Moss",
            type="Fining",
            use="Boil",
            time_min=15,
            amount_kg=0.005
        )
        db.add(misc)
        await db.commit()

        assert misc.id is not None
        assert misc.name == "Irish Moss"
        break
```

**Step 2: Run test (expect fail)**

Run: `python -m pytest tests/test_misc_model.py -v`

**Step 3: Create model**

```python
class RecipeMisc(Base):
    """Misc ingredients (spices, finings, water agents, etc)."""
    __tablename__ = "recipe_miscs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50))  # Spice, Fining, Water Agent, Herb, Flavor, Other
    use: Mapped[str] = mapped_column(String(20))  # Boil, Mash, Primary, Secondary, Bottling
    time_min: Mapped[Optional[float]] = mapped_column()  # Minutes
    amount_kg: Mapped[Optional[float]] = mapped_column()  # Kg or L (check amount_is_weight)
    amount_is_weight: Mapped[Optional[bool]] = mapped_column(default=True)
    use_for: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    recipe: Mapped["Recipe"] = relationship(back_populates="miscs")
```

Update Recipe:
```python
miscs: Mapped[list["RecipeMisc"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")
```

**Step 4: Create migration**

```python
def _migrate_create_recipe_miscs_table(conn):
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "recipe_miscs" in inspector.get_table_names():
        return

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS recipe_miscs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            type VARCHAR(50),
            use VARCHAR(20),
            time_min REAL,
            amount_kg REAL,
            amount_is_weight INTEGER DEFAULT 1,
            use_for TEXT,
            notes TEXT
        )
    """))

    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_miscs_recipe ON recipe_miscs(recipe_id)"))
    print("Migration: Created recipe_miscs table")
```

Add to init_db:
```python
await conn.run_sync(_migrate_create_recipe_miscs_table)
```

**Step 5: Test and commit**

Run: `python -m pytest tests/test_misc_model.py -v`

```bash
git add backend/models.py backend/database.py backend/tests/
git commit -m "feat: add RecipeMisc model and migration"
```

---

### Task 5: Expand Recipe Model with Additional BeerXML Fields

**Files:**
- Modify: `backend/models.py` (Recipe class)
- Modify: `backend/database.py` (add column migration)

**Step 1: Write test**

Create: `backend/tests/test_recipe_expanded_fields.py`

```python
import pytest
from datetime import datetime, timezone
from backend.models import Recipe
from backend.database import get_db, init_db


@pytest.mark.asyncio
async def test_recipe_with_expanded_fields():
    await init_db()

    async for db in get_db():
        recipe = Recipe(
            name="Expanded IPA",
            brewer="Test Brewer",
            asst_brewer="Assistant",
            boil_size_l=27.0,
            boil_time_min=60,
            efficiency_percent=75.0,
            primary_age_days=14,
            primary_temp_c=20.0,
            carbonation_vols=2.4,
            forced_carbonation=False,
            priming_sugar_name="Corn Sugar",
            age_days=21,
            age_temp_c=4.0,
            taste_notes="Hoppy with citrus notes",
            taste_rating=42
        )
        db.add(recipe)
        await db.commit()

        assert recipe.brewer == "Test Brewer"
        assert recipe.boil_time_min == 60
        assert recipe.primary_age_days == 14
        break
```

**Step 2: Run test (expect fail)**

Run: `python -m pytest tests/test_recipe_expanded_fields.py -v`
Expected: FAIL "Recipe.__init__() got unexpected keyword"

**Step 3: Expand Recipe model**

In `backend/models.py`, add to Recipe class after existing fields:

```python
    # Expanded BeerXML fields
    brewer: Mapped[Optional[str]] = mapped_column(String(100))
    asst_brewer: Mapped[Optional[str]] = mapped_column(String(100))

    # Boil
    boil_size_l: Mapped[Optional[float]] = mapped_column()  # Pre-boil volume (liters)
    boil_time_min: Mapped[Optional[int]] = mapped_column()  # Total boil time

    # Efficiency
    efficiency_percent: Mapped[Optional[float]] = mapped_column()  # Brewhouse efficiency (0-100)

    # Fermentation stages
    primary_age_days: Mapped[Optional[int]] = mapped_column()
    primary_temp_c: Mapped[Optional[float]] = mapped_column()
    secondary_age_days: Mapped[Optional[int]] = mapped_column()
    secondary_temp_c: Mapped[Optional[float]] = mapped_column()
    tertiary_age_days: Mapped[Optional[int]] = mapped_column()
    tertiary_temp_c: Mapped[Optional[float]] = mapped_column()

    # Aging
    age_days: Mapped[Optional[int]] = mapped_column()
    age_temp_c: Mapped[Optional[float]] = mapped_column()

    # Carbonation
    carbonation_vols: Mapped[Optional[float]] = mapped_column()  # CO2 volumes
    forced_carbonation: Mapped[Optional[bool]] = mapped_column()
    priming_sugar_name: Mapped[Optional[str]] = mapped_column(String(50))
    priming_sugar_amount_kg: Mapped[Optional[float]] = mapped_column()

    # Tasting
    taste_notes: Mapped[Optional[str]] = mapped_column(Text)
    taste_rating: Mapped[Optional[float]] = mapped_column()  # BJCP scale (0-50)

    # Dates
    date: Mapped[Optional[str]] = mapped_column(String(50))  # Brew date from BeerXML
```

**Step 4: Create migration**

Add migration function:

```python
def _migrate_add_recipe_expanded_fields(conn):
    """Add expanded BeerXML fields to recipes table."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "recipes" not in inspector.get_table_names():
        return

    columns = [c["name"] for c in inspector.get_columns("recipes")]

    new_columns = [
        ("brewer", "VARCHAR(100)"),
        ("asst_brewer", "VARCHAR(100)"),
        ("boil_size_l", "REAL"),
        ("boil_time_min", "INTEGER"),
        ("efficiency_percent", "REAL"),
        ("primary_age_days", "INTEGER"),
        ("primary_temp_c", "REAL"),
        ("secondary_age_days", "INTEGER"),
        ("secondary_temp_c", "REAL"),
        ("tertiary_age_days", "INTEGER"),
        ("tertiary_temp_c", "REAL"),
        ("age_days", "INTEGER"),
        ("age_temp_c", "REAL"),
        ("carbonation_vols", "REAL"),
        ("forced_carbonation", "INTEGER"),
        ("priming_sugar_name", "VARCHAR(50)"),
        ("priming_sugar_amount_kg", "REAL"),
        ("taste_notes", "TEXT"),
        ("taste_rating", "REAL"),
        ("date", "VARCHAR(50)"),
    ]

    for col_name, col_def in new_columns:
        if col_name not in columns:
            conn.execute(text(f"ALTER TABLE recipes ADD COLUMN {col_name} {col_def}"))

    print("Migration: Added expanded BeerXML fields to recipes table")
```

Add to init_db:
```python
await conn.run_sync(_migrate_add_recipe_expanded_fields)
```

**Step 5: Test and commit**

Run: `python -m pytest tests/test_recipe_expanded_fields.py -v`

```bash
git add backend/models.py backend/database.py backend/tests/
git commit -m "feat: expand Recipe model with additional BeerXML fields"
```

---

## Phase 2: Update BeerXML Parser

### Task 6: Parse Fermentables from BeerXML

**Files:**
- Modify: `backend/services/beerxml_parser.py`
- Create: `backend/tests/test_beerxml_fermentables.py`

**Step 1: Write test**

Create test file with sample BeerXML:

```python
import pytest
from backend.services.beerxml_parser import parse_beerxml


SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<RECIPES>
  <RECIPE>
    <NAME>Test IPA</NAME>
    <BREWER>Test Brewer</BREWER>
    <FERMENTABLES>
      <FERMENTABLE>
        <NAME>Pale Malt 2-Row</NAME>
        <TYPE>Grain</TYPE>
        <AMOUNT>5.0</AMOUNT>
        <YIELD>80.0</YIELD>
        <COLOR>2.0</COLOR>
        <ORIGIN>US</ORIGIN>
        <SUPPLIER>Briess</SUPPLIER>
      </FERMENTABLE>
      <FERMENTABLE>
        <NAME>Munich Malt</NAME>
        <TYPE>Grain</TYPE>
        <AMOUNT>0.5</AMOUNT>
        <YIELD>78.0</YIELD>
        <COLOR>10.0</COLOR>
      </FERMENTABLE>
    </FERMENTABLES>
  </RECIPE>
</RECIPES>
"""


def test_parse_fermentables():
    """Test parsing fermentables from BeerXML."""
    recipes = parse_beerxml(SAMPLE_XML)

    assert len(recipes) == 1
    recipe = recipes[0]

    assert len(recipe.fermentables) == 2

    pale_malt = recipe.fermentables[0]
    assert pale_malt.name == "Pale Malt 2-Row"
    assert pale_malt.type == "Grain"
    assert pale_malt.amount_kg == 5.0
    assert pale_malt.yield_percent == 80.0
    assert pale_malt.color_lovibond == 2.0
    assert pale_malt.origin == "US"
    assert pale_malt.supplier == "Briess"
```

**Step 2: Run test (expect fail)**

Run: `python -m pytest tests/test_beerxml_fermentables.py -v`
Expected: FAIL "ParsedRecipe has no attribute fermentables"

**Step 3: Update ParsedRecipe dataclass**

In `backend/services/beerxml_parser.py`, add to imports:

```python
@dataclass
class ParsedFermentable:
    """Fermentable ingredient data."""
    name: str
    type: Optional[str] = None
    amount_kg: Optional[float] = None
    yield_percent: Optional[float] = None
    color_lovibond: Optional[float] = None
    origin: Optional[str] = None
    supplier: Optional[str] = None
    notes: Optional[str] = None
    add_after_boil: Optional[bool] = None
    coarse_fine_diff: Optional[float] = None
    moisture: Optional[float] = None
    diastatic_power: Optional[float] = None
    protein: Optional[float] = None
    max_in_batch: Optional[float] = None
    recommend_mash: Optional[bool] = None
```

Update ParsedRecipe:

```python
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
    fermentables: list[ParsedFermentable] = field(default_factory=list)  # ADD THIS
    raw_xml: str = ""
```

**Step 4: Add parsing logic**

Add helper function before `_parse_recipe`:

```python
def _parse_fermentables(recipe_elem) -> list[ParsedFermentable]:
    """Parse FERMENTABLES section."""
    fermentables = []

    for ferm_elem in recipe_elem.findall('.//FERMENTABLES/FERMENTABLE'):
        fermentable = ParsedFermentable(
            name=_get_text(ferm_elem, 'NAME') or "Unknown",
            type=_get_text(ferm_elem, 'TYPE'),
            amount_kg=_get_float(ferm_elem, 'AMOUNT'),
            yield_percent=_get_float(ferm_elem, 'YIELD'),
            color_lovibond=_get_float(ferm_elem, 'COLOR'),
            origin=_get_text(ferm_elem, 'ORIGIN'),
            supplier=_get_text(ferm_elem, 'SUPPLIER'),
            notes=_get_text(ferm_elem, 'NOTES'),
            add_after_boil=_get_text(ferm_elem, 'ADD_AFTER_BOIL') == 'TRUE',
            coarse_fine_diff=_get_float(ferm_elem, 'COARSE_FINE_DIFF'),
            moisture=_get_float(ferm_elem, 'MOISTURE'),
            diastatic_power=_get_float(ferm_elem, 'DIASTATIC_POWER'),
            protein=_get_float(ferm_elem, 'PROTEIN'),
            max_in_batch=_get_float(ferm_elem, 'MAX_IN_BATCH'),
            recommend_mash=_get_text(ferm_elem, 'RECOMMEND_MASH') == 'TRUE',
        )
        fermentables.append(fermentable)

    return fermentables
```

Update `_parse_recipe` to call this (after yeast parsing):

```python
    # Parse fermentables
    recipe.fermentables = _parse_fermentables(elem)
```

**Step 5: Test and commit**

Run: `python -m pytest tests/test_beerxml_fermentables.py -v`

```bash
git add backend/services/beerxml_parser.py backend/tests/
git commit -m "feat: parse fermentables from BeerXML"
```

---

### Task 7: Parse Hops from BeerXML

**Files:**
- Modify: `backend/services/beerxml_parser.py`
- Create: `backend/tests/test_beerxml_hops.py`

**Step 1: Write test**

```python
SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<RECIPES>
  <RECIPE>
    <NAME>Hoppy IPA</NAME>
    <HOPS>
      <HOP>
        <NAME>Cascade</NAME>
        <ALPHA>5.5</ALPHA>
        <AMOUNT>0.028</AMOUNT>
        <USE>Boil</USE>
        <TIME>60</TIME>
        <FORM>Pellet</FORM>
        <TYPE>Bittering</TYPE>
      </HOP>
      <HOP>
        <NAME>Citra</NAME>
        <ALPHA>12.0</ALPHA>
        <AMOUNT>0.056</AMOUNT>
        <USE>Dry Hop</USE>
        <TIME>7</TIME>
        <FORM>Pellet</FORM>
        <TYPE>Aroma</TYPE>
      </HOP>
    </HOPS>
  </RECIPE>
</RECIPES>
"""


def test_parse_hops():
    recipes = parse_beerxml(SAMPLE_XML)
    assert len(recipes[0].hops) == 2

    cascade = recipes[0].hops[0]
    assert cascade.name == "Cascade"
    assert cascade.alpha_percent == 5.5
    assert cascade.use == "Boil"
    assert cascade.time_min == 60

    citra = recipes[0].hops[1]
    assert citra.name == "Citra"
    assert citra.use == "Dry Hop"
```

**Step 2: Run test (expect fail)**

**Step 3: Add ParsedHop dataclass and parsing**

```python
@dataclass
class ParsedHop:
    name: str
    alpha_percent: Optional[float] = None
    amount_kg: Optional[float] = None
    use: Optional[str] = None
    time_min: Optional[float] = None
    form: Optional[str] = None
    type: Optional[str] = None
    origin: Optional[str] = None
    substitutes: Optional[str] = None
    beta_percent: Optional[float] = None
    hsi: Optional[float] = None
    humulene: Optional[float] = None
    caryophyllene: Optional[float] = None
    cohumulone: Optional[float] = None
    myrcene: Optional[float] = None
    notes: Optional[str] = None


def _parse_hops(recipe_elem) -> list[ParsedHop]:
    hops = []
    for hop_elem in recipe_elem.findall('.//HOPS/HOP'):
        hop = ParsedHop(
            name=_get_text(hop_elem, 'NAME') or "Unknown",
            alpha_percent=_get_float(hop_elem, 'ALPHA'),
            amount_kg=_get_float(hop_elem, 'AMOUNT'),
            use=_get_text(hop_elem, 'USE'),
            time_min=_get_float(hop_elem, 'TIME'),
            form=_get_text(hop_elem, 'FORM'),
            type=_get_text(hop_elem, 'TYPE'),
            origin=_get_text(hop_elem, 'ORIGIN'),
            substitutes=_get_text(hop_elem, 'SUBSTITUTES'),
            beta_percent=_get_float(hop_elem, 'BETA'),
            hsi=_get_float(hop_elem, 'HSI'),
            humulene=_get_float(hop_elem, 'HUMULENE'),
            caryophyllene=_get_float(hop_elem, 'CARYOPHYLLENE'),
            cohumulone=_get_float(hop_elem, 'COHUMULONE'),
            myrcene=_get_float(hop_elem, 'MYRCENE'),
            notes=_get_text(hop_elem, 'NOTES'),
        )
        hops.append(hop)
    return hops
```

Add to ParsedRecipe:
```python
hops: list[ParsedHop] = field(default_factory=list)
```

Add to `_parse_recipe`:
```python
recipe.hops = _parse_hops(elem)
```

**Step 4: Test and commit**

```bash
git add backend/services/beerxml_parser.py backend/tests/
git commit -m "feat: parse hops from BeerXML"
```

---

### Task 8: Parse Yeasts and Misc Ingredients

**Files:**
- Modify: `backend/services/beerxml_parser.py`
- Create tests

Follow same pattern as Tasks 6-7:

1. Write test with sample XML
2. Create ParsedYeast and ParsedMisc dataclasses
3. Create `_parse_yeasts` and `_parse_miscs` functions
4. Add to ParsedRecipe and `_parse_recipe`
5. Test and commit

---

### Task 9: Update Recipe Import to Save Relational Data

**Files:**
- Create: `backend/services/recipe_importer.py`
- Modify: `backend/routers/recipes.py`

**Step 1: Write integration test**

Create: `backend/tests/test_recipe_import_integration.py`

```python
import pytest
from backend.services.recipe_importer import import_beerxml_to_db
from backend.models import Recipe
from backend.database import get_db, init_db


FULL_BEERXML = """<?xml version="1.0"?>
<RECIPES>
  <RECIPE>
    <NAME>American IPA</NAME>
    <BREWER>Test Brewer</BREWER>
    <TYPE>All Grain</TYPE>
    <OG>1.065</OG>
    <FG>1.012</FG>
    <FERMENTABLES>
      <FERMENTABLE>
        <NAME>Pale Malt</NAME>
        <AMOUNT>5.0</AMOUNT>
        <TYPE>Grain</TYPE>
      </FERMENTABLE>
    </FERMENTABLES>
    <HOPS>
      <HOP>
        <NAME>Cascade</NAME>
        <AMOUNT>0.028</AMOUNT>
        <USE>Boil</USE>
        <TIME>60</TIME>
      </HOP>
    </HOPS>
    <YEASTS>
      <YEAST>
        <NAME>US-05</NAME>
        <LAB>Fermentis</LAB>
      </YEAST>
    </YEASTS>
  </RECIPE>
</RECIPES>
"""


@pytest.mark.asyncio
async def test_import_full_recipe():
    await init_db()

    async for db in get_db():
        recipe_id = await import_beerxml_to_db(db, FULL_BEERXML)

        # Fetch with all relationships
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        result = await db.execute(
            select(Recipe)
            .where(Recipe.id == recipe_id)
            .options(
                selectinload(Recipe.fermentables),
                selectinload(Recipe.hops),
                selectinload(Recipe.yeasts)
            )
        )
        recipe = result.scalar_one()

        assert recipe.name == "American IPA"
        assert len(recipe.fermentables) == 1
        assert recipe.fermentables[0].name == "Pale Malt"
        assert len(recipe.hops) == 1
        assert recipe.hops[0].name == "Cascade"
        assert len(recipe.yeasts) == 1
        assert recipe.yeasts[0].name == "US-05"
        break
```

**Step 2: Run test (expect fail)**

**Step 3: Create recipe importer service**

Create: `backend/services/recipe_importer.py`

```python
"""Service for importing BeerXML into database."""

from sqlalchemy.ext.asyncio import AsyncSession
from backend.services.beerxml_parser import parse_beerxml
from backend.models import (
    Recipe, RecipeFermentable, RecipeHop,
    RecipeYeast, RecipeMisc
)


async def import_beerxml_to_db(db: AsyncSession, xml_content: str) -> int:
    """Import BeerXML and save to database.

    Args:
        db: Database session
        xml_content: BeerXML 1.0 string

    Returns:
        Recipe ID of first imported recipe
    """
    # Parse XML
    parsed_recipes = parse_beerxml(xml_content)
    if not parsed_recipes:
        raise ValueError("No recipes found in BeerXML")

    # Take first recipe (most BeerXML exports contain one recipe)
    parsed = parsed_recipes[0]

    # Create Recipe
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

    db.add(recipe)
    await db.flush()  # Get recipe.id

    # Add fermentables
    for f in parsed.fermentables:
        fermentable = RecipeFermentable(
            recipe_id=recipe.id,
            name=f.name,
            type=f.type,
            amount_kg=f.amount_kg,
            yield_percent=f.yield_percent,
            color_lovibond=f.color_lovibond,
            origin=f.origin,
            supplier=f.supplier,
            notes=f.notes,
            add_after_boil=f.add_after_boil,
            coarse_fine_diff=f.coarse_fine_diff,
            moisture=f.moisture,
            diastatic_power=f.diastatic_power,
            protein=f.protein,
            max_in_batch=f.max_in_batch,
            recommend_mash=f.recommend_mash,
        )
        db.add(fermentable)

    # Add hops
    for h in parsed.hops:
        hop = RecipeHop(
            recipe_id=recipe.id,
            name=h.name,
            alpha_percent=h.alpha_percent,
            amount_kg=h.amount_kg,
            use=h.use,
            time_min=h.time_min,
            form=h.form,
            type=h.type,
            origin=h.origin,
            substitutes=h.substitutes,
            beta_percent=h.beta_percent,
            hsi=h.hsi,
            humulene=h.humulene,
            caryophyllene=h.caryophyllene,
            cohumulone=h.cohumulone,
            myrcene=h.myrcene,
            notes=h.notes,
        )
        db.add(hop)

    # Add yeasts
    for y in parsed.yeasts:
        yeast = RecipeYeast(
            recipe_id=recipe.id,
            name=y.name,
            lab=y.lab,
            product_id=y.product_id,
            # Add all yeast fields...
        )
        db.add(yeast)

    # Add miscs
    for m in parsed.miscs:
        misc = RecipeMisc(
            recipe_id=recipe.id,
            name=m.name,
            # Add all misc fields...
        )
        db.add(misc)

    await db.commit()
    return recipe.id
```

**Step 4: Test and commit**

Run: `python -m pytest tests/test_recipe_import_integration.py -v`

```bash
git add backend/services/recipe_importer.py backend/tests/
git commit -m "feat: create recipe importer service for full BeerXML import"
```

---

## Phase 3: API Endpoints & Response Models

### Task 10: Update Recipe Response Models

**Files:**
- Modify: `backend/models.py` (Pydantic response models)

**Step 1: Create response models for ingredients**

Add after existing RecipeResponse:

```python
class FermentableResponse(BaseModel):
    id: int
    name: str
    type: Optional[str]
    amount_kg: Optional[float]
    yield_percent: Optional[float]
    color_lovibond: Optional[float]
    origin: Optional[str]
    supplier: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class HopResponse(BaseModel):
    id: int
    name: str
    alpha_percent: Optional[float]
    amount_kg: Optional[float]
    use: Optional[str]
    time_min: Optional[float]
    form: Optional[str]
    type: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class YeastResponse(BaseModel):
    id: int
    name: str
    lab: Optional[str]
    product_id: Optional[str]
    type: Optional[str]
    attenuation_percent: Optional[float]
    temp_min_c: Optional[float]
    temp_max_c: Optional[float]
    flocculation: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class RecipeDetailResponse(BaseModel):
    """Full recipe with all ingredients."""
    id: int
    name: str
    author: Optional[str]
    type: Optional[str]
    og_target: Optional[float]
    fg_target: Optional[float]
    ibu_target: Optional[float]
    batch_size: Optional[float]

    fermentables: list[FermentableResponse] = []
    hops: list[HopResponse] = []
    yeasts: list[YeastResponse] = []

    model_config = ConfigDict(from_attributes=True)
```

**Step 2: Update recipe detail endpoint**

Modify `backend/routers/recipes.py`:

```python
from sqlalchemy.orm import selectinload

@router.get("/{recipe_id}", response_model=RecipeDetailResponse)
async def get_recipe(recipe_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(
            selectinload(Recipe.fermentables),
            selectinload(Recipe.hops),
            selectinload(Recipe.yeasts),
            selectinload(Recipe.miscs),
        )
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(404, "Recipe not found")
    return recipe
```

**Step 3: Test endpoint**

Manual test or integration test

**Step 4: Commit**

```bash
git add backend/models.py backend/routers/recipes.py
git commit -m "feat: add detailed recipe response with ingredients"
```

---

## Phase 4: Frontend Recipe Detail View

### Task 11: Create Recipe Ingredient Display Components

**Files:**
- Create: `frontend/src/lib/components/recipe/RecipeIngredients.svelte`
- Create: `frontend/src/lib/components/recipe/FermentablesList.svelte`
- Create: `frontend/src/lib/components/recipe/HopSchedule.svelte`

**Step 1: Create fermentables list component**

Create: `frontend/src/lib/components/recipe/FermentablesList.svelte`

```svelte
<script lang="ts">
	interface Fermentable {
		name: string;
		type?: string;
		amount_kg?: number;
		color_lovibond?: number;
		origin?: string;
	}

	let { fermentables }: { fermentables: Fermentable[] } = $props();

	// Calculate total and percentages
	let totalKg = $derived(
		fermentables.reduce((sum, f) => sum + (f.amount_kg || 0), 0)
	);

	function getPercent(amount?: number): string {
		if (!amount || !totalKg) return '--';
		return ((amount / totalKg) * 100).toFixed(1) + '%';
	}
</script>

<div class="fermentables">
	<h3>Grain Bill</h3>
	<table>
		<thead>
			<tr>
				<th>Fermentable</th>
				<th>Type</th>
				<th>Amount</th>
				<th>%</th>
				<th>Color</th>
			</tr>
		</thead>
		<tbody>
			{#each fermentables as ferm}
				<tr>
					<td class="name">
						{ferm.name}
						{#if ferm.origin}
							<span class="origin">({ferm.origin})</span>
						{/if}
					</td>
					<td>{ferm.type || '--'}</td>
					<td>{ferm.amount_kg?.toFixed(2)} kg</td>
					<td>{getPercent(ferm.amount_kg)}</td>
					<td>{ferm.color_lovibond?.toFixed(0)}°L</td>
				</tr>
			{/each}
		</tbody>
		<tfoot>
			<tr>
				<td colspan="2"><strong>Total</strong></td>
				<td><strong>{totalKg.toFixed(2)} kg</strong></td>
				<td>100%</td>
				<td>--</td>
			</tr>
		</tfoot>
	</table>
</div>

<style>
	.fermentables {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		padding: 1rem;
	}

	table {
		width: 100%;
		border-collapse: collapse;
	}

	th {
		text-align: left;
		padding: 0.5rem;
		border-bottom: 2px solid var(--border-default);
		font-size: 0.875rem;
		color: var(--text-muted);
	}

	td {
		padding: 0.5rem;
		border-bottom: 1px solid var(--border-subtle);
	}

	.name {
		font-weight: 500;
	}

	.origin {
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	tfoot td {
		border-top: 2px solid var(--border-default);
		border-bottom: none;
	}
</style>
```

**Step 2: Create hop schedule component**

Create: `frontend/src/lib/components/recipe/HopSchedule.svelte`

```svelte
<script lang="ts">
	interface Hop {
		name: string;
		alpha_percent?: number;
		amount_kg?: number;
		use?: string;
		time_min?: number;
		form?: string;
	}

	let { hops }: { hops: Hop[] } = $props();

	// Group hops by use (Boil, Dry Hop, etc.)
	let groupedHops = $derived.by(() => {
		const groups: Record<string, Hop[]> = {};
		for (const hop of hops) {
			const use = hop.use || 'Other';
			if (!groups[use]) groups[use] = [];
			groups[use].push(hop);
		}
		// Sort boil hops by time (longest first)
		for (const [use, hopList] of Object.entries(groups)) {
			if (use === 'Boil') {
				hopList.sort((a, b) => (b.time_min || 0) - (a.time_min || 0));
			}
		}
		return groups;
	});

	function formatAmount(kg?: number): string {
		if (!kg) return '--';
		const grams = kg * 1000;
		return grams.toFixed(0) + 'g';
	}
</script>

<div class="hop-schedule">
	<h3>Hop Schedule</h3>

	{#each Object.entries(groupedHops) as [use, hopList]}
		<div class="hop-group">
			<h4>{use}</h4>
			<table>
				<thead>
					<tr>
						<th>Hop</th>
						<th>Amount</th>
						<th>AA%</th>
						<th>Time</th>
						<th>Form</th>
					</tr>
				</thead>
				<tbody>
					{#each hopList as hop}
						<tr>
							<td class="hop-name">{hop.name}</td>
							<td>{formatAmount(hop.amount_kg)}</td>
							<td>{hop.alpha_percent?.toFixed(1)}%</td>
							<td>
								{#if hop.use === 'Dry Hop'}
									Day {hop.time_min || 0}
								{:else}
									{hop.time_min || 0} min
								{/if}
							</td>
							<td>{hop.form || '--'}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/each}
</div>

<style>
	.hop-schedule {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		padding: 1rem;
	}

	.hop-group {
		margin-bottom: 1rem;
	}

	.hop-group:last-child {
		margin-bottom: 0;
	}

	h4 {
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-secondary);
		margin-bottom: 0.5rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	table {
		width: 100%;
		border-collapse: collapse;
	}

	th {
		text-align: left;
		padding: 0.5rem;
		font-size: 0.875rem;
		color: var(--text-muted);
	}

	td {
		padding: 0.5rem;
	}

	.hop-name {
		font-weight: 500;
	}
</style>
```

**Step 3: Update recipe detail page**

Modify: `frontend/src/routes/recipes/[id]/+page.svelte`

Add imports and components to display ingredients.

**Step 4: Manual test in browser**

**Step 5: Commit**

```bash
git add frontend/src/lib/components/recipe/
git commit -m "feat: create ingredient display components for recipes"
```

---

## Testing & Validation

### Task 12: End-to-End Test with Real BeerXML

**Files:**
- Create: `backend/tests/fixtures/sample_recipe.xml`
- Create: `backend/tests/test_full_import_e2e.py`

**Step 1: Add real BeerXML sample**

Download sample from BeerSmith or create realistic example.

**Step 2: Write E2E test**

Test full flow: XML → Parse → Import → API → Response

**Step 3: Run test**

**Step 4: Fix any issues**

**Step 5: Final commit**

```bash
git add backend/tests/
git commit -m "test: add end-to-end BeerXML import test"
```

---

## Execution Complete

Plan complete and saved to `docs/plans/2025-12-03-beerxml-full-schema.md`.

**Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
