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
