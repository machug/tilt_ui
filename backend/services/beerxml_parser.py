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
    name: str
    lab: Optional[str] = None
    product_id: Optional[str] = None
    type: Optional[str] = None  # Ale, Lager, Wheat, Wine, Champagne
    form: Optional[str] = None  # Liquid, Dry, Slant, Culture
    attenuation_percent: Optional[float] = None  # % (0-100)
    temp_min_c: Optional[float] = None  # Celsius
    temp_max_c: Optional[float] = None  # Celsius
    flocculation: Optional[str] = None  # Low, Medium, High, Very High
    amount_l: Optional[float] = None  # Liters (if liquid)
    amount_kg: Optional[float] = None  # Kg (if dry)
    add_to_secondary: Optional[bool] = None
    best_for: Optional[str] = None
    times_cultured: Optional[int] = None
    max_reuse: Optional[int] = None
    notes: Optional[str] = None


@dataclass
class ParsedStyle:
    """Style data extracted from BeerXML."""
    name: Optional[str] = None
    category: Optional[str] = None
    category_number: Optional[str] = None
    style_letter: Optional[str] = None
    guide: Optional[str] = None
    type: Optional[str] = None
    og_min: Optional[float] = None
    og_max: Optional[float] = None
    fg_min: Optional[float] = None
    fg_max: Optional[float] = None
    ibu_min: Optional[float] = None
    ibu_max: Optional[float] = None
    color_min: Optional[float] = None
    color_max: Optional[float] = None
    abv_min: Optional[float] = None
    abv_max: Optional[float] = None
    carb_min: Optional[float] = None
    carb_max: Optional[float] = None


@dataclass
class ParsedFermentable:
    """Fermentable ingredient data."""
    name: str
    type: Optional[str] = None
    amount_kg: Optional[float] = None
    yield_percent: Optional[float] = None
    color_lovibond: Optional[float] = None
    origin: Optional[str] = None
    supplier: Optional[str] = None
    notes: Optional[str] = None
    add_after_boil: Optional[bool] = None
    coarse_fine_diff: Optional[float] = None
    moisture: Optional[float] = None
    diastatic_power: Optional[float] = None
    protein: Optional[float] = None
    max_in_batch: Optional[float] = None
    recommend_mash: Optional[bool] = None


@dataclass
class ParsedHop:
    """Hop data extracted from BeerXML."""
    name: str
    alpha_percent: Optional[float] = None
    amount_kg: Optional[float] = None
    use: Optional[str] = None
    time_min: Optional[float] = None
    form: Optional[str] = None
    type: Optional[str] = None
    origin: Optional[str] = None
    substitutes: Optional[str] = None
    beta_percent: Optional[float] = None
    hsi: Optional[float] = None
    humulene: Optional[float] = None
    caryophyllene: Optional[float] = None
    cohumulone: Optional[float] = None
    myrcene: Optional[float] = None
    notes: Optional[str] = None


@dataclass
class ParsedMisc:
    """Misc ingredient data extracted from BeerXML."""
    name: str
    type: Optional[str] = None  # Spice, Fining, Water Agent, Herb, Flavor, Other
    use: Optional[str] = None  # Boil, Mash, Primary, Secondary, Bottling
    time_min: Optional[float] = None  # Minutes
    amount_kg: Optional[float] = None  # Kg or L (check amount_is_weight)
    amount_is_weight: Optional[bool] = None
    use_for: Optional[str] = None
    notes: Optional[str] = None


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
    fermentables: list[ParsedFermentable] = field(default_factory=list)
    hops: list[ParsedHop] = field(default_factory=list)
    yeasts: list[ParsedYeast] = field(default_factory=list)
    miscs: list[ParsedMisc] = field(default_factory=list)
    raw_xml: str = ""

    # Expanded BeerXML fields
    brewer: Optional[str] = None
    asst_brewer: Optional[str] = None
    boil_size_l: Optional[float] = None
    boil_time_min: Optional[int] = None
    efficiency_percent: Optional[float] = None
    primary_age_days: Optional[int] = None
    primary_temp_c: Optional[float] = None
    secondary_age_days: Optional[int] = None
    secondary_temp_c: Optional[float] = None
    tertiary_age_days: Optional[int] = None
    tertiary_temp_c: Optional[float] = None
    age_days: Optional[int] = None
    age_temp_c: Optional[float] = None
    carbonation_vols: Optional[float] = None
    forced_carbonation: Optional[bool] = None
    priming_sugar_name: Optional[str] = None
    priming_sugar_amount_kg: Optional[float] = None
    taste_notes: Optional[str] = None
    taste_rating: Optional[float] = None
    date: Optional[str] = None


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


