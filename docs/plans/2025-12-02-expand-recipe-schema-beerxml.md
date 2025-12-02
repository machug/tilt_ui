# Expand Recipe Schema for Complete BeerXML Data Storage

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform recipe storage from fermentation-only subset to complete BeerXML data with queryable relational schema for grain bills, hop schedules, mash profiles, and all brewing details.

**Architecture:** Hybrid approach - keep existing fermentation fields for quick batch creation, add relational tables for ingredients (hops, fermentables, yeasts, miscs), mash profiles, and equipment. Expand BeerXML parser to populate all tables. Update UI to display complete recipe cards.

**Tech Stack:** SQLAlchemy ORM, Alembic migrations, defusedxml, Python 3.11+, SvelteKit frontend

---

## Phase 1: Database Schema Expansion

### Task 1: Add Recipe Top-Level Fields

**Files:**
- Modify: `backend/models.py:208-247` (Recipe class)
- Create: `backend/alembic/versions/YYYY_MM_DD_HHMM_expand_recipe_schema.py`
- Test: `backend/tests/test_recipe_models.py`

**Step 1: Write failing test for expanded Recipe fields**

```python
# backend/tests/test_recipe_models.py
def test_recipe_with_expanded_beerxml_fields(db_session):
    """Test Recipe model stores complete BeerXML top-level fields."""
    recipe = Recipe(
        name="Test IPA",
        author="Brad Smith",
        asst_brewer="Drew Avis",
        type="All Grain",
        boil_size=22.71,  # liters
        boil_time=60.0,  # minutes
        efficiency=72.0,  # percent
        taste_notes="Hoppy and bitter with citrus notes",
        taste_rating=42.5,  # BJCP 0-50
        brew_date="2025-12-02",
        carbonation=2.5,  # volumes CO2
        forced_carbonation=False,
        priming_sugar_name="Corn Sugar",
        fermentation_stages=2,
        primary_age=7,  # days
        primary_temp=18.0,  # celsius
        secondary_age=14,
        secondary_temp=16.0,
        age=30,  # days to age after bottling
        age_temp=12.0,
    )
    db_session.add(recipe)
    db_session.commit()

    retrieved = db_session.query(Recipe).filter_by(name="Test IPA").first()
    assert retrieved.boil_size == 22.71
    assert retrieved.boil_time == 60.0
    assert retrieved.efficiency == 72.0
    assert retrieved.taste_notes == "Hoppy and bitter with citrus notes"
    assert retrieved.fermentation_stages == 2
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_recipe_models.py::test_recipe_with_expanded_beerxml_fields -v`
Expected: FAIL with "Recipe has no attribute 'boil_size'"

**Step 3: Add expanded fields to Recipe model**

```python
# backend/models.py:208-247 (add after existing fields)
class Recipe(Base):
    """Recipes imported from BeerXML or created manually."""
    __tablename__ = "recipes"

    # ... existing fields ...

    # Recipe-level brewing data (BeerXML top-level fields)
    boil_size: Mapped[Optional[float]] = mapped_column()  # Liters
    boil_time: Mapped[Optional[float]] = mapped_column()  # Minutes
    efficiency: Mapped[Optional[float]] = mapped_column()  # Percent (for all-grain)

    # Assistant brewer
    asst_brewer: Mapped[Optional[str]] = mapped_column(String(100))

    # Tasting and evaluation
    taste_notes: Mapped[Optional[str]] = mapped_column(Text)
    taste_rating: Mapped[Optional[float]] = mapped_column()  # BJCP 0-50
    brew_date: Mapped[Optional[str]] = mapped_column(String(50))  # Free-form date

    # Carbonation
    carbonation: Mapped[Optional[float]] = mapped_column()  # Volumes CO2
    forced_carbonation: Mapped[Optional[bool]] = mapped_column()
    priming_sugar_name: Mapped[Optional[str]] = mapped_column(String(100))
    carbonation_temp: Mapped[Optional[float]] = mapped_column()  # Celsius
    priming_sugar_equiv: Mapped[Optional[float]] = mapped_column()  # Conversion factor
    keg_priming_factor: Mapped[Optional[float]] = mapped_column()  # Keg sugar factor

    # Fermentation schedule
    fermentation_stages: Mapped[Optional[int]] = mapped_column()  # 1-3
    primary_age: Mapped[Optional[float]] = mapped_column()  # Days
    primary_temp: Mapped[Optional[float]] = mapped_column()  # Celsius
    secondary_age: Mapped[Optional[float]] = mapped_column()  # Days
    secondary_temp: Mapped[Optional[float]] = mapped_column()  # Celsius
    tertiary_age: Mapped[Optional[float]] = mapped_column()  # Days
    tertiary_temp: Mapped[Optional[float]] = mapped_column()  # Celsius
    age: Mapped[Optional[float]] = mapped_column()  # Days to age after bottling
    age_temp: Mapped[Optional[float]] = mapped_column()  # Aging temperature
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_recipe_models.py::test_recipe_with_expanded_beerxml_fields -v`
Expected: FAIL with "table recipes has no column boil_size" (migration needed)

**Step 5: Create Alembic migration**

```bash
cd backend
alembic revision --autogenerate -m "expand recipe schema with beerxml fields"
```

Expected: Creates `backend/alembic/versions/YYYY_MM_DD_HHMM_expand_recipe_schema.py`

Review migration file - should add all new columns to recipes table.

**Step 6: Apply migration**

```bash
cd backend
alembic upgrade head
```

Expected: Migration applies successfully

**Step 7: Run test again**

Run: `pytest backend/tests/test_recipe_models.py::test_recipe_with_expanded_beerxml_fields -v`
Expected: PASS

**Step 8: Commit**

```bash
git add backend/models.py backend/alembic/versions/*.py backend/tests/test_recipe_models.py
git commit -m "feat(recipes): add BeerXML top-level fields to Recipe model"
```

---

### Task 2: Create Fermentable (Grain) Model

**Files:**
- Modify: `backend/models.py` (add after Recipe class)
- Create: `backend/alembic/versions/YYYY_MM_DD_HHMM_add_fermentables_table.py`
- Test: `backend/tests/test_recipe_models.py`

**Step 1: Write failing test for Fermentable model**

```python
# backend/tests/test_recipe_models.py
def test_fermentable_model(db_session):
    """Test Fermentable model stores grain/extract/sugar data."""
    recipe = Recipe(name="Test Recipe")
    db_session.add(recipe)
    db_session.flush()

    fermentable = RecipeFermentable(
        recipe_id=recipe.id,
        name="Pale Malt (2-row) UK",
        type="Grain",
        amount=2.27,  # kg
        yield_percent=78.0,
        color=3.0,  # Lovibond
        add_after_boil=False,
        origin="United Kingdom",
        supplier="Fussybrewer Malting",
        notes="All purpose base malt for English styles",
        coarse_fine_diff=1.5,
        moisture=4.0,
        diastatic_power=45.0,
        protein=10.2,
        max_in_batch=100.0,
        recommend_mash=True,
    )
    db_session.add(fermentable)
    db_session.commit()

    retrieved = db_session.query(RecipeFermentable).first()
    assert retrieved.name == "Pale Malt (2-row) UK"
    assert retrieved.type == "Grain"
    assert retrieved.amount == 2.27
    assert retrieved.yield_percent == 78.0
    assert retrieved.recommend_mash is True
    assert retrieved.recipe.name == "Test Recipe"
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_recipe_models.py::test_fermentable_model -v`
Expected: FAIL with "name 'RecipeFermentable' is not defined"

**Step 3: Add RecipeFermentable model**

```python
# backend/models.py (add after Recipe class, before Batch class)

class RecipeFermentable(Base):
    """Fermentable ingredients (grains, extracts, sugars) in a recipe."""
    __tablename__ = "recipe_fermentables"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # Required BeerXML fields
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # Grain, Sugar, Extract, Dry Extract, Adjunct
    amount: Mapped[float] = mapped_column(nullable=False)  # Kilograms
    yield_percent: Mapped[float] = mapped_column(nullable=False)  # Percent dry yield
    color: Mapped[float] = mapped_column(nullable=False)  # Lovibond/SRM

    # Optional BeerXML fields
    add_after_boil: Mapped[Optional[bool]] = mapped_column()
    origin: Mapped[Optional[str]] = mapped_column(String(100))
    supplier: Mapped[Optional[str]] = mapped_column(String(100))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    coarse_fine_diff: Mapped[Optional[float]] = mapped_column()  # Percent
    moisture: Mapped[Optional[float]] = mapped_column()  # Percent
    diastatic_power: Mapped[Optional[float]] = mapped_column()  # Lintner units
    protein: Mapped[Optional[float]] = mapped_column()  # Percent
    max_in_batch: Mapped[Optional[float]] = mapped_column()  # Percent
    recommend_mash: Mapped[Optional[bool]] = mapped_column()
    ibu_gal_per_lb: Mapped[Optional[float]] = mapped_column()  # For hopped extracts

    # Relationship
    recipe: Mapped["Recipe"] = relationship(back_populates="fermentables")


# Update Recipe class to add relationship
# Add this to Recipe class after line 245:
fermentables: Mapped[list["RecipeFermentable"]] = relationship(
    back_populates="recipe", cascade="all, delete-orphan", order_by="RecipeFermentable.id"
)
```

**Step 4: Run test to verify schema error**

Run: `pytest backend/tests/test_recipe_models.py::test_fermentable_model -v`
Expected: FAIL with "no such table: recipe_fermentables"

**Step 5: Create and apply migration**

```bash
cd backend
alembic revision --autogenerate -m "add recipe_fermentables table"
alembic upgrade head
```

**Step 6: Run test to verify it passes**

Run: `pytest backend/tests/test_recipe_models.py::test_fermentable_model -v`
Expected: PASS

**Step 7: Commit**

```bash
git add backend/models.py backend/alembic/versions/*.py backend/tests/test_recipe_models.py
git commit -m "feat(recipes): add RecipeFermentable model for grain bills"
```

---

### Task 3: Create Hop Model

**Files:**
- Modify: `backend/models.py`
- Create: `backend/alembic/versions/YYYY_MM_DD_HHMM_add_hops_table.py`
- Test: `backend/tests/test_recipe_models.py`

