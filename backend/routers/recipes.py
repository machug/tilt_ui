"""Recipe API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models import Recipe, RecipeCreate, RecipeResponse
from ..services.recipe_importer import import_beerxml_to_db

router = APIRouter(prefix="/api/recipes", tags=["recipes"])

# File upload constraints
MAX_FILE_SIZE = 1_000_000  # 1MB in bytes


@router.get("", response_model=list[RecipeResponse])
async def list_recipes(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List all recipes."""
    query = (
        select(Recipe)
        .options(selectinload(Recipe.style))
        .order_by(Recipe.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{recipe_id}", response_model=RecipeResponse)
async def get_recipe(recipe_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific recipe by ID."""
    query = (
        select(Recipe)
        .options(selectinload(Recipe.style))
        .where(Recipe.id == recipe_id)
    )
    result = await db.execute(query)
    recipe = result.scalar_one_or_none()

    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@router.post("", response_model=RecipeResponse, status_code=201)
async def create_recipe(
    recipe: RecipeCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new recipe manually."""
    db_recipe = Recipe(
        name=recipe.name,
        author=recipe.author,
        style_id=recipe.style_id,
        type=recipe.type,
        og_target=recipe.og_target,
        fg_target=recipe.fg_target,
        yeast_name=recipe.yeast_name,
        yeast_temp_min=recipe.yeast_temp_min,
        yeast_temp_max=recipe.yeast_temp_max,
        yeast_attenuation=recipe.yeast_attenuation,
        ibu_target=recipe.ibu_target,
        abv_target=recipe.abv_target,
        batch_size=recipe.batch_size,
        notes=recipe.notes,
    )
    db.add(db_recipe)
    await db.commit()
    await db.refresh(db_recipe)
    return db_recipe


@router.post("/import", response_model=list[RecipeResponse])
async def import_beerxml(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Import recipes from a BeerXML file."""
    # Validate filename extension (before reading)
    if not file.filename or not file.filename.lower().endswith('.xml'):
        raise HTTPException(
            status_code=400,
            detail="File must have .xml extension"
        )

    # Validate content type (before reading)
    if file.content_type and file.content_type not in ["text/xml", "application/xml"]:
        # Allow if no content type (some clients don't send it)
        if file.content_type != "application/octet-stream":
            raise HTTPException(status_code=400, detail="File must be XML")

    # Read file content with size validation
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 1MB)")

    # Parse and import BeerXML
    try:
        xml_content = content.decode("utf-8")
        recipe_id = await import_beerxml_to_db(db, xml_content)
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid BeerXML: {str(e)}")

    # Fetch the created recipe
    result = await db.execute(
        select(Recipe).where(Recipe.id == recipe_id)
    )
    recipe = result.scalar_one()

    return [recipe]


@router.delete("/{recipe_id}")
async def delete_recipe(recipe_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a recipe."""
    recipe = await db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    await db.delete(recipe)
    await db.commit()
    return {"status": "deleted"}
