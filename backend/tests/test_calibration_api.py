"""Tests for device calibration API endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
class TestCalibrationAPI:
    """Test device calibration endpoints."""

    async def test_get_calibration_default(self, client: AsyncClient, test_db: AsyncSession):
        """Test getting calibration for a device with default settings."""
        # Create a device
        device_data = {
            "id": "test-device",
            "device_type": "tilt",
            "name": "Test Device",
        }
        await client.post("/api/devices", json=device_data)

        # Get calibration
        response = await client.get("/api/devices/test-device/calibration")
        assert response.status_code == 200
        data = response.json()
        assert data["calibration_type"] == "none"
        assert data["calibration_data"] is None

    async def test_get_calibration_not_found(self, client: AsyncClient):
        """Test getting calibration for non-existent device."""
        response = await client.get("/api/devices/nonexistent/calibration")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    async def test_set_offset_calibration(self, client: AsyncClient, test_db: AsyncSession):
        """Test setting offset calibration."""
        # Create device
        device_data = {
            "id": "test-offset",
            "device_type": "tilt",
            "name": "Test Tilt",
        }
        await client.post("/api/devices", json=device_data)

        # Set offset calibration
        calibration_data = {
            "calibration_type": "offset",
            "calibration_data": {
                "sg_offset": 0.002,
                "temp_offset": 1.5,
            },
        }
        response = await client.put("/api/devices/test-offset/calibration", json=calibration_data)
        assert response.status_code == 200
        data = response.json()
        assert data["calibration_type"] == "offset"
        assert data["calibration_data"]["sg_offset"] == 0.002
        assert data["calibration_data"]["temp_offset"] == 1.5

        # Verify with GET
        response = await client.get("/api/devices/test-offset/calibration")
        assert response.status_code == 200
        data = response.json()
        assert data["calibration_type"] == "offset"
        assert data["calibration_data"]["sg_offset"] == 0.002

    async def test_set_offset_calibration_sg_only(self, client: AsyncClient, test_db: AsyncSession):
        """Test setting offset calibration with only SG offset."""
        # Create device
        device_data = {
            "id": "test-sg-offset",
            "device_type": "tilt",
            "name": "Test Tilt",
        }
        await client.post("/api/devices", json=device_data)

        # Set offset calibration with only sg_offset
        calibration_data = {
            "calibration_type": "offset",
            "calibration_data": {
                "sg_offset": 0.003,
            },
        }
        response = await client.put("/api/devices/test-sg-offset/calibration", json=calibration_data)
        assert response.status_code == 200
        data = response.json()
        assert data["calibration_type"] == "offset"
        assert data["calibration_data"]["sg_offset"] == 0.003

    async def test_set_polynomial_calibration(self, client: AsyncClient, test_db: AsyncSession):
        """Test setting polynomial calibration for iSpindel."""
        # Create device
        device_data = {
            "id": "test-ispindel",
            "device_type": "ispindel",
            "name": "iSpindel #1",
        }
        await client.post("/api/devices", json=device_data)

        # Set polynomial calibration
        calibration_data = {
            "calibration_type": "polynomial",
            "calibration_data": {
                "coefficients": [0.001, -0.131, 3.871, -14.054],
            },
        }
        response = await client.put("/api/devices/test-ispindel/calibration", json=calibration_data)
        assert response.status_code == 200
        data = response.json()
        assert data["calibration_type"] == "polynomial"
        assert data["calibration_data"]["coefficients"] == [0.001, -0.131, 3.871, -14.054]

    async def test_set_linear_calibration(self, client: AsyncClient, test_db: AsyncSession):
        """Test setting linear calibration with multiple points."""
        # Create device
        device_data = {
            "id": "test-linear",
            "device_type": "tilt",
            "name": "Test Tilt",
        }
        await client.post("/api/devices", json=device_data)

        # Set linear calibration
        calibration_data = {
            "calibration_type": "linear",
            "calibration_data": {
                "points": [
                    [1.000, 1.002],
                    [1.050, 1.048],
                    [1.100, 1.095],
                ],
            },
        }
        response = await client.put("/api/devices/test-linear/calibration", json=calibration_data)
        assert response.status_code == 200
        data = response.json()
        assert data["calibration_type"] == "linear"
        assert len(data["calibration_data"]["points"]) == 3
        assert data["calibration_data"]["points"][0] == [1.000, 1.002]

    async def test_set_none_calibration(self, client: AsyncClient, test_db: AsyncSession):
        """Test setting calibration to none."""
        # Create device with calibration
        device_data = {
            "id": "test-none",
            "device_type": "tilt",
            "name": "Test Tilt",
            "calibration_type": "offset",
            "calibration_data": {"sg_offset": 0.002},
        }
        await client.post("/api/devices", json=device_data)

        # Set to none
        calibration_data = {
            "calibration_type": "none",
        }
        response = await client.put("/api/devices/test-none/calibration", json=calibration_data)
        assert response.status_code == 200
        data = response.json()
        assert data["calibration_type"] == "none"
        assert data["calibration_data"] is None

    async def test_set_calibration_not_found(self, client: AsyncClient):
        """Test setting calibration on non-existent device."""
        calibration_data = {
            "calibration_type": "none",
        }
        response = await client.put("/api/devices/nonexistent/calibration", json=calibration_data)
        assert response.status_code == 404

    async def test_validate_offset_requires_data(self, client: AsyncClient, test_db: AsyncSession):
        """Test that offset calibration requires calibration_data."""
        # Create device
        device_data = {
            "id": "test-validate-1",
            "device_type": "tilt",
            "name": "Test Tilt",
        }
        await client.post("/api/devices", json=device_data)

        # Try to set offset without data
        calibration_data = {
            "calibration_type": "offset",
        }
        response = await client.put("/api/devices/test-validate-1/calibration", json=calibration_data)
        assert response.status_code == 422  # Validation error

    async def test_validate_offset_requires_offset_fields(self, client: AsyncClient, test_db: AsyncSession):
        """Test that offset calibration requires sg_offset or temp_offset."""
        # Create device
        device_data = {
            "id": "test-validate-2",
            "device_type": "tilt",
            "name": "Test Tilt",
        }
        await client.post("/api/devices", json=device_data)

        # Try to set offset with empty data
        calibration_data = {
            "calibration_type": "offset",
            "calibration_data": {},
        }
        response = await client.put("/api/devices/test-validate-2/calibration", json=calibration_data)
        assert response.status_code == 422  # Validation error

    async def test_validate_polynomial_requires_coefficients(self, client: AsyncClient, test_db: AsyncSession):
        """Test that polynomial calibration requires coefficients."""
        # Create device
        device_data = {
            "id": "test-validate-3",
            "device_type": "ispindel",
            "name": "iSpindel",
        }
        await client.post("/api/devices", json=device_data)

        # Try to set polynomial without coefficients
        calibration_data = {
            "calibration_type": "polynomial",
            "calibration_data": {},
        }
        response = await client.put("/api/devices/test-validate-3/calibration", json=calibration_data)
        assert response.status_code == 422  # Validation error

    async def test_validate_linear_requires_points(self, client: AsyncClient, test_db: AsyncSession):
        """Test that linear calibration requires points array."""
        # Create device
        device_data = {
            "id": "test-validate-4",
            "device_type": "tilt",
            "name": "Test Tilt",
        }
        await client.post("/api/devices", json=device_data)

        # Try to set linear without points
        calibration_data = {
            "calibration_type": "linear",
            "calibration_data": {},
        }
        response = await client.put("/api/devices/test-validate-4/calibration", json=calibration_data)
        assert response.status_code == 422  # Validation error

    async def test_validate_linear_requires_two_points(self, client: AsyncClient, test_db: AsyncSession):
        """Test that linear calibration requires at least 2 points."""
        # Create device
        device_data = {
            "id": "test-validate-5",
            "device_type": "tilt",
            "name": "Test Tilt",
        }
        await client.post("/api/devices", json=device_data)

        # Try to set linear with only one point
        calibration_data = {
            "calibration_type": "linear",
            "calibration_data": {
                "points": [[1.000, 1.002]],
            },
        }
        response = await client.put("/api/devices/test-validate-5/calibration", json=calibration_data)
        assert response.status_code == 422  # Validation error

    async def test_validate_none_no_data(self, client: AsyncClient, test_db: AsyncSession):
        """Test that 'none' calibration type should not have calibration_data."""
        # Create device
        device_data = {
            "id": "test-validate-6",
            "device_type": "tilt",
            "name": "Test Tilt",
        }
        await client.post("/api/devices", json=device_data)

        # Try to set none with data
        calibration_data = {
            "calibration_type": "none",
            "calibration_data": {"sg_offset": 0.002},
        }
        response = await client.put("/api/devices/test-validate-6/calibration", json=calibration_data)
        assert response.status_code == 422  # Validation error

    async def test_test_calibration_offset(self, client: AsyncClient, test_db: AsyncSession):
        """Test calibration test endpoint with offset calibration."""
        # Create device with offset calibration
        device_data = {
            "id": "test-cal-offset",
            "device_type": "tilt",
            "name": "Test Tilt",
            "calibration_type": "offset",
            "calibration_data": {
                "sg_offset": 0.002,
                "temp_offset": 1.5,
            },
        }
        await client.post("/api/devices", json=device_data)

        # Test calibration
        test_data = {
            "raw_gravity": 1.050,
            "raw_temperature": 68.0,
        }
        response = await client.post("/api/devices/test-cal-offset/calibration/test", json=test_data)
        assert response.status_code == 200
        data = response.json()
        assert data["calibrated_gravity"] == 1.052  # 1.050 + 0.002
        assert data["calibrated_temperature"] == 69.5  # 68.0 + 1.5

    async def test_test_calibration_polynomial(self, client: AsyncClient, test_db: AsyncSession):
        """Test calibration test endpoint with polynomial calibration."""
        # Create device with polynomial calibration
        # Simple polynomial: SG = 0.002*angle + 0.98
        device_data = {
            "id": "test-cal-poly",
            "device_type": "ispindel",
            "name": "iSpindel",
            "calibration_type": "polynomial",
            "calibration_data": {
                "coefficients": [0.002, 0.98],  # 0.002*x + 0.98
            },
        }
        await client.post("/api/devices", json=device_data)

        # Test with angle
        test_data = {
            "angle": 25.0,
        }
        response = await client.post("/api/devices/test-cal-poly/calibration/test", json=test_data)
        assert response.status_code == 200
        data = response.json()
        # 0.002 * 25 + 0.98 = 0.05 + 0.98 = 1.03
        assert abs(data["calibrated_gravity"] - 1.03) < 0.0001

    async def test_test_calibration_linear(self, client: AsyncClient, test_db: AsyncSession):
        """Test calibration test endpoint with linear calibration."""
        # Create device with linear calibration
        device_data = {
            "id": "test-cal-linear",
            "device_type": "tilt",
            "name": "Test Tilt",
            "calibration_type": "linear",
            "calibration_data": {
                "points": [
                    [1.000, 1.002],
                    [1.050, 1.048],
                ],
            },
        }
        await client.post("/api/devices", json=device_data)

        # Test calibration - interpolate between points
        test_data = {
            "raw_gravity": 1.025,
        }
        response = await client.post("/api/devices/test-cal-linear/calibration/test", json=test_data)
        assert response.status_code == 200
        data = response.json()
        # Linear interpolation: 1.002 + (1.025 - 1.000) * (1.048 - 1.002) / (1.050 - 1.000)
        # = 1.002 + 0.025 * 0.046 / 0.050 = 1.002 + 0.023 = 1.025
        expected = 1.002 + (1.025 - 1.000) * (1.048 - 1.002) / (1.050 - 1.000)
        assert abs(data["calibrated_gravity"] - expected) < 0.0001

    async def test_test_calibration_none(self, client: AsyncClient, test_db: AsyncSession):
        """Test calibration test endpoint with no calibration."""
        # Create device with no calibration
        device_data = {
            "id": "test-cal-none",
            "device_type": "tilt",
            "name": "Test Tilt",
        }
        await client.post("/api/devices", json=device_data)

        # Test calibration - should return same values
        test_data = {
            "raw_gravity": 1.050,
            "raw_temperature": 68.0,
        }
        response = await client.post("/api/devices/test-cal-none/calibration/test", json=test_data)
        assert response.status_code == 200
        data = response.json()
        assert data["calibrated_gravity"] == 1.050
        assert data["calibrated_temperature"] == 68.0

    async def test_test_calibration_not_found(self, client: AsyncClient):
        """Test calibration test on non-existent device."""
        test_data = {
            "raw_gravity": 1.050,
        }
        response = await client.post("/api/devices/nonexistent/calibration/test", json=test_data)
        assert response.status_code == 404

    async def test_test_calibration_no_input(self, client: AsyncClient, test_db: AsyncSession):
        """Test calibration test endpoint requires at least one input."""
        # Create device
        device_data = {
            "id": "test-no-input",
            "device_type": "tilt",
            "name": "Test Tilt",
        }
        await client.post("/api/devices", json=device_data)

        # Test with no input values
        test_data = {}
        response = await client.post("/api/devices/test-no-input/calibration/test", json=test_data)
        assert response.status_code == 422  # Validation error

    async def test_test_calibration_gravity_only(self, client: AsyncClient, test_db: AsyncSession):
        """Test calibration test with only gravity input."""
        # Create device
        device_data = {
            "id": "test-gravity-only",
            "device_type": "tilt",
            "name": "Test Tilt",
            "calibration_type": "offset",
            "calibration_data": {
                "sg_offset": 0.002,
                "temp_offset": 1.0,
            },
        }
        await client.post("/api/devices", json=device_data)

        # Test with only gravity
        test_data = {
            "raw_gravity": 1.050,
        }
        response = await client.post("/api/devices/test-gravity-only/calibration/test", json=test_data)
        assert response.status_code == 200
        data = response.json()
        assert data["calibrated_gravity"] == 1.052
        assert data["calibrated_temperature"] is None

    async def test_test_calibration_temp_only(self, client: AsyncClient, test_db: AsyncSession):
        """Test calibration test with only temperature input."""
        # Create device
        device_data = {
            "id": "test-temp-only",
            "device_type": "tilt",
            "name": "Test Tilt",
            "calibration_type": "offset",
            "calibration_data": {
                "sg_offset": 0.002,
                "temp_offset": 1.5,
            },
        }
        await client.post("/api/devices", json=device_data)

        # Test with only temperature
        test_data = {
            "raw_temperature": 68.0,
        }
        response = await client.post("/api/devices/test-temp-only/calibration/test", json=test_data)
        assert response.status_code == 200
        data = response.json()
        assert data["calibrated_gravity"] is None
        assert data["calibrated_temperature"] == 69.5

    async def test_invalid_calibration_type(self, client: AsyncClient, test_db: AsyncSession):
        """Test setting invalid calibration type."""
        # Create device
        device_data = {
            "id": "test-invalid-type",
            "device_type": "tilt",
            "name": "Test Tilt",
        }
        await client.post("/api/devices", json=device_data)

        # Try invalid calibration type
        calibration_data = {
            "calibration_type": "invalid",
        }
        response = await client.put("/api/devices/test-invalid-type/calibration", json=calibration_data)
        assert response.status_code == 422  # Validation error
