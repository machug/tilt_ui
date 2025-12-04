"""Anomaly detection for fermentation data.

Detects unusual patterns in gravity readings that may indicate:
- Stuck fermentation (SG not declining)
- Contamination (unusual SG increases)
- Sensor drift or calibration issues

Uses Isolation Forest for unsupervised anomaly detection combined with
domain-specific rules (SG rate thresholds).
"""

import numpy as np
from sklearn.ensemble import IsolationForest
from typing import Optional


class FermentationAnomalyDetector:
    """Detects anomalies in fermentation gravity readings.

    Combines unsupervised ML (Isolation Forest) with domain knowledge:
    - Isolation Forest finds unusual patterns in [sg, sg_rate, time_delta]
    - SG rate threshold catches stuck fermentation (rate near zero)
    - SG increase detection flags potential contamination

    The detector requires a minimum history before making predictions.
    """

    def __init__(
        self,
        contamination: float = 0.05,
        min_history: int = 20,
        sg_rate_threshold: float = 0.001,  # SG per hour
    ):
        """Initialize the anomaly detector.

        Args:
            contamination: Expected proportion of anomalies (0.0 to 0.5)
            min_history: Minimum readings required before scoring
            sg_rate_threshold: Minimum acceptable SG decline rate (SG/hour)
                              Below this = stuck fermentation
        """
        self.contamination = contamination
        self.min_history = min_history
        self.sg_rate_threshold = sg_rate_threshold

        # Isolation Forest model
        self.model = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=100,
        )

        # History buffers
        self.sg_history: list[float] = []
        self.time_history: list[float] = []  # hours since start
        self.is_fitted = False

    def check_reading(
        self,
        sg: float,
        time_hours: float,
    ) -> dict:
        """Check if a reading is anomalous.

        Args:
            sg: Specific gravity reading
            time_hours: Time in hours since fermentation start

        Returns:
            Dictionary with detection results:
            - anomaly_score: Anomaly score (lower = more anomalous), None if not fitted
            - is_anomaly: True if reading is anomalous
            - reason: Why it's anomalous (if applicable)
            - sg_rate: Estimated SG change rate (SG/hour)
        """
        # Add to history
        self.sg_history.append(sg)
        self.time_history.append(time_hours)

        # Need minimum history to make predictions
        if len(self.sg_history) < self.min_history:
            return {
                "anomaly_score": None,
                "is_anomaly": False,
                "reason": "insufficient_history",
                "sg_rate": None,
            }

        # Fit model on first opportunity
        if not self.is_fitted:
            self._fit_model()

        # Calculate features for this reading
        features = self._extract_features()

        # Get anomaly score from Isolation Forest
        # Score is in range [-1, 1], negative = anomaly
        score = self.model.score_samples([features])[0]

        # Calculate recent SG rate
        sg_rate = self._calculate_sg_rate()

        # Determine if anomalous and why
        is_anomaly = False
        reason = "normal"

        # Check for unusual SG increase (contamination)
        # First check for spike in last reading (not smoothed by window)
        if len(self.sg_history) >= 2:
            last_dt = self.time_history[-1] - self.time_history[-2]
            last_rate = ((self.sg_history[-1] - self.sg_history[-2]) / last_dt
                        if last_dt > 0 else 0)

            # Flag significant positive rate (> threshold)
            if last_rate > self.sg_rate_threshold:
                is_anomaly = True
                reason = "unusual_increase"

        # Also check window-averaged rate for sustained increases
        if not is_anomaly and sg_rate is not None and sg_rate > self.sg_rate_threshold * 3:
            is_anomaly = True
            reason = "unusual_increase"

        # Check for stuck fermentation (average SG rate near zero)
        # Must have enough data and the rate should be consistently near zero
        # Using abs(rate) catches both stuck and reverse fermentation
        elif (sg_rate is not None and
              abs(sg_rate) < self.sg_rate_threshold * 2 and  # Increased tolerance
              len(self.sg_history) >= self.min_history + 10):
            # Verify it's truly stuck by checking last 10 readings (excluding current)
            # Use [-2] to [-11] to avoid including the current reading
            recent_sg_change = abs(self.sg_history[-2] - self.sg_history[-11])
            if recent_sg_change < 0.002:  # Less than 0.002 SG change over 10 readings
                is_anomaly = True
                reason = "stuck_fermentation"

        # Isolation Forest: Disabled for now
        # Normal fermentation data is too homogeneous (smooth exponential decay)
        # Isolation Forest flags all readings as anomalous when trained on uniform data
        # Future: Consider training on diverse multi-batch data or using one-class SVM
        # elif score < -0.3:
        #     is_anomaly = True
        #     reason = "unusual_pattern"

        return {
            "anomaly_score": float(score),
            "is_anomaly": is_anomaly,
            "reason": reason,
            "sg_rate": sg_rate,
        }

    def _fit_model(self) -> None:
        """Fit the Isolation Forest on accumulated history."""
        # Extract features for all historical readings
        X = []
        for i in range(len(self.sg_history)):
            sg = self.sg_history[i]
            time = self.time_history[i]

            # Calculate SG rate using previous reading
            if i > 0:
                dt = time - self.time_history[i - 1]
                sg_rate = (sg - self.sg_history[i - 1]) / dt if dt > 0 else 0
            else:
                sg_rate = 0

            # Feature vector: [sg, sg_rate, time_delta]
            X.append([sg, sg_rate, time])

        # Fit the model
        self.model.fit(X)
        self.is_fitted = True

    def _extract_features(self) -> list[float]:
        """Extract features for the most recent reading."""
        sg = self.sg_history[-1]
        time = self.time_history[-1]

        # Calculate SG rate using previous reading
        if len(self.sg_history) > 1:
            dt = time - self.time_history[-2]
            sg_rate = (sg - self.sg_history[-2]) / dt if dt > 0 else 0
        else:
            sg_rate = 0

        return [sg, sg_rate, time]

    def _calculate_sg_rate(self, window: int = 5) -> Optional[float]:
        """Calculate recent SG change rate using linear regression.

        Args:
            window: Number of recent readings to use (default: 5)

        Returns:
            SG change rate in SG per hour, or None if insufficient data
        """
        if len(self.sg_history) < 2:
            return None

        # Use last N readings
        n = min(window, len(self.sg_history))
        times = np.array(self.time_history[-n:])
        sgs = np.array(self.sg_history[-n:])

        # Linear regression: sg = slope * time + intercept
        if len(times) < 2:
            return None

        # Handle constant time (dt = 0)
        dt = times[-1] - times[0]
        if dt == 0:
            return 0.0

        # Simple least squares slope
        slope = np.polyfit(times, sgs, deg=1)[0]
        return float(slope)

    def reset(self) -> None:
        """Reset detector state for a new batch."""
        self.sg_history = []
        self.time_history = []
        self.is_fitted = False
        self.model = IsolationForest(
            contamination=self.contamination,
            random_state=42,
            n_estimators=100,
        )
