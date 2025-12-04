"""Tests for fermentation anomaly detection."""

import pytest
from backend.ml.anomaly.detector import FermentationAnomalyDetector


class TestFermentationAnomalyDetector:
    """Tests for the fermentation anomaly detector."""

    def test_initialization(self):
        """Detector initializes with default parameters."""
        detector = FermentationAnomalyDetector()

        assert detector.contamination == 0.05
        assert detector.min_history == 20
        assert detector.sg_rate_threshold == 0.001

    def test_needs_minimum_history(self, fermentation_data):
        """Detector requires minimum readings before scoring."""
        detector = FermentationAnomalyDetector(min_history=20)

        # Feed first 10 readings (below minimum)
        readings = list(zip(fermentation_data["hours"][:10],
                           fermentation_data["sg"][:10]))

        for hour, sg in readings:
            result = detector.check_reading(sg, hour)

        # Should not have enough history yet
        assert result["anomaly_score"] is None
        assert result["is_anomaly"] is False
        assert result["reason"] == "insufficient_history"

    def test_detects_stuck_fermentation(self):
        """Detector identifies stuck fermentation (flat SG curve)."""
        detector = FermentationAnomalyDetector(
            min_history=10,
            sg_rate_threshold=0.001  # 0.001 SG/hour = 0.024 SG/day
        )

        # Simulate normal fermentation
        for hour in range(10):
            sg = 1.050 - hour * 0.001  # Declining 0.001/hour
            detector.check_reading(sg, hour)

        # Then simulate stuck fermentation (10 flat readings)
        stuck_results = []
        for hour in range(10, 20):
            sg = 1.040  # Stuck at 1.040
            result = detector.check_reading(sg, hour)
            stuck_results.append(result)

        # At least one should be flagged as anomaly
        assert any(r["is_anomaly"] for r in stuck_results)
        assert any(r["reason"] == "stuck_fermentation" for r in stuck_results)

    def test_detects_unusual_sg_spike(self, fermentation_data):
        """Detector identifies unusual SG increase (contamination signal)."""
        detector = FermentationAnomalyDetector(min_history=20)

        # Feed normal data
        for hour, sg in zip(fermentation_data["hours"][:25],
                           fermentation_data["sg"][:25]):
            detector.check_reading(sg, hour)

        # Inject anomalous spike (SG increases instead of decreases)
        last_sg = fermentation_data["sg"][24]
        anomaly_sg = last_sg + 0.005  # Significant increase
        result = detector.check_reading(anomaly_sg, fermentation_data["hours"][25])

        assert result["is_anomaly"]
        assert result["reason"] in ["unusual_pattern", "unusual_increase"]

    def test_tolerates_normal_noise(self, fermentation_data):
        """Detector doesn't flag normal fermentation with realistic noise."""
        detector = FermentationAnomalyDetector(min_history=20)

        anomalies = []
        for hour, sg in zip(fermentation_data["hours"],
                           fermentation_data["sg"]):
            result = detector.check_reading(sg, hour)
            if result["is_anomaly"]:
                anomalies.append(result)

        # Should have very few false positives (< 10%)
        total_checks = len(fermentation_data["hours"]) - detector.min_history
        false_positive_rate = len(anomalies) / total_checks if total_checks > 0 else 0
        assert false_positive_rate < 0.10

    def test_reset_clears_history(self, fermentation_data):
        """Reset clears detector history for new batch."""
        detector = FermentationAnomalyDetector(min_history=10)

        # Feed some data
        for hour, sg in zip(fermentation_data["hours"][:15],
                           fermentation_data["sg"][:15]):
            detector.check_reading(sg, hour)

        # Reset
        detector.reset()

        # Should need history again
        result = detector.check_reading(1.050, 0)
        assert result["anomaly_score"] is None
        assert result["reason"] == "insufficient_history"