def _parse_fermentables(recipe_elem) -> list[ParsedFermentable]:
    """Parse FERMENTABLES section."""
    fermentables = []

    for ferm_elem in recipe_elem.findall('.//FERMENTABLES/FERMENTABLE'):
        fermentable = ParsedFermentable(
            name=_get_text(ferm_elem, 'NAME') or "Unknown",
            type=_get_text(ferm_elem, 'TYPE'),
            amount_kg=_get_float(ferm_elem, 'AMOUNT'),
            yield_percent=_get_float(ferm_elem, 'YIELD'),
            color_lovibond=_get_float(ferm_elem, 'COLOR'),
            origin=_get_text(ferm_elem, 'ORIGIN'),
            supplier=_get_text(ferm_elem, 'SUPPLIER'),
            notes=_get_text(ferm_elem, 'NOTES'),
            add_after_boil=_get_text(ferm_elem, 'ADD_AFTER_BOIL') == 'TRUE',
            coarse_fine_diff=_get_float(ferm_elem, 'COARSE_FINE_DIFF'),
            moisture=_get_float(ferm_elem, 'MOISTURE'),
            diastatic_power=_get_float(ferm_elem, 'DIASTATIC_POWER'),
            protein=_get_float(ferm_elem, 'PROTEIN'),
            max_in_batch=_get_float(ferm_elem, 'MAX_IN_BATCH'),
            recommend_mash=_get_text(ferm_elem, 'RECOMMEND_MASH') == 'TRUE',
        )
        fermentables.append(fermentable)

    return fermentables


def _parse_hops(recipe_elem) -> list[ParsedHop]:
    """Parse HOPS section."""
    hops = []
    for hop_elem in recipe_elem.findall('.//HOPS/HOP'):
        hop = ParsedHop(
            name=_get_text(hop_elem, 'NAME') or "Unknown",
            alpha_percent=_get_float(hop_elem, 'ALPHA'),
            amount_kg=_get_float(hop_elem, 'AMOUNT'),
            use=_get_text(hop_elem, 'USE'),
            time_min=_get_float(hop_elem, 'TIME'),
            form=_get_text(hop_elem, 'FORM'),
            type=_get_text(hop_elem, 'TYPE'),
            origin=_get_text(hop_elem, 'ORIGIN'),
            substitutes=_get_text(hop_elem, 'SUBSTITUTES'),
            beta_percent=_get_float(hop_elem, 'BETA'),
            hsi=_get_float(hop_elem, 'HSI'),
            humulene=_get_float(hop_elem, 'HUMULENE'),
            caryophyllene=_get_float(hop_elem, 'CARYOPHYLLENE'),
            cohumulone=_get_float(hop_elem, 'COHUMULONE'),
            myrcene=_get_float(hop_elem, 'MYRCENE'),
            notes=_get_text(hop_elem, 'NOTES'),
        )
        hops.append(hop)
    return hops


def _get_int(elem, tag: str) -> Optional[int]:
    """Get integer value of child element."""
    text = _get_text(elem, tag)
    if text:
        try:
            return int(text)
        except ValueError:
            return None
    return None


def _get_bool(elem, tag: str) -> Optional[bool]:
    """Get boolean value of child element."""
    text = _get_text(elem, tag)
    if text:
        return text.upper() == 'TRUE'
    return None


def _parse_yeasts(recipe_elem) -> list[ParsedYeast]:
    """Parse YEASTS section."""
    yeasts = []
    for yeast_elem in recipe_elem.findall('.//YEASTS/YEAST'):
        # Determine if amount is weight (dry) or volume (liquid)
        amount = _get_float(yeast_elem, 'AMOUNT')
        amount_is_weight = _get_bool(yeast_elem, 'AMOUNT_IS_WEIGHT')

        yeast = ParsedYeast(
            name=_get_text(yeast_elem, 'NAME') or "Unknown",
            lab=_get_text(yeast_elem, 'LABORATORY'),
            product_id=_get_text(yeast_elem, 'PRODUCT_ID'),
            type=_get_text(yeast_elem, 'TYPE'),
            form=_get_text(yeast_elem, 'FORM'),
            attenuation_percent=_get_float(yeast_elem, 'ATTENUATION'),
            temp_min_c=_get_float(yeast_elem, 'MIN_TEMPERATURE'),
            temp_max_c=_get_float(yeast_elem, 'MAX_TEMPERATURE'),
            flocculation=_get_text(yeast_elem, 'FLOCCULATION'),
            amount_kg=amount if amount_is_weight else None,
            amount_l=amount if amount_is_weight is False else None,
            add_to_secondary=_get_bool(yeast_elem, 'ADD_TO_SECONDARY'),
            best_for=_get_text(yeast_elem, 'BEST_FOR'),
            times_cultured=_get_int(yeast_elem, 'TIMES_CULTURED'),
            max_reuse=_get_int(yeast_elem, 'MAX_REUSE'),
            notes=_get_text(yeast_elem, 'NOTES'),
        )
        yeasts.append(yeast)
    return yeasts


