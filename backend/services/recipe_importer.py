"""Service for importing BeerXML into database."""

from sqlalchemy.ext.asyncio import AsyncSession
from backend.services.beerxml_parser import parse_beerxml
from backend.models import (
    Recipe, RecipeFermentable, RecipeHop,
    RecipeYeast, RecipeMisc
)


async def import_beerxml_to_db(db: AsyncSession, xml_content: str) -> int:
    """Import BeerXML and save to database.

    Args:
        db: Database session
        xml_content: BeerXML 1.0 string

    Returns:
        Recipe ID of first imported recipe
    """
    # Parse XML
    parsed_recipes = parse_beerxml(xml_content)
    if not parsed_recipes:
        raise ValueError("No recipes found in BeerXML")

    # Take first recipe (most BeerXML exports contain one recipe)
    parsed = parsed_recipes[0]

    # Create Recipe
    recipe = Recipe(
        name=parsed.name,
        author=parsed.author,
        type=parsed.type,
        og_target=parsed.og,
        fg_target=parsed.fg,
        ibu_target=parsed.ibu,
        srm_target=parsed.srm,
        abv_target=parsed.abv,
        batch_size=parsed.batch_size,
        beerxml_content=parsed.raw_xml,
    )

    # Add backward-compatible yeast fields from first yeast (for existing UI)
    if parsed.yeast:
        recipe.yeast_name = parsed.yeast.name
        recipe.yeast_lab = parsed.yeast.lab
        recipe.yeast_product_id = parsed.yeast.product_id
        recipe.yeast_temp_min = parsed.yeast.temp_min_c
        recipe.yeast_temp_max = parsed.yeast.temp_max_c
        recipe.yeast_attenuation = parsed.yeast.attenuation_percent

    db.add(recipe)
    await db.flush()  # Get recipe.id

    # Add fermentables
    for f in parsed.fermentables:
        fermentable = RecipeFermentable(
            recipe_id=recipe.id,
            name=f.name,
            type=f.type,
            amount_kg=f.amount_kg,
            yield_percent=f.yield_percent,
            color_lovibond=f.color_lovibond,
            origin=f.origin,
            supplier=f.supplier,
            notes=f.notes,
            add_after_boil=f.add_after_boil,
            coarse_fine_diff=f.coarse_fine_diff,
            moisture=f.moisture,
            diastatic_power=f.diastatic_power,
            protein=f.protein,
            max_in_batch=f.max_in_batch,
            recommend_mash=f.recommend_mash,
        )
        db.add(fermentable)

    # Add hops
    for h in parsed.hops:
        hop = RecipeHop(
            recipe_id=recipe.id,
            name=h.name,
            alpha_percent=h.alpha_percent,
            amount_kg=h.amount_kg,
            use=h.use,
            time_min=h.time_min,
            form=h.form,
            type=h.type,
            origin=h.origin,
            substitutes=h.substitutes,
            beta_percent=h.beta_percent,
            hsi=h.hsi,
            humulene=h.humulene,
            caryophyllene=h.caryophyllene,
            cohumulone=h.cohumulone,
            myrcene=h.myrcene,
            notes=h.notes,
        )
        db.add(hop)

    # Add yeasts
    for y in parsed.yeasts:
        yeast = RecipeYeast(
            recipe_id=recipe.id,
            name=y.name,
            lab=y.lab,
            product_id=y.product_id,
            type=y.type,
            form=y.form,
            attenuation_percent=y.attenuation_percent,
            temp_min_c=y.temp_min_c,
            temp_max_c=y.temp_max_c,
            flocculation=y.flocculation,
            amount_l=y.amount_l,
            amount_kg=y.amount_kg,
            add_to_secondary=y.add_to_secondary,
            best_for=y.best_for,
            times_cultured=y.times_cultured,
            max_reuse=y.max_reuse,
            notes=y.notes,
        )
        db.add(yeast)

    # Add miscs
    for m in parsed.miscs:
        misc = RecipeMisc(
            recipe_id=recipe.id,
            name=m.name,
            type=m.type,
            use=m.use,
            time_min=m.time_min,
            amount_kg=m.amount_kg,
            amount_is_weight=m.amount_is_weight,
            use_for=m.use_for,
            notes=m.notes,
        )
        db.add(misc)

    await db.commit()
    return recipe.id
