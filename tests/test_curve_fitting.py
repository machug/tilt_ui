"""Tests for fermentation curve fitting and predictions."""

import numpy as np
import pytest
from backend.ml.predictions.curve_fitter import FermentationCurveFitter


class TestFermentationCurveFitter:
    """Tests for the fermentation curve fitter."""

    def test_initialization(self):
        """Fitter initializes with default parameters."""
        fitter = FermentationCurveFitter()

        assert fitter.min_readings == 10
        assert fitter.completion_threshold == 0.002

    def test_needs_minimum_readings(self):
        """Fitter requires minimum readings before fitting."""
        fitter = FermentationCurveFitter(min_readings=10)

        # Try to fit with insufficient data
        times = [0, 4, 8]
        sgs = [1.050, 1.049, 1.048]

        result = fitter.fit(times, sgs)

        assert result["fitted"] is False
        assert result["reason"] == "insufficient_data"
        assert result["predicted_fg"] is None

    def test_fits_exponential_decay(self, fermentation_data):
        """Fitter fits exponential decay curve to fermentation data."""
        fitter = FermentationCurveFitter(min_readings=10)

        result = fitter.fit(fermentation_data["hours"], fermentation_data["sg"])

        # Should successfully fit
        assert result["fitted"] is True
        assert result["model_type"] == "exponential"

        # Parameters should be close to ground truth
        # Ground truth: OG=1.055, FG=1.012, k=0.02
        assert result["predicted_og"] == pytest.approx(fermentation_data["og"], abs=0.003)
        assert result["predicted_fg"] == pytest.approx(fermentation_data["fg"], abs=0.003)
        assert result["decay_rate"] is not None
        assert result["r_squared"] > 0.95  # Good fit

    def test_predicts_completion_time(self, fermentation_data):
        """Fitter estimates when fermentation will complete."""
        fitter = FermentationCurveFitter(min_readings=10, completion_threshold=0.002)

        # Fit on first 50% of data
        midpoint = len(fermentation_data["hours"]) // 2
        result = fitter.fit(
            fermentation_data["hours"][:midpoint],
            fermentation_data["sg"][:midpoint]
        )

        assert result["fitted"] is True
        assert result["hours_to_completion"] is not None
        assert result["hours_to_completion"] > 0  # Should predict future completion

        # Predicted completion time should be reasonable
        # With k=0.02, ~75% completion takes about 70 hours
        assert result["hours_to_completion"] < 200

    def test_detects_completed_fermentation(self):
        """Fitter recognizes when fermentation has already completed."""
        fitter = FermentationCurveFitter(completion_threshold=0.002)

        # Simulate fermentation that has reached near-terminal gravity
        # Use exponential decay with very slow rate near the end
        og = 1.055
        fg = 1.012
        k = 0.04  # Faster decay
        times = [float(i * 4) for i in range(20)]  # 80 hours total
        sgs = [fg + (og - fg) * np.exp(-k * t) for t in times]

        result = fitter.fit(times, sgs)

        assert result["fitted"] is True
        # After 80 hours with k=0.04, rate should be very low
        # hours_to_completion should be small (< 10 hours) or zero
        assert result["hours_to_completion"] < 10

    def test_handles_stuck_fermentation(self):
        """Fitter handles stuck fermentation gracefully."""
        fitter = FermentationCurveFitter(min_readings=10)

        # Simulate stuck fermentation (stops declining early)
        times = [float(i * 4) for i in range(15)]
        sgs = [1.050 - i * 0.001 for i in range(10)] + [1.040] * 5

        result = fitter.fit(times, sgs)

        # Should still fit but predict FG near stuck point
        # Exponential fit may smooth slightly below flat readings
        assert result["fitted"] is True
        assert result["predicted_fg"] >= 1.035  # Within reasonable range of stuck point
        assert result["predicted_fg"] <= 1.042  # Not too high

    def test_returns_predictions_at_intervals(self, fermentation_data):
        """Fitter can predict SG at future time points."""
        fitter = FermentationCurveFitter(min_readings=10)

        # Fit on first half
        midpoint = len(fermentation_data["hours"]) // 2
        result = fitter.fit(
            fermentation_data["hours"][:midpoint],
            fermentation_data["sg"][:midpoint]
        )

        # Get predictions for next 48 hours
        predictions = fitter.predict([24, 48, 72])

        assert len(predictions) == 3
        assert all(1.000 < sg < 1.100 for sg in predictions)
        # Predictions should decline over time
        assert predictions[0] > predictions[1] > predictions[2]
