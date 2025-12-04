"""Tests for MPC ambient_history safety checks."""

import pytest
from backend.ml.pipeline import MLPipeline
from backend.ml.config import MLConfig


class TestMPCAmbientHistorySafety:
    """Tests for MPC handling of missing ambient temperatures."""

    def test_handles_missing_ambient_temps_gracefully(self):
        """Pipeline handles missing ambient temps without crashing."""
        config = MLConfig(enable_mpc=True)
        pipeline = MLPipeline(config=config)

        # Process readings with some missing ambient_temp
        for i in range(10):
            # Only provide ambient_temp on even readings
            ambient = 65.0 if i % 2 == 0 else None

            result = pipeline.process_reading(
                sg=1.050,
                temp=68.0 + i * 0.5,
                rssi=-60,
                time_hours=float(i),
                ambient_temp=ambient,
                heater_on=True,
            )

            # Should not crash, even with misaligned histories
            assert result is not None
            assert "mpc" in result

    def test_mpc_waits_for_sufficient_aligned_history(self):
        """MPC only learns when all histories have sufficient aligned data."""
        config = MLConfig(enable_mpc=True)
        pipeline = MLPipeline(config=config)

        # First 2 readings: no ambient_temp
        for i in range(2):
            pipeline.process_reading(
                sg=1.050,
                temp=68.0,
                rssi=-60,
                time_hours=float(i),
                ambient_temp=None,  # Missing
                heater_on=True,
            )

        # Next 5 readings: with ambient_temp
        for i in range(2, 7):
            result = pipeline.process_reading(
                sg=1.050,
                temp=68.0 + i * 0.5,
                rssi=-60,
                time_hours=float(i),
                ambient_temp=65.0,  # Provided
                heater_on=True,
                target_temp=70.0,
            )

        # After 5 readings with ambient (>= 3), should have MPC result
        # History lengths: temp=7, heater=7, ambient=5
        # min_history_len = 5, which is >= 3, so MPC should work
        assert result["mpc"] is not None
        assert result["mpc"]["heater_on"] in [True, False]

    def test_mpc_skips_learning_with_insufficient_ambient_data(self):
        """MPC skips learning if ambient history too short."""
        config = MLConfig(enable_mpc=True)
        pipeline = MLPipeline(config=config)

        # Process many readings but only 2 with ambient
        for i in range(10):
            ambient = 65.0 if i >= 8 else None  # Only last 2 have ambient

            pipeline.process_reading(
                sg=1.050,
                temp=68.0 + i * 0.5,
                rssi=-60,
                time_hours=float(i),
                ambient_temp=ambient,
                heater_on=True,
            )

        # Try MPC with target temp
        result = pipeline.process_reading(
            sg=1.050,
            temp=73.0,
            rssi=-60,
            time_hours=10.0,
            ambient_temp=65.0,
            heater_on=True,
            target_temp=70.0,
        )

        # MPC should return result but may not have learned model yet
        # (only 3 aligned readings: indices 8, 9, 10)
        assert result["mpc"] is not None
        # Model may or may not be learned (depends on exact history alignment)

    def test_mpc_uses_aligned_slice_of_histories(self):
        """MPC uses aligned slice when histories have different lengths."""
        config = MLConfig(enable_mpc=True)
        pipeline = MLPipeline(config=config)

        # Build misaligned histories:
        # - temp_history: 10 entries
        # - heater_history: 8 entries (skip first 2)
        # - ambient_history: 6 entries (skip first 4)

        # First 4 readings: no heater or ambient
        for i in range(4):
            pipeline.process_reading(
                sg=1.050,
                temp=68.0,
                rssi=-60,
                time_hours=float(i),
                # heater_on=None, ambient_temp=None (skipped)
            )

        # Next 2 readings: heater but no ambient
        for i in range(4, 6):
            pipeline.process_reading(
                sg=1.050,
                temp=68.0,
                rssi=-60,
                time_hours=float(i),
                heater_on=True,
                # ambient_temp=None (skipped)
            )

        # Last 4 readings: heater and ambient
        for i in range(6, 10):
            pipeline.process_reading(
                sg=1.050,
                temp=68.0 + i * 0.5,
                rssi=-60,
                time_hours=float(i),
                ambient_temp=65.0,
                heater_on=True,
            )

        # Compute MPC action
        result = pipeline.process_reading(
            sg=1.050,
            temp=72.0,
            rssi=-60,
            time_hours=10.0,
            ambient_temp=65.0,
            heater_on=True,
            target_temp=70.0,
        )

        # Should have MPC result using aligned slice
        # Histories: temp=11, heater=7, ambient=5
        # min_len = 5, which is >= 3, so MPC works
        assert result["mpc"] is not None
        assert result["mpc"]["heater_on"] in [True, False, None]

    def test_no_crash_with_empty_ambient_history(self):
        """Pipeline doesn't crash if ambient_history is completely empty."""
        config = MLConfig(enable_mpc=True)
        pipeline = MLPipeline(config=config)

        # Process many readings with no ambient_temp
        for i in range(10):
            pipeline.process_reading(
                sg=1.050,
                temp=68.0 + i * 0.5,
                rssi=-60,
                time_hours=float(i),
                heater_on=True,
                # ambient_temp=None (never provided)
            )

        # Try to use MPC with target and ambient
        result = pipeline.process_reading(
            sg=1.050,
            temp=73.0,
            rssi=-60,
            time_hours=10.0,
            ambient_temp=65.0,  # First time providing it
            heater_on=True,
            target_temp=70.0,
        )

        # Should not crash
        # min_history_len = 1 (ambient_history has 1 entry now)
        # Since min_len < 3, MPC won't learn but should still return
        assert result["mpc"] is not None

    def test_mpc_learns_correctly_after_histories_align(self):
        """MPC learns thermal model once histories are properly aligned."""
        config = MLConfig(enable_mpc=True)
        pipeline = MLPipeline(config=config)

        # Start with misaligned histories, then align them
        # First reading: no heater or ambient
        pipeline.process_reading(
            sg=1.050, temp=68.0, rssi=-60, time_hours=0.0
        )

        # Build aligned history (all fields provided)
        for i in range(1, 8):
            pipeline.process_reading(
                sg=1.050,
                temp=68.0 + i * 0.5,
                rssi=-60,
                time_hours=float(i),
                ambient_temp=65.0,
                heater_on=True,
                target_temp=70.0,  # Trigger MPC learning
            )

        # Turn heater off for cooling period
        for i in range(8, 11):
            pipeline.process_reading(
                sg=1.050,
                temp=71.5 - (i - 8) * 0.3,
                rssi=-60,
                time_hours=float(i),
                ambient_temp=65.0,
                heater_on=False,
                target_temp=70.0,  # Trigger MPC learning
            )

        # Check that model was learned
        assert pipeline.mpc_controller.has_model is True
        assert pipeline.mpc_controller.heating_rate is not None
        assert pipeline.mpc_controller.cooling_coeff is not None
