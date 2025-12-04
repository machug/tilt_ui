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
async def test_create_batch_with_heater(client):
    """POST /api/batches should create batch with heater entity."""
    batch_data = {
        "status": "planning",
        "name": "Heater Test Batch",
        "heater_entity_id": "switch.fermenter_heater_1",
        "temp_target": 68.0,
        "temp_hysteresis": 1.0,
    }

    response = await client.post("/api/batches", json=batch_data)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Heater Test Batch"
    assert data["heater_entity_id"] == "switch.fermenter_heater_1"
    assert data["temp_target"] == 68.0
    assert data["temp_hysteresis"] == 1.0


@pytest.mark.asyncio
async def test_update_batch_heater(client):
    """PUT /api/batches/{id} should update heater settings."""
    # Create batch
    create_response = await client.post("/api/batches", json={"name": "Heater Update Test"})
    batch_id = create_response.json()["id"]

    # Update heater settings
    response = await client.put(
        f"/api/batches/{batch_id}",
        json={
            "heater_entity_id": "switch.new_heater",
            "temp_target": 72.0,
            "temp_hysteresis": 1.5,
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["heater_entity_id"] == "switch.new_heater"
    assert data["temp_target"] == 72.0
    assert data["temp_hysteresis"] == 1.5


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


@pytest.mark.asyncio
async def test_create_batch_invalid_heater_entity(client):
    """POST /api/batches should reject invalid heater entity format."""
    batch_data = {
        "name": "Invalid Heater Test",
        "heater_entity_id": "sensor.temperature",  # Wrong domain - must be switch. or input_boolean.
    }

    response = await client.post("/api/batches", json=batch_data)

    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_update_batch_invalid_heater_entity(client):
    """PUT /api/batches/{id} should reject invalid heater entity format."""
    # Create valid batch first
    create_response = await client.post("/api/batches", json={"name": "Valid Batch"})
    batch_id = create_response.json()["id"]

    # Try to update with invalid heater entity
    response = await client.put(
        f"/api/batches/{batch_id}",
        json={"heater_entity_id": "light.living_room"}  # Wrong domain
    )

    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_get_batch_control_status(client):
    """GET /api/control/batch/{id}/status should return control status."""
    # Create batch with heater
    batch_response = await client.post("/api/batches", json={
        "name": "Control Test",
        "status": "fermenting",
        "heater_entity_id": "switch.heater_1",
        "temp_target": 68.0,
        "temp_hysteresis": 1.0,
    })
    batch_id = batch_response.json()["id"]

    # Get control status
    response = await client.get(f"/api/control/batch/{batch_id}/status")

    assert response.status_code == 200
    data = response.json()
    assert data["batch_id"] == batch_id
    assert data["heater_entity"] == "switch.heater_1"
    assert data["target_temp"] == 68.0
    assert data["hysteresis"] == 1.0
    assert "state_available" in data  # New field indicating if runtime state is available


@pytest.mark.asyncio
async def test_batch_control_status_state_available_for_completed_batch(client):
    """GET /api/control/batch/{id}/status should indicate state_available=False for completed batches."""
    # Create batch and complete it
    batch_response = await client.post("/api/batches", json={
        "name": "Completed Batch",
        "status": "fermenting",
        "heater_entity_id": "switch.heater_2",
    })
    batch_id = batch_response.json()["id"]

    # Mark batch as completed (this will trigger cleanup of runtime state)
    await client.put(f"/api/batches/{batch_id}", json={"status": "completed"})

    # Get control status - should indicate state was cleaned up
    response = await client.get(f"/api/control/batch/{batch_id}/status")

    assert response.status_code == 200
    data = response.json()
    assert data["batch_id"] == batch_id
    assert data["state_available"] is False  # Runtime state cleaned up for completed batch


@pytest.mark.asyncio
async def test_heater_entity_conflict_on_create(client):
    """POST /api/batches should reject duplicate heater entities for fermenting batches."""
    # Create first fermenting batch with a heater
    batch1_data = {
        "status": "fermenting",
        "name": "Batch 1",
        "heater_entity_id": "switch.heater_1",
    }
    response = await client.post("/api/batches", json=batch1_data)
    assert response.status_code == 201

    # Try to create second fermenting batch with the same heater
    batch2_data = {
        "status": "fermenting",
        "name": "Batch 2",
        "heater_entity_id": "switch.heater_1",
    }
    response = await client.post("/api/batches", json=batch2_data)

    assert response.status_code == 400
    assert "already in use" in response.json()["detail"]
    assert "switch.heater_1" in response.json()["detail"]


@pytest.mark.asyncio
async def test_heater_entity_no_conflict_different_status(client):
    """POST /api/batches should allow same heater if first batch is not fermenting."""
    # Create completed batch with a heater
    batch1_data = {
        "status": "completed",
        "name": "Batch 1",
        "heater_entity_id": "switch.heater_1",
    }
    response = await client.post("/api/batches", json=batch1_data)
    assert response.status_code == 201

    # Create fermenting batch with the same heater - should work
    batch2_data = {
        "status": "fermenting",
        "name": "Batch 2",
        "heater_entity_id": "switch.heater_1",
    }
    response = await client.post("/api/batches", json=batch2_data)

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_heater_entity_conflict_on_update(client):
    """PATCH /api/batches/{id} should reject heater changes that create conflicts."""
    # Create two fermenting batches with different heaters
    batch1_data = {
        "status": "fermenting",
        "name": "Batch 1",
        "heater_entity_id": "switch.heater_1",
    }
    response1 = await client.post("/api/batches", json=batch1_data)
    assert response1.status_code == 201
    _batch1_id = response1.json()["id"]  # Created but not used in test

    batch2_data = {
        "status": "fermenting",
        "name": "Batch 2",
        "heater_entity_id": "switch.heater_2",
    }
    response2 = await client.post("/api/batches", json=batch2_data)
    assert response2.status_code == 201
    batch2_id = response2.json()["id"]

    # Try to update batch 2 to use heater_1 (already in use by batch 1)
    update_data = {"heater_entity_id": "switch.heater_1"}
    response = await client.put(f"/api/batches/{batch2_id}", json=update_data)

    assert response.status_code == 400
    assert "already in use" in response.json()["detail"]
    assert "switch.heater_1" in response.json()["detail"]
