"""
End-to-end test for BeerXML import with real recipe fixture.

This test validates the entire import flow:
1. Load realistic BeerXML from fixture file
2. Import using import_beerxml_to_db service
3. Fetch recipe via database query
4. Validate all ingredients are present and correct
"""

import pytest
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.services.recipe_importer import import_beerxml_to_db
from backend.models import Recipe
from backend.database import get_db, init_db


# Path to fixture file
FIXTURES_DIR = Path(__file__).parent / "fixtures"
REALISTIC_IPA_XML = FIXTURES_DIR / "realistic_ipa.xml"


@pytest.mark.asyncio
async def test_full_import_with_realistic_beerxml():
    """
    End-to-end test with comprehensive BeerXML file.

    This test validates:
    - Recipe metadata import (name, author, stats, dates, notes)
    - Style information import
    - Fermentables with all fields
    - Hops with boil and dry hop additions
    - Multiple yeast options
    - Misc ingredients (finings, water agents, spices)
    """
    await init_db()

    # Load real BeerXML from fixture
    with open(REALISTIC_IPA_XML, 'r') as f:
        xml_content = f.read()

    async for db in get_db():
        # Import BeerXML to database
        recipe_id = await import_beerxml_to_db(db, xml_content)
        assert recipe_id is not None, "Recipe ID should be returned"

        # Fetch the complete recipe with all relationships
        result = await db.execute(
            select(Recipe)
            .where(Recipe.id == recipe_id)
            .options(
                selectinload(Recipe.style),
                selectinload(Recipe.fermentables),
                selectinload(Recipe.hops),
                selectinload(Recipe.yeasts),
                selectinload(Recipe.miscs),
            )
        )
        recipe = result.scalar_one()

        # ========== RECIPE METADATA ==========
        assert recipe.name == "West Coast IPA"
        assert recipe.author == "John Brewer"
        assert recipe.type == "All Grain"

        # Stats
        assert recipe.og_target == 1.065
        assert recipe.fg_target == 1.012
        assert recipe.ibu_target == 65
        assert recipe.srm_target == 8.5
        assert recipe.abv_target == 7.0
        assert recipe.batch_size == 20.0

        # Expanded fields
        assert recipe.brewer == "John Brewer"
        assert recipe.asst_brewer == "Jane Assistant"
        assert recipe.boil_size_l == 27.0
        assert recipe.boil_time_min == 60
        assert recipe.efficiency_percent == 75.0

        # Fermentation
        assert recipe.primary_age_days == 14
        assert recipe.primary_temp_c == 20.0
        assert recipe.secondary_age_days == 7
        assert recipe.secondary_temp_c == 20.0

        # Aging and carbonation
        assert recipe.age_days == 21
        assert recipe.age_temp_c == 4.0
        assert recipe.carbonation_vols == 2.4
        assert recipe.forced_carbonation is False
        assert recipe.priming_sugar_name == "Corn Sugar"

        # Tasting notes
        assert recipe.taste_notes == "Clean bitterness with strong citrus and pine notes. Dry finish."
        assert recipe.taste_rating == 45
        assert recipe.date == "20 Dec 2025"

        # ========== STYLE INFORMATION ==========
        assert recipe.style is not None
        assert recipe.style.name == "American IPA"
        assert recipe.style.category == "IPA"
        assert recipe.style.category_number == "21"
        assert recipe.style.style_letter == "A"
        assert recipe.style.guide == "BJCP 2015"
        assert recipe.style.og_min == 1.056
        assert recipe.style.og_max == 1.070
        assert recipe.style.ibu_min == 40
        assert recipe.style.ibu_max == 70

        # ========== FERMENTABLES ==========
        assert len(recipe.fermentables) == 3, "Should have 3 fermentables"

        # Pale Malt 2-Row
        pale_malt = recipe.fermentables[0]
        assert pale_malt.name == "Pale Malt 2-Row"
        assert pale_malt.type == "Grain"
        assert pale_malt.amount_kg == 5.5
        assert pale_malt.yield_percent == 80.0
        assert pale_malt.color_lovibond == 2.0
        assert pale_malt.origin == "US"
        assert pale_malt.supplier == "Briess"
        assert pale_malt.notes == "Base malt for American ales"
        assert pale_malt.add_after_boil is False
        assert pale_malt.coarse_fine_diff == 1.5
        assert pale_malt.moisture == 4.0
        assert pale_malt.diastatic_power == 140.0
        assert pale_malt.protein == 11.5
        assert pale_malt.max_in_batch == 100.0
        assert pale_malt.recommend_mash is True

        # Munich Malt
        munich = recipe.fermentables[1]
        assert munich.name == "Munich Malt"
        assert munich.type == "Grain"
        assert munich.amount_kg == 0.5
        assert munich.yield_percent == 78.0
        assert munich.color_lovibond == 10.0
        assert munich.origin == "Germany"
        assert munich.supplier == "Weyermann"

        # Crystal 40L
        crystal = recipe.fermentables[2]
        assert crystal.name == "Crystal 40L"
        assert crystal.amount_kg == 0.3
        assert crystal.color_lovibond == 40.0
        assert crystal.recommend_mash is False

        # Validate total grain bill
        total_grain_kg = sum(f.amount_kg for f in recipe.fermentables)
        assert total_grain_kg == pytest.approx(6.3, rel=0.01)

        # ========== HOPS ==========
        assert len(recipe.hops) == 6, "Should have 6 hop additions (4 boil + 2 dry hop)"

        # Group hops by use
        boil_hops = [h for h in recipe.hops if h.use == "Boil"]
        dry_hops = [h for h in recipe.hops if h.use == "Dry Hop"]

        assert len(boil_hops) == 4, "Should have 4 boil hop additions"
        assert len(dry_hops) == 2, "Should have 2 dry hop additions"

        # Magnum (60 min bittering)
        magnum = next(h for h in recipe.hops if h.name == "Magnum")
        assert magnum.alpha_percent == 12.0
        assert magnum.amount_kg == 0.020
        assert magnum.use == "Boil"
        assert magnum.time_min == 60
        assert magnum.form == "Pellet"
        assert magnum.type == "Bittering"
        assert magnum.beta_percent == 5.5
        assert magnum.hsi == 35.0
        assert magnum.origin == "US"

        # Centennial (20 min)
        centennial = next(h for h in recipe.hops if h.name == "Centennial")
        assert centennial.alpha_percent == 10.0
        assert centennial.time_min == 20
        assert centennial.humulene == 18.0
        assert centennial.caryophyllene == 6.0
        assert centennial.cohumulone == 28.0
        assert centennial.myrcene == 45.0

        # Simcoe (10 min)
        simcoe = next(h for h in recipe.hops if h.name == "Simcoe")
        assert simcoe.alpha_percent == 13.0
        assert simcoe.time_min == 10
        assert simcoe.type == "Aroma"

        # Cascade (5 min)
        cascade = next(h for h in recipe.hops if h.name == "Cascade")
        assert cascade.alpha_percent == 5.5
        assert cascade.time_min == 5

        # Citra (Dry Hop)
        citra = next(h for h in recipe.hops if h.name == "Citra")
        assert citra.use == "Dry Hop"
        assert citra.amount_kg == 0.056
        assert citra.time_min == 7  # Days for dry hop
        assert citra.alpha_percent == 12.0

        # Mosaic (Dry Hop)
        mosaic = next(h for h in recipe.hops if h.name == "Mosaic")
        assert mosaic.use == "Dry Hop"
        assert mosaic.amount_kg == 0.056
        assert mosaic.alpha_percent == 12.25

        # Validate total hop amounts
        total_boil_hops_kg = sum(h.amount_kg for h in boil_hops)
        total_dry_hop_kg = sum(h.amount_kg for h in dry_hops)
        assert total_boil_hops_kg == pytest.approx(0.104, rel=0.01)
        assert total_dry_hop_kg == pytest.approx(0.112, rel=0.01)

        # ========== YEASTS ==========
        assert len(recipe.yeasts) == 2, "Should have 2 yeast options"

        # Safale US-05 (Dry)
        us05 = next(y for y in recipe.yeasts if y.name == "Safale US-05")
        assert us05.lab == "Fermentis"
        assert us05.product_id == "US-05"
        assert us05.type == "Ale"
        assert us05.form == "Dry"
        assert us05.attenuation_percent == 81.0
        assert us05.temp_min_c == 15.0
        assert us05.temp_max_c == 24.0
        assert us05.flocculation == "Medium"
        assert us05.amount_kg == 0.0115
        assert us05.add_to_secondary is False
        assert "clean" in us05.notes.lower()
        assert us05.best_for == "American ales, IPAs, Pale Ales"
        assert us05.times_cultured == 0
        assert us05.max_reuse == 5

        # WLP001 (Liquid)
        wlp001 = next(y for y in recipe.yeasts if y.product_id == "WLP001")
        assert wlp001.name == "White Labs WLP001 California Ale"
        assert wlp001.lab == "White Labs"
        assert wlp001.form == "Liquid"
        assert wlp001.amount_l == 0.100
        assert wlp001.attenuation_percent == 76.0
        assert wlp001.temp_min_c == 20.0
        assert wlp001.temp_max_c == 23.0
        assert wlp001.max_reuse == 10

        # ========== MISC INGREDIENTS ==========
        assert len(recipe.miscs) == 4, "Should have 4 misc ingredients"

        # Irish Moss (Fining)
        irish_moss = next(m for m in recipe.miscs if m.name == "Irish Moss")
        assert irish_moss.type == "Fining"
        assert irish_moss.use == "Boil"
        assert irish_moss.time_min == 15
        assert irish_moss.amount_kg == 0.005
        assert irish_moss.amount_is_weight is True
        assert irish_moss.use_for == "Clarity"

        # Gypsum (Water Agent)
        gypsum = next(m for m in recipe.miscs if m.name == "Gypsum (Calcium Sulfate)")
        assert gypsum.type == "Water Agent"
        assert gypsum.use == "Mash"
        assert gypsum.time_min == 60
        assert gypsum.amount_kg == 0.004
        assert "sulfate" in gypsum.notes.lower()

        # Calcium Chloride (Water Agent)
        cacl2 = next(m for m in recipe.miscs if m.name == "Calcium Chloride")
        assert cacl2.type == "Water Agent"
        assert cacl2.use == "Mash"
        assert cacl2.amount_kg == 0.002

        # Coriander (Spice)
        coriander = next(m for m in recipe.miscs if m.name == "Coriander")
        assert coriander.type == "Spice"
        assert coriander.use == "Boil"
        assert coriander.time_min == 5
        assert coriander.amount_kg == 0.015

        print("\n=== E2E Test Summary ===")
        print(f"Recipe: {recipe.name} ({recipe.type})")
        print(f"Stats: OG {recipe.og_target} → FG {recipe.fg_target}, {recipe.abv_target}% ABV, {recipe.ibu_target} IBU")
        print(f"Fermentables: {len(recipe.fermentables)} ({total_grain_kg:.2f} kg total)")
        print(f"Hops: {len(boil_hops)} boil additions, {len(dry_hops)} dry hop additions")
        print(f"Yeasts: {len(recipe.yeasts)} options")
        print(f"Misc: {len(recipe.miscs)} ingredients")
        print("========================\n")

        break


