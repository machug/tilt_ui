"""Tests for recipes API endpoints."""

import pytest


@pytest.mark.asyncio
async def test_list_recipes_empty(client):
    """GET /api/recipes should return empty list when no recipes exist."""
    response = await client.get("/api/recipes")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_recipe(client):
    """POST /api/recipes should create a new recipe."""
    recipe_data = {
        "name": "Test Recipe",
        "author": "Tester",
        "og_target": 1.050,
        "fg_target": 1.010,
        "yeast_name": "US-05",
        "yeast_temp_min": 15.0,
        "yeast_temp_max": 22.0,
    }

    response = await client.post("/api/recipes", json=recipe_data)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Recipe"
    assert data["og_target"] == 1.050
    assert data["yeast_temp_min"] == 15.0
    assert "id" in data


@pytest.mark.asyncio
async def test_get_recipe(client):
    """GET /api/recipes/{id} should return specific recipe."""
    # Create recipe first
    recipe_data = {"name": "Get Test Recipe"}
    create_response = await client.post("/api/recipes", json=recipe_data)
    recipe_id = create_response.json()["id"]

    # Get it
    response = await client.get(f"/api/recipes/{recipe_id}")

    assert response.status_code == 200
    assert response.json()["name"] == "Get Test Recipe"


@pytest.mark.asyncio
async def test_get_recipe_not_found(client):
    """GET /api/recipes/{id} should return 404 for non-existent recipe."""
    response = await client.get("/api/recipes/99999")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_import_beerxml(client):
    """POST /api/recipes/import should import BeerXML file."""
    beerxml = """<?xml version="1.0"?>
    <RECIPES>
      <RECIPE>
        <NAME>Imported IPA</NAME>
        <OG>1.065</OG>
        <FG>1.012</FG>
        <YEASTS>
          <YEAST>
            <NAME>US-05</NAME>
            <MIN_TEMPERATURE>15.0</MIN_TEMPERATURE>
            <MAX_TEMPERATURE>22.0</MAX_TEMPERATURE>
          </YEAST>
        </YEASTS>
      </RECIPE>
    </RECIPES>
    """

    response = await client.post(
        "/api/recipes/import",
        files={"file": ("recipe.xml", beerxml, "text/xml")},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Imported IPA"
    assert data[0]["og_target"] == 1.065
    assert data[0]["yeast_name"] == "US-05"


@pytest.mark.asyncio
async def test_delete_recipe(client):
    """DELETE /api/recipes/{id} should remove recipe."""
    # Create recipe first
    create_response = await client.post("/api/recipes", json={"name": "Delete Me"})
    recipe_id = create_response.json()["id"]

    # Delete it
    response = await client.delete(f"/api/recipes/{recipe_id}")
    assert response.status_code == 200

    # Verify deleted
    get_response = await client.get(f"/api/recipes/{recipe_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_import_beerxml_invalid_extension(client):
    """POST /api/recipes/import should reject non-XML file extensions."""
    response = await client.post(
        "/api/recipes/import",
        files={"file": ("recipe.txt", "not xml content", "text/plain")},
    )

    assert response.status_code == 400
    assert "extension" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_import_beerxml_invalid_mime_type(client):
    """POST /api/recipes/import should reject invalid MIME types."""
    response = await client.post(
        "/api/recipes/import",
        files={"file": ("recipe.xml", "content", "text/plain")},
    )

    assert response.status_code == 400
    assert "xml" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_import_beerxml_file_too_large(client):
    """POST /api/recipes/import should reject files larger than 1MB."""
    # Create content larger than 1MB
    large_content = "x" * (1_000_001)

    response = await client.post(
        "/api/recipes/import",
        files={"file": ("recipe.xml", large_content, "text/xml")},
    )

    assert response.status_code == 400
    assert "large" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_import_beerxml_invalid_xml(client):
    """POST /api/recipes/import should reject malformed XML."""
    invalid_xml = "<RECIPES><RECIPE>unclosed tag"

    response = await client.post(
        "/api/recipes/import",
        files={"file": ("recipe.xml", invalid_xml, "text/xml")},
    )

    assert response.status_code == 400
    assert "beerxml" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_import_beerxml_non_utf8(client):
    """POST /api/recipes/import should reject non-UTF-8 encoded files."""
    # Use Latin-1 encoding
    non_utf8_content = b"<?xml version='1.0'?><RECIPES><RECIPE><NAME>\xe9</NAME></RECIPE></RECIPES>"

    response = await client.post(
        "/api/recipes/import",
        files={"file": ("recipe.xml", non_utf8_content, "text/xml")},
    )

    assert response.status_code == 400
    assert "utf-8" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_import_beerxml_empty_file(client):
    """POST /api/recipes/import should reject empty XML files."""
    response = await client.post(
        "/api/recipes/import",
        files={"file": ("recipe.xml", "", "text/xml")},
    )

    assert response.status_code == 400
