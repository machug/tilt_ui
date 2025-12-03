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
