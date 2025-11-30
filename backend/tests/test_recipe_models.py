"""Tests for recipe and batch models."""

import pytest
import pytest_asyncio
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
