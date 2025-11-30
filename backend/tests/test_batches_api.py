"""Tests for batches API endpoints."""

import pytest


@pytest.mark.asyncio
async def test_list_batches_empty(client):
    """GET /api/batches should return empty list when no batches exist."""
    response = await client.get("/api/batches")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_batch(client):
    """POST /api/batches should create a new batch."""
    batch_data = {
        "status": "planning",
        "name": "Test Batch",
    }

    response = await client.post("/api/batches", json=batch_data)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Batch"
    assert data["status"] == "planning"
    assert data["batch_number"] == 1


@pytest.mark.asyncio
async def test_create_batch_with_recipe(client):
    """POST /api/batches should link to recipe and auto-name."""
    # Create recipe first
    recipe_response = await client.post("/api/recipes", json={"name": "IPA Recipe"})
    recipe_id = recipe_response.json()["id"]

    # Create batch linked to recipe
    batch_data = {
        "recipe_id": recipe_id,
        "status": "planning",
    }

    response = await client.post("/api/batches", json=batch_data)

    assert response.status_code == 201
    data = response.json()
    assert data["recipe_id"] == recipe_id
    assert data["name"] == "IPA Recipe"  # Auto-named from recipe


@pytest.mark.asyncio
async def test_update_batch_status(client):
    """PUT /api/batches/{id} should update status and set timestamps."""
    # Create batch
    create_response = await client.post("/api/batches", json={"name": "Update Test"})
    batch_id = create_response.json()["id"]

    # Update to fermenting
    response = await client.put(
        f"/api/batches/{batch_id}",
        json={"status": "fermenting"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "fermenting"
    assert data["start_time"] is not None  # Auto-set


@pytest.mark.asyncio
async def test_get_batch_not_found(client):
    """GET /api/batches/{id} should return 404 for non-existent batch."""
    response = await client.get("/api/batches/99999")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_batch_progress(client):
    """GET /api/batches/{id}/progress should return progress data."""
    # Create recipe with targets
    recipe_response = await client.post("/api/recipes", json={
        "name": "Progress Test",
        "og_target": 1.050,
        "fg_target": 1.010,
        "yeast_temp_min": 18.0,
        "yeast_temp_max": 22.0,
    })
    recipe_id = recipe_response.json()["id"]

    # Create batch
    batch_response = await client.post("/api/batches", json={
        "recipe_id": recipe_id,
        "status": "fermenting",
        "measured_og": 1.052,
    })
    batch_id = batch_response.json()["id"]

    # Get progress
    response = await client.get(f"/api/batches/{batch_id}/progress")

    assert response.status_code == 200
    data = response.json()
    assert data["batch_id"] == batch_id
    assert data["recipe_name"] == "Progress Test"
    assert data["targets"]["og"] == 1.050
    assert data["targets"]["fg"] == 1.010
    assert data["measured"]["og"] == 1.052
