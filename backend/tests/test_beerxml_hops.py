from backend.services.beerxml_parser import parse_beerxml


SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<RECIPES>
  <RECIPE>
    <NAME>Hoppy IPA</NAME>
    <HOPS>
      <HOP>
        <NAME>Cascade</NAME>
        <ALPHA>5.5</ALPHA>
        <AMOUNT>0.028</AMOUNT>
        <USE>Boil</USE>
        <TIME>60</TIME>
        <FORM>Pellet</FORM>
        <TYPE>Bittering</TYPE>
      </HOP>
      <HOP>
        <NAME>Citra</NAME>
        <ALPHA>12.0</ALPHA>
        <AMOUNT>0.056</AMOUNT>
        <USE>Dry Hop</USE>
        <TIME>7</TIME>
        <FORM>Pellet</FORM>
        <TYPE>Aroma</TYPE>
      </HOP>
    </HOPS>
  </RECIPE>
</RECIPES>
"""


def test_parse_hops():
    recipes = parse_beerxml(SAMPLE_XML)
    assert len(recipes[0].hops) == 2

    cascade = recipes[0].hops[0]
    assert cascade.name == "Cascade"
    assert cascade.alpha_percent == 5.5
    assert cascade.use == "Boil"
    assert cascade.time_min == 60

    citra = recipes[0].hops[1]
    assert citra.name == "Citra"
    assert citra.use == "Dry Hop"
