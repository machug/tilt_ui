import pytest
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
