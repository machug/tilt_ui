import pytest
from backend.services.recipe_importer import import_beerxml_to_db
from backend.models import Recipe
from backend.database import get_db, init_db


FULL_BEERXML = """<?xml version="1.0"?>
<RECIPES>
  <RECIPE>
    <NAME>American IPA</NAME>
    <BREWER>Test Brewer</BREWER>
    <TYPE>All Grain</TYPE>
    <OG>1.065</OG>
    <FG>1.012</FG>
    <FERMENTABLES>
      <FERMENTABLE>
        <NAME>Pale Malt</NAME>
        <AMOUNT>5.0</AMOUNT>
        <TYPE>Grain</TYPE>
      </FERMENTABLE>
    </FERMENTABLES>
    <HOPS>
      <HOP>
        <NAME>Cascade</NAME>
        <AMOUNT>0.028</AMOUNT>
        <USE>Boil</USE>
        <TIME>60</TIME>
      </HOP>
    </HOPS>
    <YEASTS>
      <YEAST>
        <NAME>US-05</NAME>
        <LABORATORY>Fermentis</LABORATORY>
      </YEAST>
    </YEASTS>
  </RECIPE>
</RECIPES>
"""


COMPLEX_BEERXML = """<?xml version="1.0"?>
<RECIPES>
  <RECIPE>
    <NAME>Complex IPA</NAME>
    <BREWER>Test Brewer</BREWER>
    <TYPE>All Grain</TYPE>
    <OG>1.068</OG>
    <FG>1.014</FG>
    <IBU>65</IBU>
    <EST_COLOR>8.5</EST_COLOR>
    <EST_ABV>7.1</EST_ABV>
    <BATCH_SIZE>20.0</BATCH_SIZE>
    <FERMENTABLES>
      <FERMENTABLE>
        <NAME>Pale Malt 2-Row</NAME>
        <AMOUNT>6.0</AMOUNT>
        <TYPE>Grain</TYPE>
        <YIELD>80.0</YIELD>
        <COLOR>2.0</COLOR>
        <ORIGIN>US</ORIGIN>
        <SUPPLIER>Briess</SUPPLIER>
      </FERMENTABLE>
      <FERMENTABLE>
        <NAME>Munich Malt</NAME>
        <AMOUNT>0.5</AMOUNT>
        <TYPE>Grain</TYPE>
        <YIELD>78.0</YIELD>
        <COLOR>10.0</COLOR>
      </FERMENTABLE>
    </FERMENTABLES>
    <HOPS>
      <HOP>
        <NAME>Magnum</NAME>
        <AMOUNT>0.020</AMOUNT>
        <ALPHA>12.0</ALPHA>
        <USE>Boil</USE>
        <TIME>60</TIME>
        <FORM>Pellet</FORM>
        <TYPE>Bittering</TYPE>
      </HOP>
      <HOP>
        <NAME>Citra</NAME>
        <AMOUNT>0.056</AMOUNT>
        <ALPHA>13.5</ALPHA>
        <USE>Dry Hop</USE>
        <TIME>7</TIME>
        <FORM>Pellet</FORM>
        <TYPE>Aroma</TYPE>
      </HOP>
    </HOPS>
    <YEASTS>
      <YEAST>
        <NAME>Safale US-05</NAME>
        <LABORATORY>Fermentis</LABORATORY>
        <PRODUCT_ID>US-05</PRODUCT_ID>
        <TYPE>Ale</TYPE>
        <FORM>Dry</FORM>
        <ATTENUATION>81.0</ATTENUATION>
        <MIN_TEMPERATURE>15.0</MIN_TEMPERATURE>
        <MAX_TEMPERATURE>24.0</MAX_TEMPERATURE>
        <FLOCCULATION>Medium</FLOCCULATION>
      </YEAST>
    </YEASTS>
    <MISCS>
      <MISC>
        <NAME>Irish Moss</NAME>
        <TYPE>Fining</TYPE>
        <USE>Boil</USE>
        <TIME>15</TIME>
        <AMOUNT>0.005</AMOUNT>
        <AMOUNT_IS_WEIGHT>TRUE</AMOUNT_IS_WEIGHT>
      </MISC>
    </MISCS>
  </RECIPE>
</RECIPES>
"""


