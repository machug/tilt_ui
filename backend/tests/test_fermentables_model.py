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
