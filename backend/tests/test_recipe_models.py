"""Tests for recipe and batch models."""

import pytest
from sqlalchemy import select

from backend.models import Style, Recipe, Batch


@pytest.mark.asyncio
async def test_style_model_exists(test_db):
    """Style model should exist and be queryable."""
    result = await test_db.execute(select(Style))
    styles = result.scalars().all()
    assert styles == []  # Empty but table exists


@pytest.mark.asyncio
async def test_recipe_model_exists(test_db):
    """Recipe model should exist and be queryable."""
    result = await test_db.execute(select(Recipe))
    recipes = result.scalars().all()
    assert recipes == []


@pytest.mark.asyncio
async def test_batch_model_exists(test_db):
    """Batch model should exist and be queryable."""
    result = await test_db.execute(select(Batch))
    batches = result.scalars().all()
    assert batches == []


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


@pytest.mark.asyncio
async def test_batch_id_column_in_readings(test_db):
    """Readings table should have batch_id column after migration."""
    from sqlalchemy import text

    # Get column names from readings table
    result = await test_db.execute(text("PRAGMA table_info(readings)"))
    columns = [row[1] for row in result.fetchall()]

    assert "batch_id" in columns


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