**Step 1: Write failing test for RecipeHop model**

```python
# backend/tests/test_recipe_models.py
def test_recipe_hop_model(db_session):
    """Test RecipeHop model stores hop addition data."""
    recipe = Recipe(name="Test IPA")
    db_session.add(recipe)
    db_session.flush()

    hop = RecipeHop(
        recipe_id=recipe.id,
        name="Cascade",
        alpha=5.5,
        amount=0.028,  # kg
        use="Boil",
        time=60.0,  # minutes
        notes="American aroma hop",
        type="Aroma",
        form="Pellet",
        beta=4.5,
        hsi=30.0,
        origin="USA",
        substitutes="Centennial, Amarillo",
        humulene=25.0,
        caryophyllene=8.0,
        cohumulone=35.0,
        myrcene=50.0,
    )
    db_session.add(hop)
    db_session.commit()

    retrieved = db_session.query(RecipeHop).first()
    assert retrieved.name == "Cascade"
    assert retrieved.alpha == 5.5
    assert retrieved.use == "Boil"
    assert retrieved.time == 60.0
    assert retrieved.recipe.name == "Test IPA"
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_recipe_models.py::test_recipe_hop_model -v`
Expected: FAIL with "name 'RecipeHop' is not defined"

**Step 3: Add RecipeHop model**

```python
# backend/models.py (add after RecipeFermentable)

class RecipeHop(Base):
    """Hop additions in a recipe."""
    __tablename__ = "recipe_hops"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # Required BeerXML fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    alpha: Mapped[float] = mapped_column(nullable=False)  # Percent alpha acids
    amount: Mapped[float] = mapped_column(nullable=False)  # Kilograms
    use: Mapped[str] = mapped_column(String(50), nullable=False)  # Boil, Dry Hop, Mash, First Wort, Aroma
    time: Mapped[float] = mapped_column(nullable=False)  # Minutes (or days for dry hop)

    # Optional BeerXML fields
    notes: Mapped[Optional[str]] = mapped_column(Text)
    type: Mapped[Optional[str]] = mapped_column(String(50))  # Bittering, Aroma, Both
    form: Mapped[Optional[str]] = mapped_column(String(20))  # Pellet, Plug, Leaf
    beta: Mapped[Optional[float]] = mapped_column()  # Percent beta acids
    hsi: Mapped[Optional[float]] = mapped_column()  # Hop Stability Index
    origin: Mapped[Optional[str]] = mapped_column(String(100))
    substitutes: Mapped[Optional[str]] = mapped_column(String(200))
    humulene: Mapped[Optional[float]] = mapped_column()  # Percent
    caryophyllene: Mapped[Optional[float]] = mapped_column()  # Percent
    cohumulone: Mapped[Optional[float]] = mapped_column()  # Percent
    myrcene: Mapped[Optional[float]] = mapped_column()  # Percent

    # Relationship
    recipe: Mapped["Recipe"] = relationship(back_populates="hops")


# Update Recipe class to add relationship
# Add this to Recipe class after fermentables relationship:
hops: Mapped[list["RecipeHop"]] = relationship(
    back_populates="recipe", cascade="all, delete-orphan", order_by="RecipeHop.time.desc()"
)
```

**Step 4: Create and apply migration**

```bash
cd backend
alembic revision --autogenerate -m "add recipe_hops table"
alembic upgrade head
```

**Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_recipe_models.py::test_recipe_hop_model -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/models.py backend/alembic/versions/*.py backend/tests/test_recipe_models.py
git commit -m "feat(recipes): add RecipeHop model for hop schedules"
```

---

### Task 4: Create Yeast, Misc, Water Models

**Files:**
- Modify: `backend/models.py`
- Create: `backend/alembic/versions/YYYY_MM_DD_HHMM_add_yeast_misc_water_tables.py`
- Test: `backend/tests/test_recipe_models.py`

**Step 1: Write failing test for all three models**

```python
# backend/tests/test_recipe_models.py
def test_recipe_yeast_misc_water_models(db_session):
    """Test RecipeYeast, RecipeMisc, RecipeWater models."""
    recipe = Recipe(name="Test Stout")
    db_session.add(recipe)
    db_session.flush()

    # Yeast
    yeast = RecipeYeast(
        recipe_id=recipe.id,
        name="Irish Ale",
        type="Ale",
        form="Liquid",
        amount=0.250,
        amount_is_weight=False,
        laboratory="Wyeast Labs",
        product_id="1084",
        min_temperature=16.7,
        max_temperature=22.2,
        flocculation="Medium",
        attenuation=73.0,
        notes="Dry, fruity flavor",
        best_for="Irish Dry Stouts",
        times_cultured=0,
        max_reuse=5,
        add_to_secondary=False,
    )
    db_session.add(yeast)

    # Misc ingredient
    misc = RecipeMisc(
        recipe_id=recipe.id,
        name="Irish Moss",
        type="Fining",
        use="Boil",
        time=15.0,
        amount=0.010,
        amount_is_weight=True,
        use_for="Clarity",
        notes="Fining agent for clarity",
    )
    db_session.add(misc)

    # Water profile
    water = RecipeWater(
        recipe_id=recipe.id,
        name="Burton on Trent, UK",
        amount=20.0,
        calcium=295.0,
        bicarbonate=300.0,
        sulfate=725.0,
        chloride=25.0,
        sodium=55.0,
        magnesium=45.0,
        ph=8.0,
        notes="Hard water for pale ales",
    )
    db_session.add(water)
    db_session.commit()

    # Verify
    assert db_session.query(RecipeYeast).count() == 1
    assert db_session.query(RecipeMisc).count() == 1
    assert db_session.query(RecipeWater).count() == 1

    retrieved_yeast = db_session.query(RecipeYeast).first()
    assert retrieved_yeast.name == "Irish Ale"
    assert retrieved_yeast.attenuation == 73.0
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_recipe_models.py::test_recipe_yeast_misc_water_models -v`
Expected: FAIL with "name 'RecipeYeast' is not defined"

**Step 3: Add RecipeYeast, RecipeMisc, RecipeWater models**

```python
# backend/models.py (add after RecipeHop)

class RecipeYeast(Base):
    """Yeast strains used in a recipe."""
    __tablename__ = "recipe_yeasts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # Required BeerXML fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # Ale, Lager, Wheat, Wine, Champagne
    form: Mapped[str] = mapped_column(String(20), nullable=False)  # Liquid, Dry, Slant, Culture
    amount: Mapped[float] = mapped_column(nullable=False)  # Liters or kg

    # Optional BeerXML fields
    amount_is_weight: Mapped[Optional[bool]] = mapped_column()
    laboratory: Mapped[Optional[str]] = mapped_column(String(100))
    product_id: Mapped[Optional[str]] = mapped_column(String(50))
    min_temperature: Mapped[Optional[float]] = mapped_column()  # Celsius
    max_temperature: Mapped[Optional[float]] = mapped_column()  # Celsius
    flocculation: Mapped[Optional[str]] = mapped_column(String(20))  # Low, Medium, High, Very High
    attenuation: Mapped[Optional[float]] = mapped_column()  # Percent
    notes: Mapped[Optional[str]] = mapped_column(Text)
    best_for: Mapped[Optional[str]] = mapped_column(String(200))
    times_cultured: Mapped[Optional[int]] = mapped_column()
    max_reuse: Mapped[Optional[int]] = mapped_column()
    add_to_secondary: Mapped[Optional[bool]] = mapped_column()

    # Relationship
    recipe: Mapped["Recipe"] = relationship(back_populates="yeasts")


class RecipeMisc(Base):
    """Miscellaneous ingredients (spices, finings, water agents)."""
    __tablename__ = "recipe_miscs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # Required BeerXML fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # Spice, Fining, Water Agent, Herb, Flavor, Other
    use: Mapped[str] = mapped_column(String(50), nullable=False)  # Boil, Mash, Primary, Secondary, Bottling
    time: Mapped[float] = mapped_column(nullable=False)  # Minutes
    amount: Mapped[float] = mapped_column(nullable=False)  # Liters or kg

    # Optional BeerXML fields
    amount_is_weight: Mapped[Optional[bool]] = mapped_column()
    use_for: Mapped[Optional[str]] = mapped_column(String(200))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationship
    recipe: Mapped["Recipe"] = relationship(back_populates="miscs")


class RecipeWater(Base):
    """Water profiles used in a recipe."""
    __tablename__ = "recipe_waters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # Required BeerXML fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[float] = mapped_column(nullable=False)  # Liters
    calcium: Mapped[float] = mapped_column(nullable=False)  # ppm
    bicarbonate: Mapped[float] = mapped_column(nullable=False)  # ppm
    sulfate: Mapped[float] = mapped_column(nullable=False)  # ppm
    chloride: Mapped[float] = mapped_column(nullable=False)  # ppm
    sodium: Mapped[float] = mapped_column(nullable=False)  # ppm
    magnesium: Mapped[float] = mapped_column(nullable=False)  # ppm

    # Optional BeerXML fields
    ph: Mapped[Optional[float]] = mapped_column()
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationship
    recipe: Mapped["Recipe"] = relationship(back_populates="waters")


# Update Recipe class to add relationships
# Add these to Recipe class after hops relationship:
yeasts: Mapped[list["RecipeYeast"]] = relationship(
    back_populates="recipe", cascade="all, delete-orphan"
)
miscs: Mapped[list["RecipeMisc"]] = relationship(
    back_populates="recipe", cascade="all, delete-orphan"
)
waters: Mapped[list["RecipeWater"]] = relationship(
    back_populates="recipe", cascade="all, delete-orphan"
)
```

**Step 4: Create and apply migration**

```bash
cd backend
alembic revision --autogenerate -m "add recipe_yeasts, recipe_miscs, recipe_waters tables"
alembic upgrade head
```

**Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_recipe_models.py::test_recipe_yeast_misc_water_models -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/models.py backend/alembic/versions/*.py backend/tests/test_recipe_models.py
git commit -m "feat(recipes): add RecipeYeast, RecipeMisc, RecipeWater models"
```

---

### Task 5: Create Mash Profile and Mash Step Models

**Files:**
- Modify: `backend/models.py`
- Create: `backend/alembic/versions/YYYY_MM_DD_HHMM_add_mash_tables.py`
- Test: `backend/tests/test_recipe_models.py`

**Step 1: Write failing test for mash models**

```python
# backend/tests/test_recipe_models.py
def test_mash_profile_and_steps(db_session):
    """Test RecipeMashProfile and RecipeMashStep models."""
    recipe = Recipe(name="Test All-Grain")
    db_session.add(recipe)
    db_session.flush()

    mash = RecipeMashProfile(
        recipe_id=recipe.id,
        name="Single Step Infusion, 68C",
        grain_temp=22.0,
        tun_temp=22.0,
        sparge_temp=78.0,
        ph=5.4,
        tun_weight=2.0,
        tun_specific_heat=0.3,
        equip_adjust=False,
        notes="Simple single infusion mash",
    )
    db_session.add(mash)
    db_session.flush()

    step = RecipeMashStep(
        mash_profile_id=mash.id,
        name="Conversion Step, 68C",
        type="Infusion",
        infuse_amount=10.0,
        step_temp=68.0,
        step_time=60.0,
        ramp_time=10.0,
        end_temp=66.0,
    )
    db_session.add(step)
    db_session.commit()

    # Verify
    retrieved_mash = db_session.query(RecipeMashProfile).first()
    assert retrieved_mash.name == "Single Step Infusion, 68C"
    assert len(retrieved_mash.steps) == 1
    assert retrieved_mash.steps[0].name == "Conversion Step, 68C"
    assert retrieved_mash.steps[0].step_temp == 68.0
    assert retrieved_mash.recipe.name == "Test All-Grain"
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_recipe_models.py::test_mash_profile_and_steps -v`
Expected: FAIL with "name 'RecipeMashProfile' is not defined"

**Step 3: Add RecipeMashProfile and RecipeMashStep models**

```python
# backend/models.py (add after RecipeWater)

class RecipeMashProfile(Base):
    """Mash profile for all-grain recipes."""
    __tablename__ = "recipe_mash_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # Required BeerXML fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    grain_temp: Mapped[float] = mapped_column(nullable=False)  # Celsius

    # Optional BeerXML fields
    notes: Mapped[Optional[str]] = mapped_column(Text)
    tun_temp: Mapped[Optional[float]] = mapped_column()  # Celsius
    sparge_temp: Mapped[Optional[float]] = mapped_column()  # Celsius
    ph: Mapped[Optional[float]] = mapped_column()
    tun_weight: Mapped[Optional[float]] = mapped_column()  # Kilograms
    tun_specific_heat: Mapped[Optional[float]] = mapped_column()  # cal/gram-deg C
    equip_adjust: Mapped[Optional[bool]] = mapped_column()

    # Relationships
    recipe: Mapped["Recipe"] = relationship(back_populates="mash_profile")
    steps: Mapped[list["RecipeMashStep"]] = relationship(
        back_populates="mash_profile", cascade="all, delete-orphan", order_by="RecipeMashStep.id"
    )


class RecipeMashStep(Base):
    """Individual mash step within a mash profile."""
    __tablename__ = "recipe_mash_steps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    mash_profile_id: Mapped[int] = mapped_column(ForeignKey("recipe_mash_profiles.id", ondelete="CASCADE"), nullable=False)

    # Required BeerXML fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # Infusion, Temperature, Decoction
    step_temp: Mapped[float] = mapped_column(nullable=False)  # Celsius
    step_time: Mapped[float] = mapped_column(nullable=False)  # Minutes

    # Optional BeerXML fields (infuse_amount required for Infusion type)
    infuse_amount: Mapped[Optional[float]] = mapped_column()  # Liters
    ramp_time: Mapped[Optional[float]] = mapped_column()  # Minutes
    end_temp: Mapped[Optional[float]] = mapped_column()  # Celsius

    # Relationship
    mash_profile: Mapped["RecipeMashProfile"] = relationship(back_populates="steps")


# Update Recipe class to add relationship
# Add this to Recipe class after waters relationship:
mash_profile: Mapped[Optional["RecipeMashProfile"]] = relationship(
    back_populates="recipe", cascade="all, delete-orphan", uselist=False
)
```

**Step 4: Create and apply migration**

```bash
cd backend
alembic revision --autogenerate -m "add recipe_mash_profiles and recipe_mash_steps tables"
alembic upgrade head
```

**Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_recipe_models.py::test_mash_profile_and_steps -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/models.py backend/alembic/versions/*.py backend/tests/test_recipe_models.py
git commit -m "feat(recipes): add RecipeMashProfile and RecipeMashStep models"
```

---

## Phase 2: BeerXML Parser Expansion

### Task 6: Expand BeerXML Parser - Fermentables

**Files:**
- Modify: `backend/services/beerxml_parser.py`
- Test: `backend/tests/test_beerxml_parser.py`

**Step 1: Write failing test for fermentables parsing**

```python
# backend/tests/test_beerxml_parser.py
def test_parse_fermentables():
    """Test parsing fermentables from BeerXML."""
    xml = """<?xml version="1.0" encoding="ISO-8859-1"?>
    <RECIPES>
        <RECIPE>
            <NAME>Test Recipe</NAME>
            <VERSION>1</VERSION>
            <TYPE>All Grain</TYPE>
            <BREWER>Test Brewer</BREWER>
            <BATCH_SIZE>20.0</BATCH_SIZE>
            <BOIL_SIZE>25.0</BOIL_SIZE>
            <BOIL_TIME>60.0</BOIL_TIME>
            <EFFICIENCY>75.0</EFFICIENCY>
            <FERMENTABLES>
                <FERMENTABLE>
                    <NAME>Pale Malt (2 row) UK</NAME>
                    <VERSION>1</VERSION>
                    <TYPE>Grain</TYPE>
                    <AMOUNT>5.0</AMOUNT>
                    <YIELD>78.0</YIELD>
                    <COLOR>3.0</COLOR>
                    <ADD_AFTER_BOIL>FALSE</ADD_AFTER_BOIL>
                    <ORIGIN>United Kingdom</ORIGIN>
                    <SUPPLIER>Fussybrewer Malting</SUPPLIER>
                    <NOTES>All purpose base malt</NOTES>
                    <COARSE_FINE_DIFF>1.5</COARSE_FINE_DIFF>
                    <MOISTURE>4.0</MOISTURE>
                    <DIASTATIC_POWER>45.0</DIASTATIC_POWER>
                    <PROTEIN>10.2</PROTEIN>
                    <MAX_IN_BATCH>100.0</MAX_IN_BATCH>
                    <RECOMMEND_MASH>TRUE</RECOMMEND_MASH>
                </FERMENTABLE>
                <FERMENTABLE>
                    <NAME>Crystal 40 L</NAME>
                    <VERSION>1</VERSION>
                    <TYPE>Grain</TYPE>
                    <AMOUNT>0.5</AMOUNT>
                    <YIELD>74.0</YIELD>
                    <COLOR>40.0</COLOR>
                </FERMENTABLE>
            </FERMENTABLES>
        </RECIPE>
    </RECIPES>
    """

    from backend.services.beerxml_parser import parse_beerxml

    recipes = parse_beerxml(xml)
    assert len(recipes) == 1

    recipe = recipes[0]
    assert len(recipe.fermentables) == 2

    pale_malt = recipe.fermentables[0]
    assert pale_malt.name == "Pale Malt (2 row) UK"
    assert pale_malt.type == "Grain"
    assert pale_malt.amount == 5.0
    assert pale_malt.yield_percent == 78.0
    assert pale_malt.color == 3.0
    assert pale_malt.add_after_boil is False
    assert pale_malt.origin == "United Kingdom"
    assert pale_malt.supplier == "Fussybrewer Malting"
    assert pale_malt.recommend_mash is True

    crystal = recipe.fermentables[1]
    assert crystal.name == "Crystal 40 L"
    assert crystal.amount == 0.5
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_beerxml_parser.py::test_parse_fermentables -v`
Expected: FAIL with "'ParsedRecipe' object has no attribute 'fermentables'"

**Step 3: Add ParsedFermentable dataclass and parsing logic**

```python
# backend/services/beerxml_parser.py

# Add after ParsedYeast dataclass:
@dataclass
class ParsedFermentable:
    """Fermentable ingredient extracted from BeerXML."""
    name: str
    type: str
    amount: float
    yield_percent: float
    color: float
    add_after_boil: Optional[bool] = None
    origin: Optional[str] = None
    supplier: Optional[str] = None
    notes: Optional[str] = None
    coarse_fine_diff: Optional[float] = None
    moisture: Optional[float] = None
    diastatic_power: Optional[float] = None
    protein: Optional[float] = None
    max_in_batch: Optional[float] = None
    recommend_mash: Optional[bool] = None
    ibu_gal_per_lb: Optional[float] = None


# Update ParsedRecipe dataclass to include fermentables:
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
    batch_size: Optional[float] = None
    boil_size: Optional[float] = None
    boil_time: Optional[float] = None
    efficiency: Optional[float] = None
    style: Optional[ParsedStyle] = None
    yeast: Optional[ParsedYeast] = None
    fermentables: list[ParsedFermentable] = field(default_factory=list)
    raw_xml: str = ""


# Add helper function to parse boolean:
def _get_bool(elem, tag: str) -> Optional[bool]:
    """Get boolean value of child element."""
    text = _get_text(elem, tag)
    if text:
        return text.upper() == "TRUE"
    return None


# Add parsing function for fermentables:
def _parse_fermentables(recipe_elem) -> list[ParsedFermentable]:
    """Parse all fermentables from a recipe element."""
    fermentables = []

    for ferm_elem in recipe_elem.findall('.//FERMENTABLES/FERMENTABLE'):
        # Required fields
        name = _get_text(ferm_elem, 'NAME')
        type_ = _get_text(ferm_elem, 'TYPE')
        amount = _get_float(ferm_elem, 'AMOUNT')
        yield_pct = _get_float(ferm_elem, 'YIELD')
        color = _get_float(ferm_elem, 'COLOR')

        # Skip if missing required fields
        if not all([name, type_, amount is not None, yield_pct is not None, color is not None]):
            continue

        fermentable = ParsedFermentable(
            name=name,
            type=type_,
            amount=amount,
            yield_percent=yield_pct,
            color=color,
            add_after_boil=_get_bool(ferm_elem, 'ADD_AFTER_BOIL'),
            origin=_get_text(ferm_elem, 'ORIGIN'),
            supplier=_get_text(ferm_elem, 'SUPPLIER'),
            notes=_get_text(ferm_elem, 'NOTES'),
            coarse_fine_diff=_get_float(ferm_elem, 'COARSE_FINE_DIFF'),
            moisture=_get_float(ferm_elem, 'MOISTURE'),
            diastatic_power=_get_float(ferm_elem, 'DIASTATIC_POWER'),
            protein=_get_float(ferm_elem, 'PROTEIN'),
            max_in_batch=_get_float(ferm_elem, 'MAX_IN_BATCH'),
            recommend_mash=_get_bool(ferm_elem, 'RECOMMEND_MASH'),
            ibu_gal_per_lb=_get_float(ferm_elem, 'IBU_GAL_PER_LB'),
        )
        fermentables.append(fermentable)

    return fermentables


# Update _parse_recipe function to call _parse_fermentables:
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
        boil_size=_get_float(elem, 'BOIL_SIZE'),
        boil_time=_get_float(elem, 'BOIL_TIME'),
        efficiency=_get_float(elem, 'EFFICIENCY'),
        raw_xml=raw_xml
    )

    # Parse style (existing code)
    style_elem = elem.find('.//STYLE')
    if style_elem is not None:
        recipe.style = ParsedStyle(
            name=_get_text(style_elem, 'NAME'),
            category=_get_text(style_elem, 'CATEGORY'),
            category_number=_get_text(style_elem, 'CATEGORY_NUMBER'),
            style_letter=_get_text(style_elem, 'STYLE_LETTER'),
            guide=_get_text(style_elem, 'STYLE_GUIDE'),
        )

    # Parse first yeast (existing code)
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

    # Parse fermentables (NEW)
    recipe.fermentables = _parse_fermentables(elem)

    return recipe
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_beerxml_parser.py::test_parse_fermentables -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/services/beerxml_parser.py backend/tests/test_beerxml_parser.py
git commit -m "feat(parser): parse fermentables from BeerXML"
```

---

### Task 7: Expand BeerXML Parser - Hops, Yeasts, Miscs, Waters

**Files:**
- Modify: `backend/services/beerxml_parser.py`
- Test: `backend/tests/test_beerxml_parser.py`

**Step 1: Write failing test for hops, yeasts, miscs, waters**

```python
# backend/tests/test_beerxml_parser.py
def test_parse_all_ingredients():
    """Test parsing hops, yeasts, miscs, waters from BeerXML."""
    xml = """<?xml version="1.0" encoding="ISO-8859-1"?>
    <RECIPES>
        <RECIPE>
            <NAME>Complete Recipe</NAME>
            <VERSION>1</VERSION>
            <TYPE>All Grain</TYPE>
            <BREWER>Test</BREWER>
            <BATCH_SIZE>20.0</BATCH_SIZE>
            <BOIL_SIZE>25.0</BOIL_SIZE>
            <BOIL_TIME>60.0</BOIL_TIME>
            <HOPS>
                <HOP>
                    <NAME>Cascade</NAME>
                    <VERSION>1</VERSION>
                    <ALPHA>5.5</ALPHA>
                    <AMOUNT>0.028</AMOUNT>
                    <USE>Boil</USE>
                    <TIME>60.0</TIME>
                    <FORM>Pellet</FORM>
                    <ORIGIN>USA</ORIGIN>
                </HOP>
            </HOPS>
            <YEASTS>
                <YEAST>
                    <NAME>US-05</NAME>
                    <VERSION>1</VERSION>
                    <TYPE>Ale</TYPE>
                    <FORM>Dry</FORM>
                    <AMOUNT>0.011</AMOUNT>
                    <AMOUNT_IS_WEIGHT>TRUE</AMOUNT_IS_WEIGHT>
                    <ATTENUATION>75.0</ATTENUATION>
                </YEAST>
            </YEASTS>
            <MISCS>
                <MISC>
                    <NAME>Irish Moss</NAME>
                    <VERSION>1</VERSION>
                    <TYPE>Fining</TYPE>
                    <USE>Boil</USE>
                    <TIME>15.0</TIME>
                    <AMOUNT>0.010</AMOUNT>
                    <AMOUNT_IS_WEIGHT>TRUE</AMOUNT_IS_WEIGHT>
                </MISC>
            </MISCS>
            <WATERS>
                <WATER>
                    <NAME>Burton on Trent</NAME>
                    <VERSION>1</VERSION>
                    <AMOUNT>20.0</AMOUNT>
                    <CALCIUM>295.0</CALCIUM>
                    <BICARBONATE>300.0</BICARBONATE>
                    <SULFATE>725.0</SULFATE>
                    <CHLORIDE>25.0</CHLORIDE>
                    <SODIUM>55.0</SODIUM>
                    <MAGNESIUM>45.0</MAGNESIUM>
                    <PH>8.0</PH>
                </WATER>
            </WATERS>
        </RECIPE>
    </RECIPES>
    """

    from backend.services.beerxml_parser import parse_beerxml

    recipes = parse_beerxml(xml)
    recipe = recipes[0]

    # Hops
    assert len(recipe.hops) == 1
    assert recipe.hops[0].name == "Cascade"
    assert recipe.hops[0].alpha == 5.5
    assert recipe.hops[0].use == "Boil"
    assert recipe.hops[0].time == 60.0

    # Yeasts
    assert len(recipe.yeasts) == 1
    assert recipe.yeasts[0].name == "US-05"
    assert recipe.yeasts[0].type == "Ale"
    assert recipe.yeasts[0].form == "Dry"
    assert recipe.yeasts[0].amount_is_weight is True

    # Miscs
    assert len(recipe.miscs) == 1
    assert recipe.miscs[0].name == "Irish Moss"
    assert recipe.miscs[0].type == "Fining"

    # Waters
    assert len(recipe.waters) == 1
    assert recipe.waters[0].name == "Burton on Trent"
    assert recipe.waters[0].calcium == 295.0
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_beerxml_parser.py::test_parse_all_ingredients -v`
Expected: FAIL with "'ParsedRecipe' object has no attribute 'hops'"

**Step 3: Add dataclasses and parsing functions**

```python
# backend/services/beerxml_parser.py

# Add dataclasses after ParsedFermentable:

@dataclass
class ParsedHop:
    """Hop addition extracted from BeerXML."""
    name: str
    alpha: float
    amount: float
    use: str
    time: float
    notes: Optional[str] = None
    type: Optional[str] = None
    form: Optional[str] = None
    beta: Optional[float] = None
    hsi: Optional[float] = None
    origin: Optional[str] = None
    substitutes: Optional[str] = None
    humulene: Optional[float] = None
    caryophyllene: Optional[float] = None
    cohumulone: Optional[float] = None
    myrcene: Optional[float] = None


@dataclass
class ParsedYeastFull:
    """Complete yeast data extracted from BeerXML."""
    name: str
    type: str
    form: str
    amount: float
    amount_is_weight: Optional[bool] = None
    laboratory: Optional[str] = None
    product_id: Optional[str] = None
    min_temperature: Optional[float] = None
    max_temperature: Optional[float] = None
    flocculation: Optional[str] = None
    attenuation: Optional[float] = None
    notes: Optional[str] = None
    best_for: Optional[str] = None
    times_cultured: Optional[int] = None
    max_reuse: Optional[int] = None
    add_to_secondary: Optional[bool] = None


@dataclass
class ParsedMisc:
    """Miscellaneous ingredient extracted from BeerXML."""
    name: str
    type: str
    use: str
    time: float
    amount: float
    amount_is_weight: Optional[bool] = None
    use_for: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class ParsedWater:
    """Water profile extracted from BeerXML."""
    name: str
    amount: float
    calcium: float
    bicarbonate: float
    sulfate: float
    chloride: float
    sodium: float
    magnesium: float
    ph: Optional[float] = None
    notes: Optional[str] = None


# Update ParsedRecipe to include all ingredient lists:
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
    batch_size: Optional[float] = None
    boil_size: Optional[float] = None
    boil_time: Optional[float] = None
    efficiency: Optional[float] = None
    style: Optional[ParsedStyle] = None
    yeast: Optional[ParsedYeast] = None  # Keep for backward compat (first yeast)
    fermentables: list[ParsedFermentable] = field(default_factory=list)
    hops: list[ParsedHop] = field(default_factory=list)
    yeasts: list[ParsedYeastFull] = field(default_factory=list)
    miscs: list[ParsedMisc] = field(default_factory=list)
    waters: list[ParsedWater] = field(default_factory=list)
    raw_xml: str = ""


# Add parsing functions:

def _parse_hops(recipe_elem) -> list[ParsedHop]:
    """Parse all hops from a recipe element."""
    hops = []
    for hop_elem in recipe_elem.findall('.//HOPS/HOP'):
        name = _get_text(hop_elem, 'NAME')
        alpha = _get_float(hop_elem, 'ALPHA')
        amount = _get_float(hop_elem, 'AMOUNT')
        use = _get_text(hop_elem, 'USE')
        time = _get_float(hop_elem, 'TIME')

        if not all([name, alpha is not None, amount is not None, use, time is not None]):
            continue

        hop = ParsedHop(
            name=name,
            alpha=alpha,
            amount=amount,
            use=use,
            time=time,
            notes=_get_text(hop_elem, 'NOTES'),
            type=_get_text(hop_elem, 'TYPE'),
            form=_get_text(hop_elem, 'FORM'),
            beta=_get_float(hop_elem, 'BETA'),
            hsi=_get_float(hop_elem, 'HSI'),
            origin=_get_text(hop_elem, 'ORIGIN'),
            substitutes=_get_text(hop_elem, 'SUBSTITUTES'),
            humulene=_get_float(hop_elem, 'HUMULENE'),
            caryophyllene=_get_float(hop_elem, 'CARYOPHYLLENE'),
            cohumulone=_get_float(hop_elem, 'COHUMULONE'),
            myrcene=_get_float(hop_elem, 'MYRCENE'),
        )
        hops.append(hop)

    return hops


def _get_int(elem, tag: str) -> Optional[int]:
    """Get integer value of child element."""
    text = _get_text(elem, tag)
    if text:
        try:
            return int(text)
        except ValueError:
            return None
    return None


def _parse_yeasts(recipe_elem) -> list[ParsedYeastFull]:
    """Parse all yeasts from a recipe element."""
    yeasts = []
    for yeast_elem in recipe_elem.findall('.//YEASTS/YEAST'):
        name = _get_text(yeast_elem, 'NAME')
        type_ = _get_text(yeast_elem, 'TYPE')
        form = _get_text(yeast_elem, 'FORM')
        amount = _get_float(yeast_elem, 'AMOUNT')

        if not all([name, type_, form, amount is not None]):
            continue

        yeast = ParsedYeastFull(
            name=name,
            type=type_,
            form=form,
            amount=amount,
            amount_is_weight=_get_bool(yeast_elem, 'AMOUNT_IS_WEIGHT'),
            laboratory=_get_text(yeast_elem, 'LABORATORY'),
            product_id=_get_text(yeast_elem, 'PRODUCT_ID'),
            min_temperature=_get_float(yeast_elem, 'MIN_TEMPERATURE'),
            max_temperature=_get_float(yeast_elem, 'MAX_TEMPERATURE'),
            flocculation=_get_text(yeast_elem, 'FLOCCULATION'),
            attenuation=_get_float(yeast_elem, 'ATTENUATION'),
            notes=_get_text(yeast_elem, 'NOTES'),
            best_for=_get_text(yeast_elem, 'BEST_FOR'),
            times_cultured=_get_int(yeast_elem, 'TIMES_CULTURED'),
            max_reuse=_get_int(yeast_elem, 'MAX_REUSE'),
            add_to_secondary=_get_bool(yeast_elem, 'ADD_TO_SECONDARY'),
        )
        yeasts.append(yeast)

    return yeasts


def _parse_miscs(recipe_elem) -> list[ParsedMisc]:
    """Parse all misc ingredients from a recipe element."""
    miscs = []
    for misc_elem in recipe_elem.findall('.//MISCS/MISC'):
        name = _get_text(misc_elem, 'NAME')
        type_ = _get_text(misc_elem, 'TYPE')
        use = _get_text(misc_elem, 'USE')
        time = _get_float(misc_elem, 'TIME')
        amount = _get_float(misc_elem, 'AMOUNT')

        if not all([name, type_, use, time is not None, amount is not None]):
            continue

        misc = ParsedMisc(
            name=name,
            type=type_,
            use=use,
            time=time,
            amount=amount,
            amount_is_weight=_get_bool(misc_elem, 'AMOUNT_IS_WEIGHT'),
            use_for=_get_text(misc_elem, 'USE_FOR'),
            notes=_get_text(misc_elem, 'NOTES'),
        )
        miscs.append(misc)

    return miscs


def _parse_waters(recipe_elem) -> list[ParsedWater]:
    """Parse all water profiles from a recipe element."""
    waters = []
    for water_elem in recipe_elem.findall('.//WATERS/WATER'):
        name = _get_text(water_elem, 'NAME')
        amount = _get_float(water_elem, 'AMOUNT')
        calcium = _get_float(water_elem, 'CALCIUM')
        bicarbonate = _get_float(water_elem, 'BICARBONATE')
        sulfate = _get_float(water_elem, 'SULFATE')
        chloride = _get_float(water_elem, 'CHLORIDE')
        sodium = _get_float(water_elem, 'SODIUM')
        magnesium = _get_float(water_elem, 'MAGNESIUM')

        if not all([
            name, amount is not None, calcium is not None, bicarbonate is not None,
            sulfate is not None, chloride is not None, sodium is not None, magnesium is not None
        ]):
            continue

        water = ParsedWater(
            name=name,
            amount=amount,
            calcium=calcium,
            bicarbonate=bicarbonate,
            sulfate=sulfate,
            chloride=chloride,
            sodium=sodium,
            magnesium=magnesium,
            ph=_get_float(water_elem, 'PH'),
            notes=_get_text(water_elem, 'NOTES'),
        )
        waters.append(water)

    return waters


# Update _parse_recipe to call all parsing functions:
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
        boil_size=_get_float(elem, 'BOIL_SIZE'),
        boil_time=_get_float(elem, 'BOIL_TIME'),
        efficiency=_get_float(elem, 'EFFICIENCY'),
        raw_xml=raw_xml
    )

    # Parse style (existing)
    style_elem = elem.find('.//STYLE')
    if style_elem is not None:
        recipe.style = ParsedStyle(
            name=_get_text(style_elem, 'NAME'),
            category=_get_text(style_elem, 'CATEGORY'),
            category_number=_get_text(style_elem, 'CATEGORY_NUMBER'),
            style_letter=_get_text(style_elem, 'STYLE_LETTER'),
            guide=_get_text(style_elem, 'STYLE_GUIDE'),
        )

    # Parse first yeast for backward compat (existing)
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

    # Parse all ingredient lists (NEW)
    recipe.fermentables = _parse_fermentables(elem)
    recipe.hops = _parse_hops(elem)
    recipe.yeasts = _parse_yeasts(elem)
    recipe.miscs = _parse_miscs(elem)
    recipe.waters = _parse_waters(elem)

    return recipe
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_beerxml_parser.py::test_parse_all_ingredients -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/services/beerxml_parser.py backend/tests/test_beerxml_parser.py
git commit -m "feat(parser): parse hops, yeasts, miscs, waters from BeerXML"
```

---

### Task 8: Expand BeerXML Parser - Mash Profiles

**Files:**
- Modify: `backend/services/beerxml_parser.py`
- Test: `backend/tests/test_beerxml_parser.py`

**Step 1: Write failing test for mash profile parsing**

```python
# backend/tests/test_beerxml_parser.py
def test_parse_mash_profile():
    """Test parsing mash profile and steps from BeerXML."""
    xml = """<?xml version="1.0" encoding="ISO-8859-1"?>
    <RECIPES>
        <RECIPE>
            <NAME>All Grain Test</NAME>
            <VERSION>1</VERSION>
            <TYPE>All Grain</TYPE>
            <BREWER>Test</BREWER>
            <BATCH_SIZE>20.0</BATCH_SIZE>
            <BOIL_SIZE>25.0</BOIL_SIZE>
            <BOIL_TIME>60.0</BOIL_TIME>
            <MASH>
                <NAME>Single Step Infusion, 68C</NAME>
                <VERSION>1</VERSION>
                <GRAIN_TEMP>22.0</GRAIN_TEMP>
                <TUN_TEMP>22.0</TUN_TEMP>
                <SPARGE_TEMP>78.0</SPARGE_TEMP>
                <PH>5.4</PH>
                <TUN_WEIGHT>2.0</TUN_WEIGHT>
                <TUN_SPECIFIC_HEAT>0.3</TUN_SPECIFIC_HEAT>
                <EQUIP_ADJUST>FALSE</EQUIP_ADJUST>
                <NOTES>Simple single infusion</NOTES>
                <MASH_STEPS>
                    <MASH_STEP>
                        <NAME>Conversion Step, 68C</NAME>
                        <VERSION>1</VERSION>
                        <TYPE>Infusion</TYPE>
                        <INFUSE_AMOUNT>10.0</INFUSE_AMOUNT>
                        <STEP_TEMP>68.0</STEP_TEMP>
                        <STEP_TIME>60.0</STEP_TIME>
                        <RAMP_TIME>10.0</RAMP_TIME>
                        <END_TEMP>66.0</END_TEMP>
                    </MASH_STEP>
                    <MASH_STEP>
                        <NAME>Mash Out</NAME>
                        <VERSION>1</VERSION>
                        <TYPE>Temperature</TYPE>
                        <STEP_TEMP>78.0</STEP_TEMP>
                        <STEP_TIME>10.0</STEP_TIME>
                    </MASH_STEP>
                </MASH_STEPS>
            </MASH>
        </RECIPE>
    </RECIPES>
    """

    from backend.services.beerxml_parser import parse_beerxml

    recipes = parse_beerxml(xml)
    recipe = recipes[0]

    assert recipe.mash_profile is not None
    assert recipe.mash_profile.name == "Single Step Infusion, 68C"
    assert recipe.mash_profile.grain_temp == 22.0
    assert recipe.mash_profile.sparge_temp == 78.0
    assert recipe.mash_profile.equip_adjust is False

    assert len(recipe.mash_profile.steps) == 2

    step1 = recipe.mash_profile.steps[0]
    assert step1.name == "Conversion Step, 68C"
    assert step1.type == "Infusion"
    assert step1.step_temp == 68.0
    assert step1.step_time == 60.0
    assert step1.infuse_amount == 10.0

    step2 = recipe.mash_profile.steps[1]
    assert step2.name == "Mash Out"
    assert step2.type == "Temperature"
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_beerxml_parser.py::test_parse_mash_profile -v`
Expected: FAIL with "'ParsedRecipe' object has no attribute 'mash_profile'"

**Step 3: Add mash profile dataclasses and parsing**

```python
# backend/services/beerxml_parser.py

# Add dataclasses after ParsedWater:

@dataclass
class ParsedMashStep:
    """Mash step extracted from BeerXML."""
    name: str
    type: str
    step_temp: float
    step_time: float
    infuse_amount: Optional[float] = None
    ramp_time: Optional[float] = None
    end_temp: Optional[float] = None


@dataclass
class ParsedMashProfile:
    """Mash profile extracted from BeerXML."""
    name: str
    grain_temp: float
    notes: Optional[str] = None
    tun_temp: Optional[float] = None
    sparge_temp: Optional[float] = None
    ph: Optional[float] = None
    tun_weight: Optional[float] = None
    tun_specific_heat: Optional[float] = None
    equip_adjust: Optional[bool] = None
    steps: list[ParsedMashStep] = field(default_factory=list)


# Update ParsedRecipe to include mash profile:
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
    batch_size: Optional[float] = None
    boil_size: Optional[float] = None
    boil_time: Optional[float] = None
    efficiency: Optional[float] = None
    style: Optional[ParsedStyle] = None
    yeast: Optional[ParsedYeast] = None
    fermentables: list[ParsedFermentable] = field(default_factory=list)
    hops: list[ParsedHop] = field(default_factory=list)
    yeasts: list[ParsedYeastFull] = field(default_factory=list)
    miscs: list[ParsedMisc] = field(default_factory=list)
    waters: list[ParsedWater] = field(default_factory=list)
    mash_profile: Optional[ParsedMashProfile] = None
    raw_xml: str = ""


# Add parsing function:

def _parse_mash_profile(recipe_elem) -> Optional[ParsedMashProfile]:
    """Parse mash profile from a recipe element."""
    mash_elem = recipe_elem.find('.//MASH')
    if mash_elem is None:
        return None

    name = _get_text(mash_elem, 'NAME')
    grain_temp = _get_float(mash_elem, 'GRAIN_TEMP')

    if not name or grain_temp is None:
        return None

    profile = ParsedMashProfile(
        name=name,
        grain_temp=grain_temp,
        notes=_get_text(mash_elem, 'NOTES'),
        tun_temp=_get_float(mash_elem, 'TUN_TEMP'),
        sparge_temp=_get_float(mash_elem, 'SPARGE_TEMP'),
        ph=_get_float(mash_elem, 'PH'),
        tun_weight=_get_float(mash_elem, 'TUN_WEIGHT'),
        tun_specific_heat=_get_float(mash_elem, 'TUN_SPECIFIC_HEAT'),
        equip_adjust=_get_bool(mash_elem, 'EQUIP_ADJUST'),
    )

    # Parse mash steps
    for step_elem in mash_elem.findall('.//MASH_STEPS/MASH_STEP'):
        step_name = _get_text(step_elem, 'NAME')
        step_type = _get_text(step_elem, 'TYPE')
        step_temp = _get_float(step_elem, 'STEP_TEMP')
        step_time = _get_float(step_elem, 'STEP_TIME')

        if not all([step_name, step_type, step_temp is not None, step_time is not None]):
            continue

        step = ParsedMashStep(
            name=step_name,
            type=step_type,
            step_temp=step_temp,
            step_time=step_time,
            infuse_amount=_get_float(step_elem, 'INFUSE_AMOUNT'),
            ramp_time=_get_float(step_elem, 'RAMP_TIME'),
            end_temp=_get_float(step_elem, 'END_TEMP'),
        )
        profile.steps.append(step)

    return profile


# Update _parse_recipe to call _parse_mash_profile:
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
        boil_size=_get_float(elem, 'BOIL_SIZE'),
        boil_time=_get_float(elem, 'BOIL_TIME'),
        efficiency=_get_float(elem, 'EFFICIENCY'),
        raw_xml=raw_xml
    )

    # Parse style (existing)
    style_elem = elem.find('.//STYLE')
    if style_elem is not None:
        recipe.style = ParsedStyle(
            name=_get_text(style_elem, 'NAME'),
            category=_get_text(style_elem, 'CATEGORY'),
            category_number=_get_text(style_elem, 'CATEGORY_NUMBER'),
            style_letter=_get_text(style_elem, 'STYLE_LETTER'),
            guide=_get_text(style_elem, 'STYLE_GUIDE'),
        )

    # Parse first yeast for backward compat (existing)
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

    # Parse all ingredient lists (existing)
    recipe.fermentables = _parse_fermentables(elem)
    recipe.hops = _parse_hops(elem)
    recipe.yeasts = _parse_yeasts(elem)
    recipe.miscs = _parse_miscs(elem)
    recipe.waters = _parse_waters(elem)

    # Parse mash profile (NEW)
    recipe.mash_profile = _parse_mash_profile(elem)

    return recipe
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_beerxml_parser.py::test_parse_mash_profile -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/services/beerxml_parser.py backend/tests/test_beerxml_parser.py
git commit -m "feat(parser): parse mash profiles from BeerXML"
```

---

## Phase 3: Recipe Import Integration

### Task 9: Update Recipe Import to Save All Data

**Files:**
- Modify: `backend/routers/recipes.py`
- Test: `backend/tests/test_recipes_api.py`

**Step 1: Write failing integration test**

```python
# backend/tests/test_recipes_api.py
def test_import_complete_beerxml(client, db_session):
    """Test importing BeerXML saves all ingredient data."""
    xml_content = """<?xml version="1.0" encoding="ISO-8859-1"?>
    <RECIPES>
        <RECIPE>
            <NAME>Complete Test Recipe</NAME>
            <VERSION>1</VERSION>
            <TYPE>All Grain</TYPE>
            <BREWER>Test Brewer</BREWER>
            <BATCH_SIZE>20.0</BATCH_SIZE>
            <BOIL_SIZE>25.0</BOIL_SIZE>
            <BOIL_TIME>60.0</BOIL_TIME>
            <EFFICIENCY>75.0</EFFICIENCY>
            <FERMENTABLES>
                <FERMENTABLE>
                    <NAME>Pale Malt</NAME>
                    <VERSION>1</VERSION>
                    <TYPE>Grain</TYPE>
                    <AMOUNT>5.0</AMOUNT>
                    <YIELD>78.0</YIELD>
                    <COLOR>3.0</COLOR>
                </FERMENTABLE>
            </FERMENTABLES>
            <HOPS>
                <HOP>
                    <NAME>Cascade</NAME>
                    <VERSION>1</VERSION>
                    <ALPHA>5.5</ALPHA>
                    <AMOUNT>0.028</AMOUNT>
                    <USE>Boil</USE>
                    <TIME>60.0</TIME>
                </HOP>
            </HOPS>
            <YEASTS>
                <YEAST>
                    <NAME>US-05</NAME>
                    <VERSION>1</VERSION>
                    <TYPE>Ale</TYPE>
                    <FORM>Dry</FORM>
                    <AMOUNT>0.011</AMOUNT>
                </YEAST>
            </YEASTS>
        </RECIPE>
    </RECIPES>
    """

    # Upload file
    files = {"file": ("recipe.xml", xml_content.encode(), "application/xml")}
    response = client.post("/api/recipes/import", files=files)
    assert response.status_code == 200

    recipes = response.json()
    assert len(recipes) == 1
    recipe_id = recipes[0]["id"]

    # Verify recipe was saved with all data
    from backend.models import Recipe, RecipeFermentable, RecipeHop, RecipeYeast

    recipe = db_session.query(Recipe).filter_by(id=recipe_id).first()
    assert recipe is not None
    assert recipe.boil_size == 25.0
    assert recipe.efficiency == 75.0

    # Check fermentables
    fermentables = db_session.query(RecipeFermentable).filter_by(recipe_id=recipe_id).all()
    assert len(fermentables) == 1
    assert fermentables[0].name == "Pale Malt"

    # Check hops
    hops = db_session.query(RecipeHop).filter_by(recipe_id=recipe_id).all()
    assert len(hops) == 1
    assert hops[0].name == "Cascade"

    # Check yeasts
    yeasts = db_session.query(RecipeYeast).filter_by(recipe_id=recipe_id).all()
    assert len(yeasts) == 1
    assert yeasts[0].name == "US-05"
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_recipes_api.py::test_import_complete_beerxml -v`
Expected: FAIL (recipe fields not populated, no ingredient records created)

**Step 3: Update import_beerxml endpoint**

```python
# backend/routers/recipes.py
# Find the import_beerxml function and update it:

@router.post("/import", response_model=list[RecipeResponse])
async def import_beerxml(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
):
    """Import recipes from a BeerXML file."""
    # ... existing validation code ...

    # Parse BeerXML
    parsed_recipes = parse_beerxml(xml_content)

    # Create Recipe records with full data
    saved_recipes = []
    for parsed in parsed_recipes:
        # Create Recipe with expanded fields
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
            boil_size=parsed.boil_size,
            boil_time=parsed.boil_time,
            efficiency=parsed.efficiency,
            beerxml_content=parsed.raw_xml,
        )

        # Add yeast info (first yeast for backward compat)
        if parsed.yeast:
            recipe.yeast_name = parsed.yeast.name
            recipe.yeast_lab = parsed.yeast.lab
            recipe.yeast_product_id = parsed.yeast.product_id
            recipe.yeast_temp_min = parsed.yeast.temp_min
            recipe.yeast_temp_max = parsed.yeast.temp_max
            recipe.yeast_attenuation = parsed.yeast.attenuation

        db.add(recipe)
        await db.flush()  # Get recipe.id

        # Add fermentables
        for ferm in parsed.fermentables:
            fermentable = RecipeFermentable(
                recipe_id=recipe.id,
                name=ferm.name,
                type=ferm.type,
                amount=ferm.amount,
                yield_percent=ferm.yield_percent,
                color=ferm.color,
                add_after_boil=ferm.add_after_boil,
                origin=ferm.origin,
                supplier=ferm.supplier,
                notes=ferm.notes,
                coarse_fine_diff=ferm.coarse_fine_diff,
                moisture=ferm.moisture,
                diastatic_power=ferm.diastatic_power,
                protein=ferm.protein,
                max_in_batch=ferm.max_in_batch,
                recommend_mash=ferm.recommend_mash,
                ibu_gal_per_lb=ferm.ibu_gal_per_lb,
            )
            db.add(fermentable)

        # Add hops
        for hop in parsed.hops:
            hop_record = RecipeHop(
                recipe_id=recipe.id,
                name=hop.name,
                alpha=hop.alpha,
                amount=hop.amount,
                use=hop.use,
                time=hop.time,
                notes=hop.notes,
                type=hop.type,
                form=hop.form,
                beta=hop.beta,
                hsi=hop.hsi,
                origin=hop.origin,
                substitutes=hop.substitutes,
                humulene=hop.humulene,
                caryophyllene=hop.caryophyllene,
                cohumulone=hop.cohumulone,
                myrcene=hop.myrcene,
            )
            db.add(hop_record)

        # Add yeasts
        for yeast in parsed.yeasts:
            yeast_record = RecipeYeast(
                recipe_id=recipe.id,
                name=yeast.name,
                type=yeast.type,
                form=yeast.form,
                amount=yeast.amount,
                amount_is_weight=yeast.amount_is_weight,
                laboratory=yeast.laboratory,
                product_id=yeast.product_id,
                min_temperature=yeast.min_temperature,
                max_temperature=yeast.max_temperature,
                flocculation=yeast.flocculation,
                attenuation=yeast.attenuation,
                notes=yeast.notes,
                best_for=yeast.best_for,
                times_cultured=yeast.times_cultured,
                max_reuse=yeast.max_reuse,
                add_to_secondary=yeast.add_to_secondary,
            )
            db.add(yeast_record)

        # Add miscs
        for misc in parsed.miscs:
            misc_record = RecipeMisc(
                recipe_id=recipe.id,
                name=misc.name,
                type=misc.type,
                use=misc.use,
                time=misc.time,
                amount=misc.amount,
                amount_is_weight=misc.amount_is_weight,
                use_for=misc.use_for,
                notes=misc.notes,
            )
            db.add(misc_record)

        # Add waters
        for water in parsed.waters:
            water_record = RecipeWater(
                recipe_id=recipe.id,
                name=water.name,
                amount=water.amount,
                calcium=water.calcium,
                bicarbonate=water.bicarbonate,
                sulfate=water.sulfate,
                chloride=water.chloride,
                sodium=water.sodium,
                magnesium=water.magnesium,
                ph=water.ph,
                notes=water.notes,
            )
            db.add(water_record)

        # Add mash profile
        if parsed.mash_profile:
            mash = RecipeMashProfile(
                recipe_id=recipe.id,
                name=parsed.mash_profile.name,
                grain_temp=parsed.mash_profile.grain_temp,
                notes=parsed.mash_profile.notes,
                tun_temp=parsed.mash_profile.tun_temp,
                sparge_temp=parsed.mash_profile.sparge_temp,
                ph=parsed.mash_profile.ph,
                tun_weight=parsed.mash_profile.tun_weight,
                tun_specific_heat=parsed.mash_profile.tun_specific_heat,
                equip_adjust=parsed.mash_profile.equip_adjust,
            )
            db.add(mash)
            await db.flush()  # Get mash.id

            for step in parsed.mash_profile.steps:
                step_record = RecipeMashStep(
                    mash_profile_id=mash.id,
                    name=step.name,
                    type=step.type,
                    step_temp=step.step_temp,
                    step_time=step.step_time,
                    infuse_amount=step.infuse_amount,
                    ramp_time=step.ramp_time,
                    end_temp=step.end_temp,
                )
                db.add(step_record)

        saved_recipes.append(recipe)

    await db.commit()

    # Reload with relationships
    result = []
    for recipe in saved_recipes:
        await db.refresh(recipe)
        result.append(recipe)

    return result
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_recipes_api.py::test_import_complete_beerxml -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/routers/recipes.py backend/tests/test_recipes_api.py
git commit -m "feat(import): save complete BeerXML data to database"
```

---

## Phase 4: Update Recipe Response Schema

### Task 10: Expand RecipeResponse Pydantic Model

**Files:**
- Modify: `backend/models.py:547-` (RecipeResponse and related)
- Test: `backend/tests/test_recipes_api.py`

**Step 1: Write failing test for expanded response**

```python
# backend/tests/test_recipes_api.py
def test_get_recipe_returns_full_data(client, db_session):
    """Test GET /api/recipes/{id} returns all ingredient data."""
    # Create recipe with ingredients
    from backend.models import Recipe, RecipeFermentable, RecipeHop

    recipe = Recipe(
        name="IPA",
        boil_size=25.0,
        efficiency=75.0,
    )
    db_session.add(recipe)
    db_session.flush()

    ferm = RecipeFermentable(
        recipe_id=recipe.id,
        name="Pale Malt",
        type="Grain",
        amount=5.0,
        yield_percent=78.0,
        color=3.0,
    )
    db_session.add(ferm)

    hop = RecipeHop(
        recipe_id=recipe.id,
        name="Cascade",
        alpha=5.5,
        amount=0.028,
        use="Boil",
        time=60.0,
    )
    db_session.add(hop)
    db_session.commit()

    # Get recipe
    response = client.get(f"/api/recipes/{recipe.id}")
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "IPA"
    assert data["boil_size"] == 25.0
    assert data["efficiency"] == 75.0

    # Check fermentables
    assert "fermentables" in data
    assert len(data["fermentables"]) == 1
    assert data["fermentables"][0]["name"] == "Pale Malt"

    # Check hops
    assert "hops" in data
    assert len(data["hops"]) == 1
    assert data["hops"][0]["name"] == "Cascade"
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_recipes_api.py::test_get_recipe_returns_full_data -v`
Expected: FAIL with "fermentables not in response"

**Step 3: Add Pydantic response models for ingredients**

```python
# backend/models.py (add after RecipeResponse, around line 570)

class RecipeFermentableResponse(BaseModel):
    """Response model for fermentable ingredient."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    amount: float
    yield_percent: float
    color: float
    add_after_boil: Optional[bool] = None
    origin: Optional[str] = None
    supplier: Optional[str] = None
    notes: Optional[str] = None
    coarse_fine_diff: Optional[float] = None
    moisture: Optional[float] = None
    diastatic_power: Optional[float] = None
    protein: Optional[float] = None
    max_in_batch: Optional[float] = None
    recommend_mash: Optional[bool] = None
    ibu_gal_per_lb: Optional[float] = None


class RecipeHopResponse(BaseModel):
    """Response model for hop addition."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    alpha: float
    amount: float
    use: str
    time: float
    notes: Optional[str] = None
    type: Optional[str] = None
    form: Optional[str] = None
    beta: Optional[float] = None
    hsi: Optional[float] = None
    origin: Optional[str] = None
    substitutes: Optional[str] = None
    humulene: Optional[float] = None
    caryophyllene: Optional[float] = None
    cohumulone: Optional[float] = None
    myrcene: Optional[float] = None


class RecipeYeastResponse(BaseModel):
    """Response model for yeast strain."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    form: str
    amount: float
    amount_is_weight: Optional[bool] = None
    laboratory: Optional[str] = None
    product_id: Optional[str] = None
    min_temperature: Optional[float] = None
    max_temperature: Optional[float] = None
    flocculation: Optional[str] = None
    attenuation: Optional[float] = None
    notes: Optional[str] = None
    best_for: Optional[str] = None
    times_cultured: Optional[int] = None
    max_reuse: Optional[int] = None
    add_to_secondary: Optional[bool] = None


class RecipeMiscResponse(BaseModel):
    """Response model for misc ingredient."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    use: str
    time: float
    amount: float
    amount_is_weight: Optional[bool] = None
    use_for: Optional[str] = None
    notes: Optional[str] = None


class RecipeWaterResponse(BaseModel):
    """Response model for water profile."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    amount: float
    calcium: float
    bicarbonate: float
    sulfate: float
    chloride: float
    sodium: float
    magnesium: float
    ph: Optional[float] = None
    notes: Optional[str] = None


class RecipeMashStepResponse(BaseModel):
    """Response model for mash step."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    step_temp: float
    step_time: float
    infuse_amount: Optional[float] = None
    ramp_time: Optional[float] = None
    end_temp: Optional[float] = None


class RecipeMashProfileResponse(BaseModel):
    """Response model for mash profile."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    grain_temp: float
    notes: Optional[str] = None
    tun_temp: Optional[float] = None
    sparge_temp: Optional[float] = None
    ph: Optional[float] = None
    tun_weight: Optional[float] = None
    tun_specific_heat: Optional[float] = None
    equip_adjust: Optional[bool] = None
    steps: list[RecipeMashStepResponse] = []


# Update RecipeResponse to include all relationships:
class RecipeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    author: Optional[str] = None
    style_id: Optional[str] = None
    type: Optional[str] = None

    # Gravity and targets
    og_target: Optional[float] = None
    fg_target: Optional[float] = None
    ibu_target: Optional[float] = None
    srm_target: Optional[float] = None
    abv_target: Optional[float] = None
    batch_size: Optional[float] = None

    # Brewing parameters
    boil_size: Optional[float] = None
    boil_time: Optional[float] = None
    efficiency: Optional[float] = None

    # Yeast (backward compat - top level)
    yeast_name: Optional[str] = None
    yeast_lab: Optional[str] = None
    yeast_product_id: Optional[str] = None
    yeast_temp_min: Optional[float] = None
    yeast_temp_max: Optional[float] = None
    yeast_attenuation: Optional[float] = None

    # Notes
    notes: Optional[str] = None
    created_at: datetime

    # Relationships
    style: Optional[StyleResponse] = None
    fermentables: list[RecipeFermentableResponse] = []
    hops: list[RecipeHopResponse] = []
    yeasts: list[RecipeYeastResponse] = []
    miscs: list[RecipeMiscResponse] = []
    waters: list[RecipeWaterResponse] = []
    mash_profile: Optional[RecipeMashProfileResponse] = None
```

**Step 4: Update recipe GET endpoint to load relationships**

```python
# backend/routers/recipes.py
# Find get_recipe endpoint and update:

from sqlalchemy.orm import selectinload

@router.get("/{recipe_id}", response_model=RecipeResponse)
async def get_recipe(recipe_id: int, db: AsyncSession = Depends(get_session)):
    """Get a single recipe by ID with all ingredients."""
    result = await db.execute(
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(
            selectinload(Recipe.fermentables),
            selectinload(Recipe.hops),
            selectinload(Recipe.yeasts),
            selectinload(Recipe.miscs),
            selectinload(Recipe.waters),
            selectinload(Recipe.mash_profile).selectinload(RecipeMashProfile.steps),
            selectinload(Recipe.style),
        )
    )
    recipe = result.scalar_one_or_none()

    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return recipe
```

**Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_recipes_api.py::test_get_recipe_returns_full_data -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/models.py backend/routers/recipes.py backend/tests/test_recipes_api.py
git commit -m "feat(api): return complete recipe data with all ingredients"
```

---

## Phase 5: Frontend UI Updates

### Task 11: Update Recipe Detail View - Grain Bill Section

**Files:**
- Modify: `frontend/src/routes/recipes/[id]/+page.svelte`

**Step 1: Add grain bill section to recipe detail view**

```svelte
<!-- frontend/src/routes/recipes/[id]/+page.svelte -->
<!-- Add after Yeast section, around line 140 -->

{#if recipe.fermentables && recipe.fermentables.length > 0}
  <div class="section">
    <h2 class="section-title">Grain Bill</h2>
    <div class="table-container">
      <table class="ingredient-table">
        <thead>
          <tr>
            <th>Fermentable</th>
            <th>Type</th>
            <th>Amount</th>
            <th>Percent</th>
            <th>Color</th>
          </tr>
        </thead>
        <tbody>
          {#each recipe.fermentables as ferm}
            {@const totalGrain = recipe.fermentables.reduce((sum, f) => sum + f.amount, 0)}
            {@const percent = ((ferm.amount / totalGrain) * 100).toFixed(1)}
            <tr>
              <td class="ingredient-name">
                {ferm.name}
                {#if ferm.origin}
                  <span class="ingredient-origin">({ferm.origin})</span>
                {/if}
              </td>
              <td>{ferm.type}</td>
              <td class="measurement">{ferm.amount.toFixed(2)} kg</td>
              <td class="measurement">{percent}%</td>
              <td class="measurement">{ferm.color.toFixed(0)} L</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>
{/if}
```

**Step 2: Add styles for ingredient tables**

```svelte
<!-- Add to <style> section at bottom of file -->

<style>
  /* ... existing styles ... */

  .table-container {
    overflow-x: auto;
    border: 1px solid var(--border-subtle);
    border-radius: 6px;
  }

  .ingredient-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }

  .ingredient-table th {
    background: var(--bg-surface);
    padding: var(--space-3);
    text-align: left;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    font-size: 12px;
    letter-spacing: 0.05em;
    border-bottom: 2px solid var(--border-default);
  }

  .ingredient-table td {
    padding: var(--space-3);
    border-bottom: 1px solid var(--border-subtle);
    color: var(--text-primary);
  }

  .ingredient-table tbody tr:last-child td {
    border-bottom: none;
  }

  .ingredient-table tbody tr:hover {
    background: var(--bg-hover);
  }

  .ingredient-name {
    font-weight: 500;
  }

  .ingredient-origin {
    color: var(--text-muted);
    font-size: 12px;
    font-style: italic;
  }

  .measurement {
    font-family: var(--font-measurement);
  }
