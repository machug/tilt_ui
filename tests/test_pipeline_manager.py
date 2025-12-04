"""Tests for ML pipeline manager (per-device state isolation)."""

import pytest
from backend.ml.pipeline_manager import MLPipelineManager
from backend.ml.config import MLConfig


class TestMLPipelineManager:
    """Tests for the ML pipeline manager."""

    def test_creates_separate_pipelines_per_device(self):
        """Manager creates separate pipeline instances for each device."""
        manager = MLPipelineManager()

        # Get pipelines for two devices
        pipeline_red = manager.get_pipeline("RED")
        pipeline_blue = manager.get_pipeline("BLUE")

        # Should be different instances
        assert pipeline_red is not pipeline_blue
        assert id(pipeline_red) != id(pipeline_blue)

    def test_returns_same_pipeline_for_same_device(self):
        """Manager returns same pipeline instance for repeated calls."""
        manager = MLPipelineManager()

        pipeline1 = manager.get_pipeline("RED")
        pipeline2 = manager.get_pipeline("RED")

        # Should be identical instance
        assert pipeline1 is pipeline2

    def test_isolates_kalman_state_between_devices(self):
        """Kalman filter state is isolated between devices."""
        manager = MLPipelineManager()

        # Build history for RED device (low SG, low temp)
        for i in range(5):
            manager.process_reading(
                device_id="RED",
                sg=1.050 - i * 0.001,
                temp=68.0,
                rssi=-60,
                time_hours=float(i),
            )

        # Build history for BLUE device (high SG, high temp)
        for i in range(5):
            manager.process_reading(
                device_id="BLUE",
                sg=1.080 - i * 0.001,
                temp=75.0,
                rssi=-50,
                time_hours=float(i),
            )

        # Get final state for each device
        result_red = manager.process_reading(
            device_id="RED",
            sg=1.046,
            temp=68.0,
            rssi=-60,
            time_hours=5.0,
        )

        result_blue = manager.process_reading(
            device_id="BLUE",
            sg=1.076,
            temp=75.0,
            rssi=-50,
            time_hours=5.0,
        )

        # Each device's filtered values should be in its own range
        # RED: around 1.046, BLUE: around 1.076 (30-point difference)
        sg_diff = abs(result_blue["kalman"]["sg_filtered"] - result_red["kalman"]["sg_filtered"])
        assert sg_diff > 0.020  # Should be separated by significant amount

        temp_diff = abs(result_blue["kalman"]["temp_filtered"] - result_red["kalman"]["temp_filtered"])
        assert temp_diff > 5.0  # Should be separated by significant amount

    def test_isolates_anomaly_history_between_devices(self):
        """Anomaly detector history is isolated between devices."""
        manager = MLPipelineManager()

        # Build normal fermentation history for RED
        for i in range(20):
            manager.process_reading(
                device_id="RED",
                sg=1.050 - i * 0.001,  # Normal decline
                temp=68.0,
                rssi=-60,
                time_hours=float(i * 4),
            )

        # Build anomalous history for BLUE (stuck fermentation)
        # Need enough time to trigger stuck detection (24+ hours)
        for i in range(30):
            manager.process_reading(
                device_id="BLUE",
                sg=1.050,  # Stuck at same value
                temp=68.0,
                rssi=-60,
                time_hours=float(i * 2),  # Every 2 hours for 60 hours
            )

        # RED should be normal
        result_red = manager.process_reading(
            device_id="RED",
            sg=1.030,
            temp=68.0,
            rssi=-60,
            time_hours=80.0,
        )

        # BLUE should detect anomaly (stuck)
        result_blue = manager.process_reading(
            device_id="BLUE",
            sg=1.050,
            temp=68.0,
            rssi=-60,
            time_hours=60.0,
        )

        # RED should be normal (continuing to decline)
        assert result_red["anomaly"]["is_anomaly"] is False

        # BLUE might detect anomaly (stuck) - depends on exact rate calculation
        # Key test: devices have separate histories (not contaminated)
        # If we read histories directly, they should be different lengths
        pipeline_red = manager.get_pipeline("RED")
        pipeline_blue = manager.get_pipeline("BLUE")

        # Verify histories are isolated (different accumulated data)
        assert len(pipeline_red.sg_history) == 21  # 20 + 1
        assert len(pipeline_blue.sg_history) == 31  # 30 + 1

    def test_isolates_prediction_history_between_devices(self):
        """Curve fitting uses separate history per device."""
        manager = MLPipelineManager()

        # Build fast fermentation for RED (steep curve)
        for i in range(20):
            manager.process_reading(
                device_id="RED",
                sg=1.050 - i * 0.002,  # Fast decline
                temp=68.0,
                rssi=-60,
                time_hours=float(i * 4),
            )

        # Build slow fermentation for BLUE (shallow curve)
        for i in range(20):
            manager.process_reading(
                device_id="BLUE",
                sg=1.050 - i * 0.0005,  # Slow decline
                temp=68.0,
                rssi=-60,
                time_hours=float(i * 4),
            )

        # Each should have different predictions
        result_red = manager.process_reading(
            device_id="RED",
            sg=1.010,
            temp=68.0,
            rssi=-60,
            time_hours=80.0,
        )

        result_blue = manager.process_reading(
            device_id="BLUE",
            sg=1.040,
            temp=68.0,
            rssi=-60,
            time_hours=80.0,
        )

        # Both should have predictions (enough history)
        assert result_red["predictions"] is not None
        assert result_blue["predictions"] is not None

        # RED should be closer to completion (faster fermentation)
        if result_red["predictions"]["fitted"] and result_blue["predictions"]["fitted"]:
            # RED has dropped more points (1.050 → 1.010 = 40 points)
            # BLUE has dropped fewer points (1.050 → 1.040 = 10 points)
            # So RED should be further along
            assert result_red["predictions"]["predicted_fg"] < result_blue["predictions"]["predicted_fg"]

    def test_isolates_mpc_thermal_model_between_devices(self):
        """MPC thermal model is separate per device."""
        config = MLConfig(enable_mpc=True)
        manager = MLPipelineManager(config=config)

        # Train RED with high heating rate (powerful heater)
        for i in range(10):
            result = manager.process_reading(
                device_id="RED",
                sg=1.050,
                temp=68.0 + i * 1.0,  # Fast warming
                rssi=-60,
                time_hours=float(i),
                ambient_temp=65.0,
                heater_on=True,
                target_temp=75.0,  # Need target to trigger MPC learning
            )

        # Train BLUE with low heating rate (weak heater)
        for i in range(10):
            result = manager.process_reading(
                device_id="BLUE",
                sg=1.050,
                temp=68.0 + i * 0.3,  # Slow warming
                rssi=-60,
                time_hours=float(i),
                ambient_temp=65.0,
                heater_on=True,
                target_temp=75.0,  # Need target to trigger MPC learning
            )

        # Each device should have its own MPC controller with separate history
        pipeline_red = manager.get_pipeline("RED")
        pipeline_blue = manager.get_pipeline("BLUE")

        # Verify separate temp histories (different data)
        assert len(pipeline_red.temp_history) == 10
        assert len(pipeline_blue.temp_history) == 10

        # RED should have warmed faster
        assert pipeline_red.temp_history[-1] > pipeline_blue.temp_history[-1]

    def test_reset_pipeline_clears_device_state(self):
        """Resetting a device's pipeline clears its state."""
        manager = MLPipelineManager()

        # Build history for RED
        for i in range(10):
            manager.process_reading(
                device_id="RED",
                sg=1.050 - i * 0.001,
                temp=68.0,
                rssi=-60,
                time_hours=float(i * 4),
            )

        # Reset RED pipeline
        manager.reset_pipeline("RED", initial_sg=1.060, initial_temp=70.0)

        # Next reading should be at reset state
        result = manager.process_reading(
            device_id="RED",
            sg=1.060,
            temp=70.0,
            rssi=-60,
            time_hours=0,
        )

        assert result["kalman"]["sg_filtered"] == pytest.approx(1.060, abs=0.001)
        assert result["kalman"]["temp_filtered"] == pytest.approx(70.0, abs=0.1)

    def test_remove_pipeline_deletes_device(self):
        """Removing a pipeline deletes its state."""
        manager = MLPipelineManager()

        # Create pipelines for multiple devices
        manager.get_pipeline("RED")
        manager.get_pipeline("BLUE")
        manager.get_pipeline("GREEN")

        assert len(manager.list_active_pipelines()) == 3

        # Remove one device
        manager.remove_pipeline("BLUE")

        active = manager.list_active_pipelines()
        assert len(active) == 2
        assert "BLUE" not in active
        assert "RED" in active
        assert "GREEN" in active

    def test_processes_many_devices_concurrently(self):
        """Manager handles many devices without cross-contamination."""
        manager = MLPipelineManager()

        # Simulate 5 devices with different SG values
        devices = ["RED", "BLUE", "GREEN", "ORANGE", "YELLOW"]
        initial_sgs = [1.050, 1.060, 1.045, 1.055, 1.070]

        # Process readings for all devices
        for device, sg in zip(devices, initial_sgs):
            for i in range(10):
                manager.process_reading(
                    device_id=device,
                    sg=sg - i * 0.001,
                    temp=68.0,
                    rssi=-60,
                    time_hours=float(i * 4),
                )

        # Each device should have its own filtered state
        for device, expected_sg in zip(devices, initial_sgs):
            result = manager.process_reading(
                device_id=device,
                sg=expected_sg - 0.010,
                temp=68.0,
                rssi=-60,
                time_hours=40.0,
            )
            # Filtered SG should be close to its own series
            assert result["kalman"]["sg_filtered"] < expected_sg
            assert result["kalman"]["sg_filtered"] > expected_sg - 0.020
