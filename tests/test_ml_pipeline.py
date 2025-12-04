"""Tests for ML pipeline orchestrator."""

import pytest
from backend.ml.pipeline import MLPipeline


class TestMLPipeline:
    """Tests for the ML pipeline orchestrator."""

    def test_initialization(self):
        """Pipeline initializes with enabled components."""
        pipeline = MLPipeline()

        # Components enabled by default
        assert pipeline.kalman_filter is not None
        assert pipeline.anomaly_detector is not None
        assert pipeline.curve_fitter is not None

        # MPC disabled by default (requires Home Assistant)
        assert pipeline.mpc_controller is None

    def test_processes_single_reading(self):
        """Pipeline processes a reading through all stages."""
        pipeline = MLPipeline()

        result = pipeline.process_reading(
            sg=1.050,
            temp=68.0,
            rssi=-60,
            time_hours=0,
            ambient_temp=65.0,
        )

        # Should have results from each stage
        assert "kalman" in result
        assert "anomaly" in result
        assert result["kalman"]["sg_filtered"] is not None
        assert result["anomaly"]["is_anomaly"] in [True, False]

    def test_builds_history_for_predictions(self):
        """Pipeline accumulates history for curve fitting."""
        pipeline = MLPipeline()

        # Process several readings
        for i in range(15):
            time_hours = float(i * 4)
            sg = 1.050 - i * 0.001  # Declining SG
            pipeline.process_reading(
                sg=sg,
                temp=68.0,
                rssi=-60,
                time_hours=time_hours,
                ambient_temp=65.0,
            )

        # After enough readings, should have predictions
        result = pipeline.process_reading(
            sg=1.035,
            temp=68.0,
            rssi=-60,
            time_hours=60.0,
            ambient_temp=65.0,
        )

        assert "predictions" in result
        if result["predictions"]["fitted"]:
            assert result["predictions"]["predicted_fg"] is not None

    def test_learns_thermal_model_for_mpc(self):
        """Pipeline learns thermal model for MPC control."""
        from backend.ml.config import MLConfig

        # Enable MPC for this test
        config = MLConfig(enable_mpc=True)
        pipeline = MLPipeline(config=config)

        # Process readings with temperature and heater state
        for i in range(10):
            time_hours = float(i)
            temp = 68.0 + i * 0.5  # Warming
            pipeline.process_reading(
                sg=1.050,
                temp=temp,
                rssi=-60,
                time_hours=time_hours,
                ambient_temp=65.0,
                heater_on=True,  # Heater causing warming
            )

        # Should be able to compute MPC action
        result = pipeline.process_reading(
            sg=1.050,
            temp=70.0,
            rssi=-60,
            time_hours=10.0,
            ambient_temp=65.0,
            target_temp=72.0,
        )

        assert "mpc" in result
        if result["mpc"]["heater_on"] is not None:
            # MPC has learned model
            assert result["mpc"]["reason"] is not None

    def test_resets_for_new_batch(self):
        """Pipeline can reset state for new fermentation batch."""
        pipeline = MLPipeline()

        # Process some readings
        for i in range(5):
            pipeline.process_reading(
                sg=1.050 - i * 0.001,
                temp=68.0,
                rssi=-60,
                time_hours=float(i * 4),
                ambient_temp=65.0,
            )

        # Reset for new batch
        pipeline.reset(initial_sg=1.060, initial_temp=70.0)

        # Should have reset Kalman filter and detectors
        result = pipeline.process_reading(
            sg=1.060,
            temp=70.0,
            rssi=-60,
            time_hours=0,
            ambient_temp=65.0,
        )

        # Kalman should be at new initial state
        assert result["kalman"]["sg_filtered"] == pytest.approx(1.060, abs=0.001)
        assert result["kalman"]["temp_filtered"] == pytest.approx(70.0, abs=0.1)

    def test_feature_flags_control_components(self):
        """Pipeline respects feature flag configuration."""
        from backend.ml.config import MLConfig

        # Disable predictions
        config = MLConfig(enable_predictions=False)
        pipeline = MLPipeline(config=config)

        result = pipeline.process_reading(
            sg=1.050,
            temp=68.0,
            rssi=-60,
            time_hours=0,
            ambient_temp=65.0,
        )

        # Predictions should be skipped
        assert "predictions" not in result or result["predictions"] is None

    def test_returns_comprehensive_results(self):
        """Pipeline returns results from all enabled components."""
        pipeline = MLPipeline()

        # Build up some history
        for i in range(25):
            pipeline.process_reading(
                sg=1.050 - i * 0.001,
                temp=68.0 + i * 0.1,
                rssi=-60,
                time_hours=float(i * 4),
                ambient_temp=65.0,
                heater_on=i % 2 == 0,
            )

        result = pipeline.process_reading(
            sg=1.025,
            temp=70.0,
            rssi=-60,
            time_hours=100.0,
            ambient_temp=65.0,
            target_temp=70.0,
        )

        # Should have all component results
        assert "kalman" in result
        assert "anomaly" in result
        assert "predictions" in result
        assert "mpc" in result

        # Verify structure
        assert "sg_filtered" in result["kalman"]
        assert "is_anomaly" in result["anomaly"]