</style>
```

**Step 3: Test locally**

```bash
cd frontend
npm run dev
```

Visit http://localhost:5173/recipes/{id} and verify grain bill displays.

**Step 4: Commit**

```bash
git add frontend/src/routes/recipes/[id]/+page.svelte
git commit -m "feat(ui): add grain bill section to recipe detail"
```

---

### Task 12: Update Recipe Detail View - Hop Schedule Section

**Files:**
- Modify: `frontend/src/routes/recipes/[id]/+page.svelte`

**Step 1: Add hop schedule section**

```svelte
<!-- Add after grain bill section -->

{#if recipe.hops && recipe.hops.length > 0}
  <div class="section">
    <h2 class="section-title">Hop Schedule</h2>
    <div class="table-container">
      <table class="ingredient-table">
        <thead>
          <tr>
            <th>Hop</th>
            <th>Alpha</th>
            <th>Amount</th>
            <th>Use</th>
            <th>Time</th>
            <th>Form</th>
          </tr>
        </thead>
        <tbody>
          {#each recipe.hops as hop}
            <tr>
              <td class="ingredient-name">
                {hop.name}
                {#if hop.origin}
                  <span class="ingredient-origin">({hop.origin})</span>
                {/if}
              </td>
              <td class="measurement">{hop.alpha.toFixed(1)}%</td>
              <td class="measurement">{(hop.amount * 1000).toFixed(0)} g</td>
              <td>{hop.use}</td>
              <td class="measurement">
                {#if hop.use === 'Dry Hop'}
                  {(hop.time / 1440).toFixed(0)} days
                {:else}
                  {hop.time.toFixed(0)} min
                {/if}
              </td>
              <td>{hop.form || '-'}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>
{/if}
```

**Step 2: Test locally and commit**

```bash
git add frontend/src/routes/recipes/[id]/+page.svelte
git commit -m "feat(ui): add hop schedule to recipe detail"
```

---

### Task 13: Update Recipe Detail View - Mash Profile Section

**Files:**
- Modify: `frontend/src/routes/recipes/[id]/+page.svelte`

**Step 1: Add mash profile section**

```svelte
<!-- Add after hop schedule section -->

{#if recipe.mash_profile}
  <div class="section">
    <h2 class="section-title">Mash Profile</h2>
    <div class="mash-info">
      <p class="mash-header">{recipe.mash_profile.name}</p>

      <div class="param-grid">
        <div class="param">
          <span class="param-label">Grain Temp</span>
          <span class="param-value">{recipe.mash_profile.grain_temp.toFixed(0)}°C</span>
        </div>
        {#if recipe.mash_profile.sparge_temp}
          <div class="param">
            <span class="param-label">Sparge Temp</span>
            <span class="param-value">{recipe.mash_profile.sparge_temp.toFixed(0)}°C</span>
          </div>
        {/if}
        {#if recipe.mash_profile.ph}
          <div class="param">
            <span class="param-label">pH</span>
            <span class="param-value">{recipe.mash_profile.ph.toFixed(1)}</span>
          </div>
        {/if}
      </div>

      {#if recipe.mash_profile.steps && recipe.mash_profile.steps.length > 0}
        <h3 class="subsection-title">Mash Steps</h3>
        <div class="mash-steps">
          {#each recipe.mash_profile.steps as step, idx}
            <div class="mash-step">
              <div class="step-number">{idx + 1}</div>
              <div class="step-content">
                <p class="step-name">{step.name}</p>
                <p class="step-details">
                  {step.type}
                  {#if step.infuse_amount}
                    — Add {step.infuse_amount.toFixed(1)} L water
                  {/if}
                  — {step.step_temp.toFixed(0)}°C for {step.step_time.toFixed(0)} min
                </p>
              </div>
            </div>
          {/each}
        </div>
      {/if}

      {#if recipe.mash_profile.notes}
        <p class="notes">{recipe.mash_profile.notes}</p>
      {/if}
    </div>
  </div>
{/if}
```

**Step 2: Add mash-specific styles**

```svelte
<style>
  /* ... existing styles ... */

  .mash-info {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-4);
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 6px;
  }

  .mash-header {
    font-family: var(--font-recipe-name);
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0;
  }

  .subsection-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--recipe-accent);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin: var(--space-2) 0;
  }

  .mash-steps {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .mash-step {
    display: flex;
    gap: var(--space-3);
    align-items: flex-start;
  }

  .step-number {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: var(--recipe-accent-muted);
    color: var(--recipe-accent);
    font-family: var(--font-mono);
    font-size: 14px;
    font-weight: 600;
    flex-shrink: 0;
  }

  .step-content {
    flex: 1;
  }

  .step-name {
    font-weight: 500;
    color: var(--text-primary);
    margin: 0 0 var(--space-1) 0;
  }

  .step-details {
    font-size: 13px;
    font-family: var(--font-mono);
    color: var(--text-secondary);
    margin: 0;
  }
</style>
```

**Step 3: Test and commit**

```bash
git add frontend/src/routes/recipes/[id]/+page.svelte
git commit -m "feat(ui): add mash profile section to recipe detail"
```

---

### Task 14: Build and Deploy

**Files:**
- Build: `frontend/` → `backend/static/`
- Deploy: Push to GitHub, pull on Raspberry Pi

**Step 1: Build frontend**

```bash
cd frontend
npm run build
```

**Step 2: Test built version locally**

```bash
cd ..
# Start backend with built frontend
python -m pytest backend/tests/  # Run all tests first
```

**Step 3: Commit build output**

```bash
git add backend/static
git commit -m "build: compile expanded recipe UI"
```

**Step 4: Push to GitHub**

```bash
git push origin feature/expand-recipe-schema
```

**Step 5: Deploy to Raspberry Pi**

```bash
# SSH to Pi
ssh pi@192.168.4.117

# Pull changes
cd /opt/brewsignal
git fetch origin
git checkout feature/expand-recipe-schema
git pull

# Run migrations
cd backend
source ../.venv/bin/activate
alembic upgrade head

# Restart service
sudo systemctl restart brewsignal

# Verify
sudo systemctl status brewsignal
```

**Step 6: Test on Pi**

Visit http://192.168.4.117:8080/recipes and verify:
- Import new BeerXML file
- View recipe with grain bill, hop schedule, mash profile
- All sections display correctly

**Step 7: Final commit**

```bash
git add .
git commit -m "chore: complete recipe schema expansion deployment"
git push
```

---

## Verification Checklist

- [ ] All database migrations applied successfully
- [ ] BeerXML parser extracts all ingredient data
- [ ] Recipe import saves fermentables, hops, yeasts, miscs, waters, mash profiles
- [ ] Recipe GET endpoint returns complete data with relationships
- [ ] Recipe detail UI displays grain bill table
- [ ] Recipe detail UI displays hop schedule table
- [ ] Recipe detail UI displays mash profile with steps
- [ ] All tests pass (`pytest backend/tests/`)
- [ ] Frontend builds without errors
- [ ] Deployed to Raspberry Pi successfully
- [ ] Can import BeerXML and see complete recipe card

---

## Future Enhancements (Not in Scope)

- Recipe search/filter by ingredients (e.g., "find recipes with Cascade hops")
- Recipe edit UI (currently import-only)
- Equipment profile storage
- Style guidelines display
- Ingredient inventory tracking
- Recipe scaling calculator
- Print-friendly recipe view

---

## Success Criteria

✅ Database schema expanded with relational tables for all BeerXML components
✅ BeerXML parser extracts complete recipe data
✅ Recipe import saves all ingredients to database
✅ Recipe API returns complete data with relationships
✅ Recipe detail UI displays comprehensive brewing blueprint:
   - Grain bill with percentages
   - Hop schedule with timings
   - Mash profile with step-by-step instructions
   - Yeast fermentation schedule
   - Water chemistry (if present)
✅ All tests pass
✅ Successfully deployed to production