def _parse_miscs(recipe_elem) -> list[ParsedMisc]:
    """Parse MISCS section."""
    miscs = []
    for misc_elem in recipe_elem.findall('.//MISCS/MISC'):
        misc = ParsedMisc(
            name=_get_text(misc_elem, 'NAME') or "Unknown",
            type=_get_text(misc_elem, 'TYPE'),
            use=_get_text(misc_elem, 'USE'),
            time_min=_get_float(misc_elem, 'TIME'),
            amount_kg=_get_float(misc_elem, 'AMOUNT'),
            amount_is_weight=_get_bool(misc_elem, 'AMOUNT_IS_WEIGHT'),
            use_for=_get_text(misc_elem, 'USE_FOR'),
            notes=_get_text(misc_elem, 'NOTES'),
        )
        miscs.append(misc)
    return miscs


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
        raw_xml=raw_xml,

        # Expanded BeerXML fields
        brewer=_get_text(elem, 'BREWER'),
        asst_brewer=_get_text(elem, 'ASST_BREWER'),
        boil_size_l=_get_float(elem, 'BOIL_SIZE'),
        boil_time_min=_get_int(elem, 'BOIL_TIME'),
        efficiency_percent=_get_float(elem, 'EFFICIENCY'),
        primary_age_days=_get_int(elem, 'PRIMARY_AGE'),
        primary_temp_c=_get_float(elem, 'PRIMARY_TEMP'),
        secondary_age_days=_get_int(elem, 'SECONDARY_AGE'),
        secondary_temp_c=_get_float(elem, 'SECONDARY_TEMP'),
        tertiary_age_days=_get_int(elem, 'TERTIARY_AGE'),
        tertiary_temp_c=_get_float(elem, 'TERTIARY_TEMP'),
        age_days=_get_int(elem, 'AGE'),
        age_temp_c=_get_float(elem, 'AGE_TEMP'),
        carbonation_vols=_get_float(elem, 'CARBONATION'),
        forced_carbonation=_get_bool(elem, 'FORCED_CARBONATION'),
        priming_sugar_name=_get_text(elem, 'PRIMING_SUGAR_NAME'),
        priming_sugar_amount_kg=_get_float(elem, 'PRIMING_SUGAR_EQUIV'),
        taste_notes=_get_text(elem, 'TASTE_NOTES'),
        taste_rating=_get_float(elem, 'TASTE_RATING'),
        date=_get_text(elem, 'DATE'),
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
            type=_get_text(style_elem, 'TYPE'),
            og_min=_get_float(style_elem, 'OG_MIN'),
            og_max=_get_float(style_elem, 'OG_MAX'),
            fg_min=_get_float(style_elem, 'FG_MIN'),
            fg_max=_get_float(style_elem, 'FG_MAX'),
            ibu_min=_get_float(style_elem, 'IBU_MIN'),
            ibu_max=_get_float(style_elem, 'IBU_MAX'),
            color_min=_get_float(style_elem, 'COLOR_MIN'),
            color_max=_get_float(style_elem, 'COLOR_MAX'),
            abv_min=_get_float(style_elem, 'ABV_MIN'),
            abv_max=_get_float(style_elem, 'ABV_MAX'),
            carb_min=_get_float(style_elem, 'CARB_MIN'),
            carb_max=_get_float(style_elem, 'CARB_MAX'),
        )

    # Parse first yeast (for backward compatibility with old single-yeast field)
    yeast_elem = elem.find('.//YEASTS/YEAST')
    if yeast_elem is not None:
        amount = _get_float(yeast_elem, 'AMOUNT')
        amount_is_weight = _get_bool(yeast_elem, 'AMOUNT_IS_WEIGHT')

        recipe.yeast = ParsedYeast(
            name=_get_text(yeast_elem, 'NAME') or "Unknown",
            lab=_get_text(yeast_elem, 'LABORATORY'),
            product_id=_get_text(yeast_elem, 'PRODUCT_ID'),
            type=_get_text(yeast_elem, 'TYPE'),
            form=_get_text(yeast_elem, 'FORM'),
            attenuation_percent=_get_float(yeast_elem, 'ATTENUATION'),
            temp_min_c=_get_float(yeast_elem, 'MIN_TEMPERATURE'),
            temp_max_c=_get_float(yeast_elem, 'MAX_TEMPERATURE'),
            flocculation=_get_text(yeast_elem, 'FLOCCULATION'),
            amount_kg=amount if amount_is_weight else None,
            amount_l=amount if amount_is_weight is False else None,
            add_to_secondary=_get_bool(yeast_elem, 'ADD_TO_SECONDARY'),
            best_for=_get_text(yeast_elem, 'BEST_FOR'),
            times_cultured=_get_int(yeast_elem, 'TIMES_CULTURED'),
            max_reuse=_get_int(yeast_elem, 'MAX_REUSE'),
            notes=_get_text(yeast_elem, 'NOTES'),
        )

    # Parse fermentables
    recipe.fermentables = _parse_fermentables(elem)

    # Parse hops
    recipe.hops = _parse_hops(elem)

    # Parse yeasts (all yeasts, not just first one)
    recipe.yeasts = _parse_yeasts(elem)

    # Parse misc ingredients
    recipe.miscs = _parse_miscs(elem)

    return recipe
