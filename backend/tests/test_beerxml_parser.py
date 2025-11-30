"""Tests for BeerXML parser service."""

import pytest


SAMPLE_BEERXML = """<?xml version="1.0" encoding="UTF-8"?>
<RECIPES>
  <RECIPE>
    <NAME>Test IPA</NAME>
    <TYPE>All Grain</TYPE>
    <BREWER>Test Brewer</BREWER>
    <BATCH_SIZE>19.0</BATCH_SIZE>
    <OG>1.065</OG>
    <FG>1.012</FG>
    <IBU>60.0</IBU>
    <EST_ABV>7.0</EST_ABV>
    <STYLE>
      <NAME>American IPA</NAME>
      <CATEGORY>IPA</CATEGORY>
      <CATEGORY_NUMBER>21</CATEGORY_NUMBER>
      <STYLE_LETTER>A</STYLE_LETTER>
      <STYLE_GUIDE>BJCP 2021</STYLE_GUIDE>
    </STYLE>
    <YEASTS>
      <YEAST>
        <NAME>Safale US-05</NAME>
        <LABORATORY>Fermentis</LABORATORY>
        <PRODUCT_ID>US-05</PRODUCT_ID>
        <MIN_TEMPERATURE>15.0</MIN_TEMPERATURE>
        <MAX_TEMPERATURE>22.0</MAX_TEMPERATURE>
        <ATTENUATION>77.0</ATTENUATION>
      </YEAST>
    </YEASTS>
  </RECIPE>
</RECIPES>
"""


def test_parse_beerxml_extracts_recipe_name():
    """Parser should extract recipe name from BeerXML."""
    from backend.services.beerxml_parser import parse_beerxml

    recipes = parse_beerxml(SAMPLE_BEERXML)

    assert len(recipes) == 1
    assert recipes[0].name == "Test IPA"


def test_parse_beerxml_extracts_gravity_targets():
    """Parser should extract OG and FG targets."""
    from backend.services.beerxml_parser import parse_beerxml

    recipes = parse_beerxml(SAMPLE_BEERXML)

    assert recipes[0].og == 1.065
    assert recipes[0].fg == 1.012


def test_parse_beerxml_extracts_yeast_data():
    """Parser should extract yeast name and temp range."""
    from backend.services.beerxml_parser import parse_beerxml

    recipes = parse_beerxml(SAMPLE_BEERXML)

    yeast = recipes[0].yeast
    assert yeast is not None
    assert yeast.name == "Safale US-05"
    assert yeast.lab == "Fermentis"
    assert yeast.temp_min == 15.0
    assert yeast.temp_max == 22.0
    assert yeast.attenuation == 77.0


def test_parse_beerxml_extracts_style():
    """Parser should extract style information."""
    from backend.services.beerxml_parser import parse_beerxml

    recipes = parse_beerxml(SAMPLE_BEERXML)

    style = recipes[0].style
    assert style is not None
    assert style.name == "American IPA"
    assert style.category_number == "21"
    assert style.style_letter == "A"
    assert style.guide == "BJCP 2021"


def test_parse_beerxml_handles_missing_fields():
    """Parser should handle missing optional fields gracefully."""
    from backend.services.beerxml_parser import parse_beerxml

    minimal_xml = """<?xml version="1.0"?>
    <RECIPES>
      <RECIPE>
        <NAME>Minimal Recipe</NAME>
      </RECIPE>
    </RECIPES>
    """

    recipes = parse_beerxml(minimal_xml)

    assert len(recipes) == 1
    assert recipes[0].name == "Minimal Recipe"
    assert recipes[0].og is None
    assert recipes[0].yeast is None
    assert recipes[0].style is None


def test_parse_beerxml_handles_multiple_recipes():
    """Parser should handle files with multiple recipes."""
    from backend.services.beerxml_parser import parse_beerxml

    multi_xml = """<?xml version="1.0"?>
    <RECIPES>
      <RECIPE><NAME>Recipe One</NAME></RECIPE>
      <RECIPE><NAME>Recipe Two</NAME></RECIPE>
    </RECIPES>
    """

    recipes = parse_beerxml(multi_xml)

    assert len(recipes) == 2
    assert recipes[0].name == "Recipe One"
    assert recipes[1].name == "Recipe Two"


def test_parse_beerxml_rejects_malformed_xml():
    """Parser should raise error for malformed XML."""
    from backend.services.beerxml_parser import parse_beerxml
    import defusedxml.ElementTree as ET

    with pytest.raises(ET.ParseError):
        parse_beerxml("<invalid><xml>")
