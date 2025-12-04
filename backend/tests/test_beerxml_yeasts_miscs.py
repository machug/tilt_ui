"""Tests for parsing yeasts and misc ingredients from BeerXML."""

from backend.services.beerxml_parser import parse_beerxml


SAMPLE_XML_YEASTS = """<?xml version="1.0" encoding="UTF-8"?>
<RECIPES>
  <RECIPE>
    <NAME>Test Ale</NAME>
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
        <AMOUNT>0.0115</AMOUNT>
        <AMOUNT_IS_WEIGHT>TRUE</AMOUNT_IS_WEIGHT>
        <ADD_TO_SECONDARY>FALSE</ADD_TO_SECONDARY>
        <BEST_FOR>American Ales</BEST_FOR>
        <TIMES_CULTURED>0</TIMES_CULTURED>
        <MAX_REUSE>5</MAX_REUSE>
        <NOTES>Very clean fermenting yeast</NOTES>
      </YEAST>
      <YEAST>
        <NAME>Wyeast 1056</NAME>
        <LABORATORY>Wyeast</LABORATORY>
        <PRODUCT_ID>1056</PRODUCT_ID>
        <TYPE>Ale</TYPE>
        <FORM>Liquid</FORM>
        <ATTENUATION>75.0</ATTENUATION>
        <MIN_TEMPERATURE>16.0</MIN_TEMPERATURE>
        <MAX_TEMPERATURE>22.0</MAX_TEMPERATURE>
        <FLOCCULATION>Medium-Low</FLOCCULATION>
        <AMOUNT>0.125</AMOUNT>
        <AMOUNT_IS_WEIGHT>FALSE</AMOUNT_IS_WEIGHT>
      </YEAST>
    </YEASTS>
  </RECIPE>
</RECIPES>
"""


SAMPLE_XML_MISCS = """<?xml version="1.0" encoding="UTF-8"?>
<RECIPES>
  <RECIPE>
    <NAME>Test Beer</NAME>
    <MISCS>
      <MISC>
        <NAME>Irish Moss</NAME>
        <TYPE>Fining</TYPE>
        <USE>Boil</USE>
        <TIME>15</TIME>
        <AMOUNT>0.005</AMOUNT>
        <AMOUNT_IS_WEIGHT>TRUE</AMOUNT_IS_WEIGHT>
        <USE_FOR>Clarity</USE_FOR>
        <NOTES>Kettle fining agent</NOTES>
      </MISC>
      <MISC>
        <NAME>Coriander</NAME>
        <TYPE>Spice</TYPE>
        <USE>Boil</USE>
        <TIME>5</TIME>
        <AMOUNT>0.015</AMOUNT>
        <AMOUNT_IS_WEIGHT>TRUE</AMOUNT_IS_WEIGHT>
        <USE_FOR>Flavor</USE_FOR>
      </MISC>
      <MISC>
        <NAME>Gypsum</NAME>
        <TYPE>Water Agent</TYPE>
        <USE>Mash</USE>
        <TIME>0</TIME>
        <AMOUNT>0.002</AMOUNT>
        <AMOUNT_IS_WEIGHT>TRUE</AMOUNT_IS_WEIGHT>
        <USE_FOR>Water chemistry adjustment</USE_FOR>
      </MISC>
    </MISCS>
  </RECIPE>
</RECIPES>
"""


def test_parse_yeasts():
    """Test parsing yeasts from BeerXML."""
    recipes = parse_beerxml(SAMPLE_XML_YEASTS)

    assert len(recipes) == 1
    recipe = recipes[0]

    # Check we have 2 yeasts
    assert len(recipe.yeasts) == 2

    # Check first yeast (US-05, dry)
    us05 = recipe.yeasts[0]
    assert us05.name == "Safale US-05"
    assert us05.lab == "Fermentis"
    assert us05.product_id == "US-05"
    assert us05.type == "Ale"
    assert us05.form == "Dry"
    assert us05.attenuation_percent == 81.0
    assert us05.temp_min_c == 15.0
    assert us05.temp_max_c == 24.0
    assert us05.flocculation == "Medium"
    assert us05.amount_kg == 0.0115
    assert us05.amount_l is None
    assert us05.add_to_secondary is False
    assert us05.best_for == "American Ales"
    assert us05.times_cultured == 0
    assert us05.max_reuse == 5
    assert us05.notes == "Very clean fermenting yeast"

    # Check second yeast (Wyeast 1056, liquid)
    wyeast = recipe.yeasts[1]
    assert wyeast.name == "Wyeast 1056"
    assert wyeast.lab == "Wyeast"
    assert wyeast.product_id == "1056"
    assert wyeast.type == "Ale"
    assert wyeast.form == "Liquid"
    assert wyeast.attenuation_percent == 75.0
    assert wyeast.temp_min_c == 16.0
    assert wyeast.temp_max_c == 22.0
    assert wyeast.flocculation == "Medium-Low"
    assert wyeast.amount_l == 0.125
    assert wyeast.amount_kg is None


def test_parse_miscs():
    """Test parsing misc ingredients from BeerXML."""
    recipes = parse_beerxml(SAMPLE_XML_MISCS)

    assert len(recipes) == 1
    recipe = recipes[0]

    # Check we have 3 miscs
    assert len(recipe.miscs) == 3

    # Check first misc (Irish Moss)
    irish_moss = recipe.miscs[0]
    assert irish_moss.name == "Irish Moss"
    assert irish_moss.type == "Fining"
    assert irish_moss.use == "Boil"
    assert irish_moss.time_min == 15
    assert irish_moss.amount_kg == 0.005
    assert irish_moss.amount_is_weight is True
    assert irish_moss.use_for == "Clarity"
    assert irish_moss.notes == "Kettle fining agent"

    # Check second misc (Coriander)
    coriander = recipe.miscs[1]
    assert coriander.name == "Coriander"
    assert coriander.type == "Spice"
    assert coriander.use == "Boil"
    assert coriander.time_min == 5
    assert coriander.amount_kg == 0.015
    assert coriander.amount_is_weight is True
    assert coriander.use_for == "Flavor"

    # Check third misc (Gypsum)
    gypsum = recipe.miscs[2]
    assert gypsum.name == "Gypsum"
    assert gypsum.type == "Water Agent"
    assert gypsum.use == "Mash"
    assert gypsum.time_min == 0
    assert gypsum.amount_kg == 0.002
    assert gypsum.amount_is_weight is True
    assert gypsum.use_for == "Water chemistry adjustment"


def test_parse_empty_yeasts_and_miscs():
    """Test parsing recipe with no yeasts or miscs."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <RECIPES>
      <RECIPE>
        <NAME>Minimal Recipe</NAME>
      </RECIPE>
    </RECIPES>
    """

    recipes = parse_beerxml(xml)
    assert len(recipes) == 1
    recipe = recipes[0]

    # Should have empty lists, not None
    assert recipe.yeasts == []
    assert recipe.miscs == []
