"""Service for importing BeerXML into database."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.services.beerxml_parser import parse_beerxml
from backend.models import (
    Recipe, RecipeFermentable, RecipeHop,
    RecipeYeast, RecipeMisc, Style
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

    # Handle style - create or find existing
    style_id = None
    if parsed.style and parsed.style.name:
        # Generate style ID from guide, category_number, and style_letter
        guide = parsed.style.guide or "unknown"
        cat_num = parsed.style.category_number or "0"
        style_letter = parsed.style.style_letter or ""
        style_id = f"{guide.lower().replace(' ', '-')}-{cat_num}{style_letter.lower()}"

        # Check if style exists
        result = await db.execute(select(Style).where(Style.id == style_id))
        existing_style = result.scalar_one_or_none()

        if not existing_style:
            # Create new style
            style = Style(
                id=style_id,
                guide=guide,
                category_number=cat_num,
                style_letter=style_letter,
                name=parsed.style.name,
                category=parsed.style.category or parsed.style.name,
                type=parsed.style.type or "Ale",
                og_min=parsed.style.og_min,
                og_max=parsed.style.og_max,
                fg_min=parsed.style.fg_min,
                fg_max=parsed.style.fg_max,
                ibu_min=parsed.style.ibu_min,
                ibu_max=parsed.style.ibu_max,
                srm_min=parsed.style.color_min,
                srm_max=parsed.style.color_max,
                abv_min=parsed.style.abv_min,
                abv_max=parsed.style.abv_max,
            )
            db.add(style)
            await db.flush()

    # Create Recipe
    recipe = Recipe(
        name=parsed.name,
        author=parsed.author,
        style_id=style_id,
        type=parsed.type,
        og_target=parsed.og,
        fg_target=parsed.fg,
        ibu_target=parsed.ibu,
        srm_target=parsed.srm,
        abv_target=parsed.abv,
        batch_size=parsed.batch_size,
        beerxml_content=parsed.raw_xml,

        # Expanded BeerXML fields
        brewer=parsed.brewer,
        asst_brewer=parsed.asst_brewer,
        boil_size_l=parsed.boil_size_l,
        boil_time_min=parsed.boil_time_min,
        efficiency_percent=parsed.efficiency_percent,
        primary_age_days=parsed.primary_age_days,
        primary_temp_c=parsed.primary_temp_c,
        secondary_age_days=parsed.secondary_age_days,
        secondary_temp_c=parsed.secondary_temp_c,
        tertiary_age_days=parsed.tertiary_age_days,
        tertiary_temp_c=parsed.tertiary_temp_c,
        age_days=parsed.age_days,
        age_temp_c=parsed.age_temp_c,
        carbonation_vols=parsed.carbonation_vols,
        forced_carbonation=parsed.forced_carbonation,
        priming_sugar_name=parsed.priming_sugar_name,
        priming_sugar_amount_kg=parsed.priming_sugar_amount_kg,
        taste_notes=parsed.taste_notes,
        taste_rating=parsed.taste_rating,
        date=parsed.date,
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
