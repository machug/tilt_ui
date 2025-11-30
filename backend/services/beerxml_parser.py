"""BeerXML 1.0 parser service.

Parses BeerXML files and extracts fermentation-relevant data:
- Recipe name, author, type
- OG/FG targets
- Yeast name, temp range, attenuation
- Style information
"""

from dataclasses import dataclass, field
from typing import Optional

import defusedxml.ElementTree as ET


@dataclass
class ParsedYeast:
    """Yeast data extracted from BeerXML."""
    name: Optional[str] = None
    lab: Optional[str] = None
    product_id: Optional[str] = None
    temp_min: Optional[float] = None  # Celsius
    temp_max: Optional[float] = None  # Celsius
    attenuation: Optional[float] = None


@dataclass
class ParsedStyle:
    """Style data extracted from BeerXML."""
    name: Optional[str] = None
    category: Optional[str] = None
    category_number: Optional[str] = None
    style_letter: Optional[str] = None
    guide: Optional[str] = None


@dataclass
class ParsedRecipe:
    """Recipe data extracted from BeerXML."""
    name: str
    author: Optional[str] = None
    type: Optional[str] = None
    og: Optional[float] = None
    fg: Optional[float] = None
    ibu: Optional[float] = None
    srm: Optional[float] = None
    abv: Optional[float] = None
    batch_size: Optional[float] = None  # Liters
    style: Optional[ParsedStyle] = None
    yeast: Optional[ParsedYeast] = None
    raw_xml: str = ""


def parse_beerxml(xml_content: str) -> list[ParsedRecipe]:
    """Parse BeerXML content and return list of recipes.

    Args:
        xml_content: BeerXML 1.0 formatted XML string

    Returns:
        List of ParsedRecipe dataclasses with extracted data

    Raises:
        ET.ParseError: If XML is malformed
    """
    root = ET.fromstring(xml_content)
    recipes = []

    for recipe_elem in root.findall('.//RECIPE'):
        recipe = _parse_recipe(recipe_elem, xml_content)
        recipes.append(recipe)

    return recipes


def _get_text(elem, tag: str) -> Optional[str]:
    """Get text content of child element."""
    child = elem.find(tag)
    return child.text.strip() if child is not None and child.text else None


def _get_float(elem, tag: str) -> Optional[float]:
    """Get float value of child element."""
    text = _get_text(elem, tag)
    if text:
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _parse_recipe(elem, raw_xml: str) -> ParsedRecipe:
    """Parse a single RECIPE element."""
    recipe = ParsedRecipe(
        name=_get_text(elem, 'NAME') or "Unnamed Recipe",
        author=_get_text(elem, 'BREWER'),
        type=_get_text(elem, 'TYPE'),
        og=_get_float(elem, 'OG'),
        fg=_get_float(elem, 'FG'),
        ibu=_get_float(elem, 'IBU'),
        srm=_get_float(elem, 'EST_COLOR'),
        abv=_get_float(elem, 'EST_ABV'),
        batch_size=_get_float(elem, 'BATCH_SIZE'),
        raw_xml=raw_xml
    )

    # Parse style
    style_elem = elem.find('.//STYLE')
    if style_elem is not None:
        recipe.style = ParsedStyle(
            name=_get_text(style_elem, 'NAME'),
            category=_get_text(style_elem, 'CATEGORY'),
            category_number=_get_text(style_elem, 'CATEGORY_NUMBER'),
            style_letter=_get_text(style_elem, 'STYLE_LETTER'),
            guide=_get_text(style_elem, 'STYLE_GUIDE'),
        )

    # Parse first yeast
    yeast_elem = elem.find('.//YEASTS/YEAST')
    if yeast_elem is not None:
        recipe.yeast = ParsedYeast(
            name=_get_text(yeast_elem, 'NAME'),
            lab=_get_text(yeast_elem, 'LABORATORY'),
            product_id=_get_text(yeast_elem, 'PRODUCT_ID'),
            temp_min=_get_float(yeast_elem, 'MIN_TEMPERATURE'),
            temp_max=_get_float(yeast_elem, 'MAX_TEMPERATURE'),
            attenuation=_get_float(yeast_elem, 'ATTENUATION'),
        )

    return recipe