@pytest.mark.asyncio
async def test_api_endpoint_returns_full_recipe():
    """
    Test that the recipe detail API endpoint returns all imported data correctly.

    This simulates the actual API flow that the frontend would use.
    """
    await init_db()

    # Load and import recipe
    with open(REALISTIC_IPA_XML, 'r') as f:
        xml_content = f.read()

    async for db in get_db():
        recipe_id = await import_beerxml_to_db(db, xml_content)

        # Simulate API endpoint query (same as GET /api/recipes/{id})
        from backend.routers.recipes import get_recipe

        recipe_response = await get_recipe(recipe_id, db)

        # Validate response structure (RecipeDetailResponse)
        assert recipe_response.id == recipe_id
        assert recipe_response.name == "West Coast IPA"
        assert recipe_response.author == "John Brewer"

        # Verify all ingredients are included in response
        assert len(recipe_response.fermentables) == 3
        assert len(recipe_response.hops) == 6
        assert len(recipe_response.yeasts) == 2

        # Verify fermentable data structure
        assert recipe_response.fermentables[0].name == "Pale Malt 2-Row"
        assert recipe_response.fermentables[0].amount_kg == 5.5

        # Verify hop data structure
        magnum = next(h for h in recipe_response.hops if h.name == "Magnum")
        assert magnum.alpha_percent == 12.0
        assert magnum.use == "Boil"

        # Verify yeast data structure
        us05 = next(y for y in recipe_response.yeasts if y.product_id == "US-05")
        assert us05.lab == "Fermentis"
        assert us05.attenuation_percent == 81.0

        print("\n=== API Response Test ===")
        print(f"Recipe ID: {recipe_response.id}")
        print(f"Ingredients in response: {len(recipe_response.fermentables)} fermentables, "
              f"{len(recipe_response.hops)} hops, {len(recipe_response.yeasts)} yeasts")
        print("=========================\n")

        break