@pytest.mark.asyncio
async def test_import_full_recipe():
    await init_db()

    async for db in get_db():
        recipe_id = await import_beerxml_to_db(db, FULL_BEERXML)

        # Fetch with all relationships
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        result = await db.execute(
            select(Recipe)
            .where(Recipe.id == recipe_id)
            .options(
                selectinload(Recipe.fermentables),
                selectinload(Recipe.hops),
                selectinload(Recipe.yeasts)
            )
        )
        recipe = result.scalar_one()

        assert recipe.name == "American IPA"
        assert len(recipe.fermentables) == 1
        assert recipe.fermentables[0].name == "Pale Malt"
        assert len(recipe.hops) == 1
        assert recipe.hops[0].name == "Cascade"
        assert len(recipe.yeasts) == 1
        assert recipe.yeasts[0].name == "US-05"
        break


@pytest.mark.asyncio
async def test_import_complex_recipe_with_all_fields():
    """Test importing a recipe with multiple ingredients and detailed fields."""
    await init_db()

    async for db in get_db():
        recipe_id = await import_beerxml_to_db(db, COMPLEX_BEERXML)

        # Fetch with all relationships
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        result = await db.execute(
            select(Recipe)
            .where(Recipe.id == recipe_id)
            .options(
                selectinload(Recipe.fermentables),
                selectinload(Recipe.hops),
                selectinload(Recipe.yeasts),
                selectinload(Recipe.miscs)
            )
        )
        recipe = result.scalar_one()

        # Verify recipe fields
        assert recipe.name == "Complex IPA"
        assert recipe.author == "Test Brewer"
        assert recipe.og_target == 1.068
        assert recipe.fg_target == 1.014
        assert recipe.ibu_target == 65
        assert recipe.srm_target == 8.5
        assert recipe.abv_target == 7.1
        assert recipe.batch_size == 20.0

        # Verify fermentables
        assert len(recipe.fermentables) == 2
        pale_malt = recipe.fermentables[0]
        assert pale_malt.name == "Pale Malt 2-Row"
        assert pale_malt.amount_kg == 6.0
        assert pale_malt.type == "Grain"
        assert pale_malt.yield_percent == 80.0
        assert pale_malt.color_lovibond == 2.0
        assert pale_malt.origin == "US"
        assert pale_malt.supplier == "Briess"

        munich = recipe.fermentables[1]
        assert munich.name == "Munich Malt"
        assert munich.amount_kg == 0.5

        # Verify hops
        assert len(recipe.hops) == 2
        magnum = recipe.hops[0]
        assert magnum.name == "Magnum"
        assert magnum.amount_kg == 0.020
        assert magnum.alpha_percent == 12.0
        assert magnum.use == "Boil"
        assert magnum.time_min == 60
        assert magnum.form == "Pellet"
        assert magnum.type == "Bittering"

        citra = recipe.hops[1]
        assert citra.name == "Citra"
        assert citra.use == "Dry Hop"
        assert citra.time_min == 7

        # Verify yeasts
        assert len(recipe.yeasts) == 1
        yeast = recipe.yeasts[0]
        assert yeast.name == "Safale US-05"
        assert yeast.lab == "Fermentis"
        assert yeast.product_id == "US-05"
        assert yeast.type == "Ale"
        assert yeast.form == "Dry"
        assert yeast.attenuation_percent == 81.0
        assert yeast.temp_min_c == 15.0
        assert yeast.temp_max_c == 24.0
        assert yeast.flocculation == "Medium"

        # Verify misc ingredients
        assert len(recipe.miscs) == 1
        misc = recipe.miscs[0]
        assert misc.name == "Irish Moss"
        assert misc.type == "Fining"
        assert misc.use == "Boil"
        assert misc.time_min == 15
        assert misc.amount_kg == 0.005
        assert misc.amount_is_weight is True

        break
