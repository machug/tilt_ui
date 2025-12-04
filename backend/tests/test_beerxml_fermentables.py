from backend.services.beerxml_parser import parse_beerxml


SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<RECIPES>
  <RECIPE>
    <NAME>Test IPA</NAME>
    <BREWER>Test Brewer</BREWER>
    <FERMENTABLES>
      <FERMENTABLE>
        <NAME>Pale Malt 2-Row</NAME>
        <TYPE>Grain</TYPE>
        <AMOUNT>5.0</AMOUNT>
        <YIELD>80.0</YIELD>
        <COLOR>2.0</COLOR>
        <ORIGIN>US</ORIGIN>
        <SUPPLIER>Briess</SUPPLIER>
      </FERMENTABLE>
      <FERMENTABLE>
        <NAME>Munich Malt</NAME>
        <TYPE>Grain</TYPE>
        <AMOUNT>0.5</AMOUNT>
        <YIELD>78.0</YIELD>
        <COLOR>10.0</COLOR>
      </FERMENTABLE>
    </FERMENTABLES>
  </RECIPE>
</RECIPES>
"""


def test_parse_fermentables():
    """Test parsing fermentables from BeerXML."""
    recipes = parse_beerxml(SAMPLE_XML)

    assert len(recipes) == 1
    recipe = recipes[0]

    assert len(recipe.fermentables) == 2

    pale_malt = recipe.fermentables[0]
    assert pale_malt.name == "Pale Malt 2-Row"
    assert pale_malt.type == "Grain"
    assert pale_malt.amount_kg == 5.0
    assert pale_malt.yield_percent == 80.0
    assert pale_malt.color_lovibond == 2.0
    assert pale_malt.origin == "US"
    assert pale_malt.supplier == "Briess"
