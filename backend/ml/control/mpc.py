"""Model Predictive Control for fermentation temperature regulation.

Uses a learned thermal model to predict temperature trajectory and prevent
overshoot by computing optimal heater/cooler ON/OFF actions over a receding horizon.

The thermal model accounts for:
- Heater power (temperature rise when ON)
- Active cooling power (temperature drop when cooler ON)
- Natural ambient exchange toward ambient temperature
- Thermal inertia (time lag between heater/cooler state and temperature change)
- Mutual exclusion (heater and cooler never run simultaneously)

MPC solves an optimization problem at each time step:
1. Predict temperature over next N hours for different heater/cooler sequences
2. Choose sequence that minimizes distance from target without overshoot
3. Apply first action from optimal sequence
4. Repeat at next time step (receding horizon)

Supports both heater-only mode (backward compatible) and dual-mode operation
with independent heater and cooler control.
"""

import logging
import numpy as np
from typing import Optional


class MPCTemperatureController:
    """Model Predictive Controller for fermentation temperature.

    The controller learns a simple thermal model from historical data:
    - Heater ON: dT/dt = heating_rate - ambient_coeff * (T - T_ambient)
    - Heater OFF: dT/dt = -ambient_coeff * (T - T_ambient)

    At each control step, it predicts temperature trajectories for all
    possible heater sequences over the horizon and selects the sequence
    that best achieves the target without overshoot.
    """

    def __init__(
        self,
        horizon_hours: float = 4.0,
        max_temp_rate: float = 0.56,  # Max °C/hour change (~1°F/hour equivalent)
        dt_hours: float = 0.25,  # 15-minute time steps
    ):
        """Initialize the MPC controller.

        Args:
            horizon_hours: Prediction horizon in hours
            max_temp_rate: Maximum allowed temperature change rate (°C/hour)
            dt_hours: Time step for prediction (hours)
        """
        self.horizon_hours = horizon_hours
        self.max_temp_rate = max_temp_rate
        self.dt_hours = dt_hours

        # Thermal model parameters (learned from data)
        self.heating_rate: Optional[float] = None      # °C/hour when heater ON
        self.cooling_rate: Optional[float] = None      # °C/hour when cooler ON (active cooling)
        self.ambient_coeff: Optional[float] = None     # Natural cooling coefficient
        self.has_model = False
        self.has_cooling = False  # True if cooling model available

    def learn_thermal_model(
        self,
        temp_history: list[float],
        time_history: list[float],
        heater_history: list[bool],
        ambient_history: list[float],
        cooler_history: Optional[list[bool]] = None,
    ) -> dict:
        """Learn thermal model parameters from historical data.

        Args:
            temp_history: Temperature readings (°C)
            time_history: Time stamps (hours)
            heater_history: Heater state (True=ON, False=OFF)
            ambient_history: Ambient temperature (°C)
            cooler_history: Cooler state (True=ON, False=OFF), optional

        Returns:
            Dictionary with learned parameters and fit quality
        """
        # Validate all histories have same length
        histories = [temp_history, time_history, heater_history, ambient_history]
        if cooler_history is not None:
            histories.append(cooler_history)
        min_len = min(len(h) for h in histories)

        if min_len < 3:
            return {
                "success": False,
                "reason": "insufficient_data",
                "heating_rate": None,
                "cooling_rate": None,
                "ambient_coeff": None,
                "has_cooling": False,
            }

        # Slice all histories to same length to prevent IndexError
        temp_history = temp_history[-min_len:]
        time_history = time_history[-min_len:]
        heater_history = heater_history[-min_len:]
        ambient_history = ambient_history[-min_len:]
        if cooler_history is not None:
            cooler_history = cooler_history[-min_len:]

        # Calculate temperature rates (dT/dt)
        idle_rates = []      # Both heater and cooler OFF
        heating_rates = []   # Heater ON, cooler OFF
        cooling_rates = []   # Cooler ON, heater OFF

        for i in range(1, len(temp_history)):
            dt = time_history[i] - time_history[i - 1]
            if dt <= 0:
                continue

            dtemp = temp_history[i] - temp_history[i - 1]
            rate = dtemp / dt  # °C/hour

            # Temperature difference from ambient
            temp_above_ambient = temp_history[i - 1] - ambient_history[i - 1]

            heater_on = heater_history[i - 1]
            cooler_on = cooler_history[i - 1] if cooler_history else False

            # Validate mutual exclusion
            if heater_on and cooler_on:
                logging.warning(f"Point {i}: Both heater and cooler ON (mutual exclusion violation)")
                continue  # Skip this point

            # Categorize by regime
            if heater_on:
                # Heater ON: rate = heating_rate - ambient_coeff * (T - T_ambient)
                heating_rates.append((rate, temp_above_ambient))
            elif cooler_on:
                # Cooler ON: rate = -cooling_rate - ambient_coeff * (T - T_ambient)
                cooling_rates.append((rate, temp_above_ambient))
            else:
                # Both OFF: rate = -ambient_coeff * (T - T_ambient)
                idle_rates.append((rate, temp_above_ambient))

        # Estimate ambient coefficient from idle periods (both OFF)
        # Fallback to cooling periods if no idle data
        coeff_sources = idle_rates if idle_rates else cooling_rates

        if coeff_sources:
            # rate = -ambient_coeff * temp_above_ambient
            # ambient_coeff = -rate / temp_above_ambient
            coeffs = []
            for rate, temp_diff in coeff_sources:
                if abs(temp_diff) > 0.1:  # Avoid division by near-zero
                    coeff = -rate / temp_diff
                    if coeff > 0:  # Sanity check
                        coeffs.append(coeff)

            self.ambient_coeff = float(np.median(coeffs)) if coeffs else 0.1
        else:
            self.ambient_coeff = 0.1  # Default fallback

        # Estimate heating rate from heating periods
        if heating_rates:
            # rate = heating_rate - ambient_coeff * temp_above_ambient
            # heating_rate = rate + ambient_coeff * temp_above_ambient
            net_heating_rates = []
            for rate, temp_diff in heating_rates:
                net_rate = rate + self.ambient_coeff * temp_diff
                net_heating_rates.append(net_rate)

            self.heating_rate = float(np.median(net_heating_rates))
        else:
            self.heating_rate = 1.1  # Default fallback (1.1°C/hour, ~2°F/hour equivalent)

        # Learn cooling rate from cooling periods (if cooler_history provided)
        if cooler_history and cooling_rates:
            # rate = -cooling_rate - ambient_coeff * temp_above_ambient
            # cooling_rate = -rate - ambient_coeff * temp_above_ambient
            net_cooling_rates = []
            for rate, temp_diff in cooling_rates:
                net_rate = -rate - self.ambient_coeff * temp_diff
                if net_rate > 0:  # Sanity check (cooling_rate should be positive)
                    net_cooling_rates.append(net_rate)

            if net_cooling_rates:
                self.cooling_rate = float(np.median(net_cooling_rates))
                self.has_cooling = True
            else:
                self.cooling_rate = None
                self.has_cooling = False
        else:
            self.cooling_rate = None
            self.has_cooling = False

        self.has_model = True

        return {
            "success": True,
            "reason": None,
            "heating_rate": self.heating_rate,
            "cooling_rate": self.cooling_rate,
            "ambient_coeff": self.ambient_coeff,
            "has_cooling": self.has_cooling,
        }

    def compute_action(
        self,
        current_temp: float,
        target_temp: float,
        ambient_temp: float,
        heater_currently_on: Optional[bool] = None,
        cooler_currently_on: Optional[bool] = None,
    ) -> dict:
        """Compute optimal heater/cooler action using MPC.

        Args:
            current_temp: Current fermentation temperature (°C)
            target_temp: Target temperature (°C)
            ambient_temp: Ambient/room temperature (°C)
            heater_currently_on: Current heater state (for continuity preference)
            cooler_currently_on: Current cooler state (for continuity preference)

        Returns:
            Dictionary with control decision:
            - heater_on: True/False/None (None if no model)
            - cooler_on: True/False/None (None if no model or no cooling)
            - reason: Explanation for decision
            - predicted_temp: Predicted temperature at end of horizon
            - cost: Optimization cost (lower is better)
        """
        if not self.has_model:
            return {
                "heater_on": None,
                "cooler_on": None,
                "reason": "no_model",
                "predicted_temp": None,
                "cost": None,
            }

        # If above target and no cooling available, turn off heater
        if current_temp >= target_temp and not self.has_cooling:
            return {
                "heater_on": False,
                "cooler_on": False,
                "reason": "above_target_no_cooling",
                "predicted_temp": current_temp,
                "cost": 0,
            }

        # Compute number of time steps in horizon
        n_steps = int(self.horizon_hours / self.dt_hours)

        # Build list of actions to evaluate
        actions_to_evaluate = []

        # Action 1: Heater ON, Cooler OFF
        actions_to_evaluate.append({
            "heater_on": True,
            "cooler_on": False,
            "heater_seq": [True] * n_steps,
            "cooler_seq": [False] * n_steps,
        })

        # Action 2: Both OFF
        actions_to_evaluate.append({
            "heater_on": False,
            "cooler_on": False,
            "heater_seq": [False] * n_steps,
            "cooler_seq": [False] * n_steps,
        })

        # Action 3: Cooler ON, Heater OFF (only if cooling available)
        if self.has_cooling:
            actions_to_evaluate.append({
                "heater_on": False,
                "cooler_on": True,
                "heater_seq": [False] * n_steps,
                "cooler_seq": [True] * n_steps,
            })

        # Evaluate all actions
        best_action = None
        best_cost = float("inf")
        best_trajectory = None

        for action in actions_to_evaluate:
            # Predict trajectory
            trajectory = self.predict_trajectory(
                current_temp,
                action["heater_seq"],
                action["cooler_seq"],
                ambient_temp
            )

            # Calculate cost: penalize distance from target and overshoot
            cost = 0
            for temp in trajectory:
                error = temp - target_temp
                if error > 0:
                    # Overshoot: heavily penalize
                    cost += error ** 2 * 10
                else:
                    # Below target: normal penalty
                    cost += error ** 2

            # Small penalty for switching state (reduce cycling)
            if heater_currently_on is not None and action["heater_on"] != heater_currently_on:
                cost += 0.1
            if cooler_currently_on is not None and action["cooler_on"] != cooler_currently_on:
                cost += 0.1

            if cost < best_cost:
                best_cost = cost
                best_action = action
                best_trajectory = trajectory

        # Determine reason
        if best_action["heater_on"]:
            reason = "heating_to_target"
        elif best_action["cooler_on"]:
            reason = "cooling_to_target"
        elif best_trajectory and best_trajectory[-1] > target_temp:
            reason = "preventing_overshoot"
        elif best_trajectory and best_trajectory[-1] < target_temp:
            reason = "preventing_undershoot"
        else:
            reason = "maintaining_target"

        return {
            "heater_on": best_action["heater_on"],
            "cooler_on": best_action["cooler_on"],
            "reason": reason,
            "predicted_temp": best_trajectory[-1] if best_trajectory else current_temp,
            "cost": best_cost,
        }

    def predict_trajectory(
        self,
        initial_temp: float,
        heater_sequence: list[bool],
        cooler_sequence: list[bool],
        ambient_temp: float,
    ) -> list[float]:
        """Predict temperature trajectory given heater and cooler sequences.

        Args:
            initial_temp: Starting temperature (°C)
            heater_sequence: Sequence of heater states over horizon
            cooler_sequence: Sequence of cooler states over horizon
            ambient_temp: Ambient temperature (°C)

        Returns:
            List of predicted temperatures at each time step

        Raises:
            ValueError: If heater and cooler both ON at same time step (mutual exclusion)
        """
        if not self.has_model:
            return [initial_temp] * len(heater_sequence)

        # Validate sequences have same length
        if len(heater_sequence) != len(cooler_sequence):
            raise ValueError("Heater and cooler sequences must have same length")

        trajectory = []
        temp = initial_temp

        for heater_on, cooler_on in zip(heater_sequence, cooler_sequence):
            # Enforce mutual exclusion
            if heater_on and cooler_on:
                raise ValueError("Cannot have both heater and cooler ON (mutual exclusion)")

            # Calculate temperature change rate based on active system
            temp_above_ambient = temp - ambient_temp

            if heater_on:
                # Heater ON: add heating power, subtract ambient cooling
                rate = self.heating_rate - self.ambient_coeff * temp_above_ambient
            elif cooler_on and self.has_cooling:
                # Cooler ON: subtract cooling power and ambient effect
                rate = -self.cooling_rate - self.ambient_coeff * temp_above_ambient
            else:
                # Both OFF: only ambient effect
                rate = -self.ambient_coeff * temp_above_ambient

            # Clamp rate to physical limits
            rate = np.clip(rate, -self.max_temp_rate, self.max_temp_rate)

            # Update temperature
            temp = temp + rate * self.dt_hours
            trajectory.append(float(temp))

        return trajectory
