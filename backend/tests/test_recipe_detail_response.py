"""Integration test for recipe detail response with ingredients."""

import pytest
from backend.models import Recipe, RecipeFermentable, RecipeHop, RecipeYeast, RecipeMisc
from backend.database import get_db, init_db


@pytest.mark.asyncio
async def test_recipe_detail_response_with_ingredients():
    """Test that RecipeDetailResponse correctly includes all ingredients."""
    await init_db()

    async for db in get_db():
        # Create a recipe
        recipe = Recipe(
            name="Test IPA with Ingredients",
            author="Test Brewer",
            og_target=1.065,
            fg_target=1.012,
            ibu_target=60.0,
            batch_size=20.0,
        )
        db.add(recipe)
        await db.commit()
        await db.refresh(recipe)

        # Add fermentables
        fermentable1 = RecipeFermentable(
            recipe_id=recipe.id,
            name="Pale Malt 2-Row",
            type="Grain",
            amount_kg=5.0,
            yield_percent=80.0,
            color_lovibond=2.0,
            origin="US",
            supplier="Briess"
        )
        fermentable2 = RecipeFermentable(
            recipe_id=recipe.id,
            name="Munich Malt",
            type="Grain",
            amount_kg=0.5,
            yield_percent=78.0,
            color_lovibond=10.0,
        )
        db.add(fermentable1)
        db.add(fermentable2)

        # Add hops
        hop1 = RecipeHop(
            recipe_id=recipe.id,
            name="Cascade",
            alpha_percent=5.5,
            amount_kg=0.028,
            use="Boil",
            time_min=60,
            form="Pellet",
            type="Bittering"
        )
        hop2 = RecipeHop(
            recipe_id=recipe.id,
            name="Citra",
            alpha_percent=12.0,
            amount_kg=0.056,
            use="Dry Hop",
            time_min=7,
            form="Pellet",
            type="Aroma"
        )
        db.add(hop1)
        db.add(hop2)

        # Add yeast
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

        # Add misc
        misc = RecipeMisc(
            recipe_id=recipe.id,
            name="Irish Moss",
            type="Fining",
            use="Boil",
            time_min=15,
            amount_kg=0.005,
            amount_is_weight=True
        )
        db.add(misc)

        await db.commit()

        # Now fetch with selectinload
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        result = await db.execute(
            select(Recipe)
            .where(Recipe.id == recipe.id)
            .options(
                selectinload(Recipe.fermentables),
                selectinload(Recipe.hops),
                selectinload(Recipe.yeasts),
                selectinload(Recipe.miscs),
            )
        )
        loaded_recipe = result.scalar_one()

        # Verify relationships are loaded
        assert loaded_recipe.name == "Test IPA with Ingredients"
        assert len(loaded_recipe.fermentables) == 2
        assert len(loaded_recipe.hops) == 2
        assert len(loaded_recipe.yeasts) == 1
        assert len(loaded_recipe.miscs) == 1

        # Verify fermentable data
        assert loaded_recipe.fermentables[0].name == "Pale Malt 2-Row"
        assert loaded_recipe.fermentables[0].amount_kg == 5.0
        assert loaded_recipe.fermentables[1].name == "Munich Malt"

        # Verify hop data
        assert loaded_recipe.hops[0].name == "Cascade"
        assert loaded_recipe.hops[0].use == "Boil"
        assert loaded_recipe.hops[1].name == "Citra"
        assert loaded_recipe.hops[1].use == "Dry Hop"

        # Verify yeast data
        assert loaded_recipe.yeasts[0].name == "Safale US-05"
        assert loaded_recipe.yeasts[0].lab == "Fermentis"

        # Verify misc data
        assert loaded_recipe.miscs[0].name == "Irish Moss"

        # Test that Pydantic model can be created from ORM object
        from backend.models import RecipeDetailResponse
        response = RecipeDetailResponse.model_validate(loaded_recipe)

        assert response.id == recipe.id
        assert response.name == "Test IPA with Ingredients"
        assert len(response.fermentables) == 2
        assert len(response.hops) == 2
        assert len(response.yeasts) == 1
        assert len(response.miscs) == 1

        # Verify serialization to dict
        response_dict = response.model_dump()
        assert response_dict["name"] == "Test IPA with Ingredients"
        assert len(response_dict["fermentables"]) == 2
        assert response_dict["fermentables"][0]["name"] == "Pale Malt 2-Row"
        assert response_dict["hops"][0]["name"] == "Cascade"
        assert response_dict["yeasts"][0]["name"] == "Safale US-05"
        assert response_dict["miscs"][0]["name"] == "Irish Moss"

        break
