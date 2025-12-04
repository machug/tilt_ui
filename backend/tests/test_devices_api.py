"""Tests for device CRUD API endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession



@pytest.mark.asyncio
class TestDevicesAPI:
    """Test device CRUD endpoints."""

    async def test_list_devices_empty(self, client: AsyncClient):
        """Test listing devices when none exist."""
        response = await client.get("/api/devices")
        assert response.status_code == 200
        assert response.json() == []

    async def test_create_device(self, client: AsyncClient, test_db: AsyncSession):
        """Test creating a new device."""
        device_data = {
            "id": "test-device-001",
            "device_type": "ispindel",
            "name": "My iSpindel",
            "display_name": "iSpindel #1",
            "beer_name": "Test IPA",
            "original_gravity": 1.055,
            "native_gravity_unit": "sg",
            "native_temp_unit": "c",
            "calibration_type": "polynomial",
            "calibration_data": {"coefficients": [0, 1, 0.5]},
        }

        response = await client.post("/api/devices", json=device_data)
        assert response.status_code == 201
        data = response.json()

        assert data["id"] == "test-device-001"
        assert data["device_type"] == "ispindel"
        assert data["name"] == "My iSpindel"
        assert data["display_name"] == "iSpindel #1"
        assert data["beer_name"] == "Test IPA"
        assert data["original_gravity"] == 1.055
        assert data["calibration_data"] == {"coefficients": [0, 1, 0.5]}

    async def test_create_device_duplicate(self, client: AsyncClient, test_db: AsyncSession):
        """Test creating a device with duplicate ID fails."""
        device_data = {
            "id": "test-device-002",
            "device_type": "tilt",
            "name": "Tilt Red",
        }

        # Create first device
        response1 = await client.post("/api/devices", json=device_data)
        assert response1.status_code == 201

        # Try to create duplicate
        response2 = await client.post("/api/devices", json=device_data)
        assert response2.status_code == 400
        assert "already exists" in response2.json()["detail"]

    async def test_create_device_invalid_type(self, client: AsyncClient):
        """Test creating device with invalid device_type fails."""
        device_data = {
            "id": "test-device-003",
            "device_type": "invalid",
            "name": "Invalid Device",
        }

        response = await client.post("/api/devices", json=device_data)
        assert response.status_code == 422  # Validation error

    async def test_create_device_invalid_og(self, client: AsyncClient):
        """Test creating device with invalid OG fails."""
        device_data = {
            "id": "test-device-004",
            "device_type": "tilt",
            "name": "Test Tilt",
            "original_gravity": 2.0,  # Invalid
        }

        response = await client.post("/api/devices", json=device_data)
        assert response.status_code == 422  # Validation error

    async def test_list_devices(self, client: AsyncClient, test_db: AsyncSession):
        """Test listing all devices."""
        # Create multiple devices
        devices = [
            {
                "id": "tilt-red",
                "device_type": "tilt",
                "name": "Tilt Red",
                "color": "RED",
            },
            {
                "id": "ispindel-001",
                "device_type": "ispindel",
                "name": "iSpindel #1",
            },
            {
                "id": "gravitymon-001",
                "device_type": "gravitymon",
                "name": "GravityMon #1",
            },
        ]

        for device in devices:
            await client.post("/api/devices", json=device)

        # List all devices
        response = await client.get("/api/devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

        # Verify order (newest first - created_at desc)
        ids = [d["id"] for d in data]
        assert "gravitymon-001" in ids
        assert "ispindel-001" in ids
        assert "tilt-red" in ids

    async def test_list_devices_filter_by_type(self, client: AsyncClient, test_db: AsyncSession):
        """Test filtering devices by device_type."""
        # Create devices of different types
        devices = [
            {"id": "tilt-1", "device_type": "tilt", "name": "Tilt 1"},
            {"id": "tilt-2", "device_type": "tilt", "name": "Tilt 2"},
            {"id": "ispindel-1", "device_type": "ispindel", "name": "iSpindel 1"},
        ]

        for device in devices:
            await client.post("/api/devices", json=device)

        # Filter by tilt
        response = await client.get("/api/devices?device_type=tilt")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(d["device_type"] == "tilt" for d in data)

        # Filter by ispindel
        response = await client.get("/api/devices?device_type=ispindel")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["device_type"] == "ispindel"

    async def test_get_device(self, client: AsyncClient, test_db: AsyncSession):
        """Test getting a specific device."""
        device_data = {
            "id": "test-get",
            "device_type": "tilt",
            "name": "Test Device",
            "display_name": "My Test Device",
        }

        # Create device
        await client.post("/api/devices", json=device_data)

        # Get device
        response = await client.get("/api/devices/test-get")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test-get"
        assert data["name"] == "Test Device"
        assert data["display_name"] == "My Test Device"

    async def test_get_device_not_found(self, client: AsyncClient):
        """Test getting non-existent device returns 404."""
        response = await client.get("/api/devices/nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    async def test_update_device(self, client: AsyncClient, test_db: AsyncSession):
        """Test updating device properties."""
        # Create device
        device_data = {
            "id": "test-update",
            "device_type": "ispindel",
            "name": "Original Name",
            "beer_name": "Original Beer",
        }
        await client.post("/api/devices", json=device_data)

        # Update device
        update_data = {
            "name": "Updated Name",
            "beer_name": "Updated Beer",
            "original_gravity": 1.060,
        }
        response = await client.put("/api/devices/test-update", json=update_data)
        assert response.status_code == 200
        data = response.json()

        assert data["name"] == "Updated Name"
        assert data["beer_name"] == "Updated Beer"
        assert data["original_gravity"] == 1.060

    async def test_update_device_partial(self, client: AsyncClient, test_db: AsyncSession):
        """Test partial update of device."""
        # Create device
        device_data = {
            "id": "test-partial",
            "device_type": "tilt",
            "name": "Original",
            "beer_name": "Original Beer",
        }
        await client.post("/api/devices", json=device_data)

        # Update only beer_name
        update_data = {"beer_name": "New Beer"}
        response = await client.put("/api/devices/test-partial", json=update_data)
        assert response.status_code == 200
        data = response.json()

        # Beer name updated, name unchanged
        assert data["name"] == "Original"
        assert data["beer_name"] == "New Beer"

    async def test_update_device_calibration_data(self, client: AsyncClient, test_db: AsyncSession):
        """Test updating calibration data."""
        # Create device
        device_data = {
            "id": "test-calibration",
            "device_type": "ispindel",
            "name": "iSpindel",
            "calibration_type": "none",
        }
        await client.post("/api/devices", json=device_data)

        # Update with calibration data
        update_data = {
            "calibration_type": "polynomial",
            "calibration_data": {
                "coefficients": [0.001, -0.131, 3.871, -14.054],
                "order": 3,
            },
        }
        response = await client.put("/api/devices/test-calibration", json=update_data)
        assert response.status_code == 200
        data = response.json()

        assert data["calibration_type"] == "polynomial"
        assert data["calibration_data"]["coefficients"] == [0.001, -0.131, 3.871, -14.054]
        assert data["calibration_data"]["order"] == 3

    async def test_update_device_not_found(self, client: AsyncClient):
        """Test updating non-existent device returns 404."""
        update_data = {"name": "New Name"}
        response = await client.put("/api/devices/nonexistent", json=update_data)
        assert response.status_code == 404

    async def test_delete_device(self, client: AsyncClient, test_db: AsyncSession):
        """Test deleting a device."""
        # Create device
        device_data = {
            "id": "test-delete",
            "device_type": "tilt",
            "name": "To Be Deleted",
        }
        await client.post("/api/devices", json=device_data)

        # Delete device
        response = await client.delete("/api/devices/test-delete")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        assert data["device_id"] == "test-delete"

        # Verify device is gone
        response = await client.get("/api/devices/test-delete")
        assert response.status_code == 404

    async def test_delete_device_not_found(self, client: AsyncClient):
        """Test deleting non-existent device returns 404."""
        response = await client.delete("/api/devices/nonexistent")
        assert response.status_code == 404

    async def test_device_with_tilt_legacy_fields(self, client: AsyncClient, test_db: AsyncSession):
        """Test device creation with Tilt legacy fields (color, mac)."""
        device_data = {
            "id": "tilt-purple",
            "device_type": "tilt",
            "name": "Tilt Purple",
            "color": "PURPLE",
            "mac": "AA:BB:CC:DD:EE:FF",
        }

        response = await client.post("/api/devices", json=device_data)
        assert response.status_code == 201
        data = response.json()

        assert data["color"] == "PURPLE"
        assert data["mac"] == "AA:BB:CC:DD:EE:FF"
