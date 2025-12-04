"""Fermentation curve fitting for predictions.

Fits exponential decay models to fermentation data to predict:
- Final gravity (FG)
- Time to completion
- Future SG values

Uses scipy's curve_fit with exponential decay model:
SG(t) = FG + (OG - FG) * exp(-k * t)

Where:
- OG: Original gravity (initial SG)
- FG: Final gravity (terminal SG)
- k: Decay rate constant
- t: Time in hours
"""

import numpy as np
from scipy.optimize import curve_fit
from typing import Optional


class FermentationCurveFitter:
    """Fits exponential decay curves to fermentation gravity data.

    The fitter uses non-linear least squares to fit an exponential decay
    model to the SG readings over time. This model is commonly used for
    fermentation kinetics.

    The model: SG(t) = FG + (OG - FG) * exp(-k * t)

    Predictions can be used for:
    - Estimating final gravity (FG)
    - Predicting completion time
    - Forecasting future SG values
    """

    def __init__(
        self,
        min_readings: int = 10,
        completion_threshold: float = 0.002,  # SG per day
    ):
        """Initialize the curve fitter.

        Args:
            min_readings: Minimum readings required to fit curve
            completion_threshold: Daily SG change rate considered "complete"
        """
        self.min_readings = min_readings
        self.completion_threshold = completion_threshold

        # Fitted parameters (None until fit() is called)
        self.og: Optional[float] = None  # Original gravity
        self.fg: Optional[float] = None  # Final gravity
        self.k: Optional[float] = None   # Decay rate constant
        self.r_squared: Optional[float] = None  # Fit quality

    def fit(self, times: list[float], sgs: list[float]) -> dict:
        """Fit exponential decay curve to fermentation data.

        Args:
            times: Time points in hours since fermentation start
            sgs: Specific gravity readings

        Returns:
            Dictionary with fit results:
            - fitted: True if fit successful
            - model_type: Type of model ("exponential" or None)
            - predicted_og: Fitted original gravity
            - predicted_fg: Fitted final gravity
            - decay_rate: Fitted decay constant k
            - r_squared: R² goodness of fit
            - hours_to_completion: Estimated hours until complete
            - reason: If not fitted, reason why
        """
        # Check minimum readings
        if len(times) < self.min_readings:
            return {
                "fitted": False,
                "model_type": None,
                "predicted_og": None,
                "predicted_fg": None,
                "decay_rate": None,
                "r_squared": None,
                "hours_to_completion": None,
                "reason": "insufficient_data",
            }

        # Convert to numpy arrays
        times_arr = np.array(times, dtype=float)
        sgs_arr = np.array(sgs, dtype=float)

        # Exponential decay model: SG(t) = fg + (og - fg) * exp(-k * t)
        def exp_decay(t, og, fg, k):
            return fg + (og - fg) * np.exp(-k * t)

        # Initial parameter guesses
        og_guess = sgs_arr[0]  # First reading
        fg_guess = sgs_arr[-1]  # Last reading
        k_guess = 0.02  # Typical fermentation rate

        try:
            # Fit the curve
            popt, pcov = curve_fit(
                exp_decay,
                times_arr,
                sgs_arr,
                p0=[og_guess, fg_guess, k_guess],
                bounds=([1.000, 0.990, 0.001], [1.200, 1.100, 0.5]),  # Reasonable bounds
                maxfev=10000
            )

            og_fit, fg_fit, k_fit = popt

            # Calculate R² (coefficient of determination)
            residuals = sgs_arr - exp_decay(times_arr, *popt)
            ss_res = np.sum(residuals ** 2)
            ss_tot = np.sum((sgs_arr - np.mean(sgs_arr)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

            # Store fitted parameters
            self.og = float(og_fit)
            self.fg = float(fg_fit)
            self.k = float(k_fit)
            self.r_squared = float(r_squared)

            # Calculate hours to completion
            hours_to_completion = self._calculate_completion_time(times_arr[-1], sgs_arr[-1])

            return {
                "fitted": True,
                "model_type": "exponential",
                "predicted_og": self.og,
                "predicted_fg": self.fg,
                "decay_rate": self.k,
                "r_squared": self.r_squared,
                "hours_to_completion": hours_to_completion,
                "reason": None,
            }

        except (RuntimeError, ValueError) as e:
            # Fit failed
            return {
                "fitted": False,
                "model_type": None,
                "predicted_og": None,
                "predicted_fg": None,
                "decay_rate": None,
                "r_squared": None,
                "hours_to_completion": None,
                "reason": f"fit_failed: {str(e)}",
            }

    def _calculate_completion_time(
        self,
        current_time: float,
        current_sg: float
    ) -> float:
        """Calculate hours until fermentation completes.

        Args:
            current_time: Current time in hours
            current_sg: Current specific gravity

        Returns:
            Hours until completion (0 if already complete)
        """
        if self.fg is None or self.k is None or self.og is None:
            return 0

        # Check if current SG is already at or below predicted FG
        # Allow small tolerance for measurement noise
        if current_sg <= self.fg + 0.001:
            return 0  # Already at FG

        # Check if already complete (rate below threshold)
        # Completion threshold is in SG/day, convert to SG/hour
        threshold_hourly = self.completion_threshold / 24

        # Current rate: dSG/dt = -(OG - FG) * k * exp(-k * t)
        current_rate = abs((self.og - self.fg) * self.k * np.exp(-self.k * current_time))

        if current_rate < threshold_hourly:
            return 0  # Already complete

        # Solve for time when rate equals threshold
        # rate_threshold = (OG - FG) * k * exp(-k * t_complete)
        # exp(-k * t_complete) = rate_threshold / ((OG - FG) * k)
        # -k * t_complete = ln(rate_threshold / ((OG - FG) * k))
        # t_complete = -ln(rate_threshold / ((OG - FG) * k)) / k

        try:
            t_complete = -np.log(threshold_hourly / ((self.og - self.fg) * self.k)) / self.k
            hours_remaining = t_complete - current_time
            return float(max(0, hours_remaining))
        except (ValueError, ZeroDivisionError):
            return 0

    def predict(self, future_times: list[float]) -> list[float]:
        """Predict SG at future time points.

        Args:
            future_times: List of time points (hours) to predict SG

        Returns:
            List of predicted SG values
        """
        if self.og is None or self.fg is None or self.k is None:
            msg = "Must call fit() before predict()"
            raise ValueError(msg)

        predictions = []
        for t in future_times:
            sg = self.fg + (self.og - self.fg) * np.exp(-self.k * t)
            predictions.append(float(sg))

        return predictions
