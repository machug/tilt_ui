"""Test recipe detail endpoint returns ingredients."""

import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.models import Recipe, RecipeFermentable, RecipeHop, RecipeYeast, RecipeMisc
from backend.database import get_db, init_db


@pytest.mark.asyncio
async def test_get_recipe_endpoint_with_ingredients():
    """Test that GET /api/recipes/{id} returns recipe with all ingredients."""
    await init_db()

    async for db in get_db():
        # Create a recipe with ingredients
        recipe = Recipe(
            name="API Test IPA",
            author="API Tester",
            og_target=1.060,
            ibu_target=50.0,
        )
        db.add(recipe)
        await db.commit()
        await db.refresh(recipe)

        # Add one of each ingredient type
        fermentable = RecipeFermentable(
            recipe_id=recipe.id,
            name="Test Malt",
            type="Grain",
            amount_kg=4.5,
            yield_percent=80.0,
            color_lovibond=3.0,
        )
        hop = RecipeHop(
            recipe_id=recipe.id,
            name="Test Hop",
            alpha_percent=7.5,
            amount_kg=0.025,
            use="Boil",
            time_min=60,
        )
        yeast = RecipeYeast(
            recipe_id=recipe.id,
            name="Test Yeast",
            lab="Test Lab",
            type="Ale",
            attenuation_percent=75.0,
        )
        misc = RecipeMisc(
            recipe_id=recipe.id,
            name="Test Misc",
            type="Fining",
            use="Boil",
            time_min=10,
        )
        db.add_all([fermentable, hop, yeast, misc])
        await db.commit()

        recipe_id = recipe.id
        break

    # Make HTTP request to endpoint
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/recipes/{recipe_id}")

    assert response.status_code == 200
    data = response.json()

    # Verify recipe data
    assert data["id"] == recipe_id
    assert data["name"] == "API Test IPA"
    assert data["author"] == "API Tester"
    assert data["og_target"] == 1.060
    assert data["ibu_target"] == 50.0

    # Verify ingredients are included
    assert "fermentables" in data
    assert "hops" in data
    assert "yeasts" in data
    assert "miscs" in data

    # Verify ingredient data
    assert len(data["fermentables"]) == 1
    assert data["fermentables"][0]["name"] == "Test Malt"
    assert data["fermentables"][0]["amount_kg"] == 4.5
    assert data["fermentables"][0]["type"] == "Grain"

    assert len(data["hops"]) == 1
    assert data["hops"][0]["name"] == "Test Hop"
    assert data["hops"][0]["use"] == "Boil"
    assert data["hops"][0]["time_min"] == 60

    assert len(data["yeasts"]) == 1
    assert data["yeasts"][0]["name"] == "Test Yeast"
    assert data["yeasts"][0]["lab"] == "Test Lab"

    assert len(data["miscs"]) == 1
    assert data["miscs"][0]["name"] == "Test Misc"
    assert data["miscs"][0]["type"] == "Fining"


@pytest.mark.asyncio
async def test_get_recipe_endpoint_empty_ingredients():
    """Test that GET /api/recipes/{id} returns empty arrays when no ingredients."""
    await init_db()

    async for db in get_db():
        # Create a recipe without ingredients
        recipe = Recipe(
            name="Empty Recipe",
            og_target=1.050,
        )
        db.add(recipe)
        await db.commit()
        await db.refresh(recipe)
        recipe_id = recipe.id
        break

    # Make HTTP request
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/recipes/{recipe_id}")

    assert response.status_code == 200
    data = response.json()

    # Verify empty ingredient arrays
    assert data["fermentables"] == []
    assert data["hops"] == []
    assert data["yeasts"] == []
    assert data["miscs"] == []
