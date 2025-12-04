"""Model Predictive Control for fermentation temperature regulation.

Uses a learned thermal model to predict temperature trajectory and prevent
overshoot by computing optimal heater ON/OFF actions over a receding horizon.

The thermal model accounts for:
- Heater power (temperature rise when ON)
- Natural cooling toward ambient temperature
- Thermal inertia (time lag between heater state and temperature change)

MPC solves an optimization problem at each time step:
1. Predict temperature over next N hours for different heater sequences
2. Choose sequence that minimizes distance from target without overshoot
3. Apply first action from optimal sequence
4. Repeat at next time step (receding horizon)
"""

import numpy as np
from typing import Optional


class MPCTemperatureController:
    """Model Predictive Controller for fermentation temperature.

    The controller learns a simple thermal model from historical data:
    - Heater ON: dT/dt = heating_rate - cooling_coeff * (T - T_ambient)
    - Heater OFF: dT/dt = -cooling_coeff * (T - T_ambient)

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
        self.heating_rate: Optional[float] = None  # °C/hour when heater ON
        self.cooling_coeff: Optional[float] = None  # Cooling coefficient
        self.has_model = False

    def learn_thermal_model(
        self,
        temp_history: list[float],
        time_history: list[float],
        heater_history: list[bool],
        ambient_history: list[float],
    ) -> dict:
        """Learn thermal model parameters from historical data.

        Args:
            temp_history: Temperature readings (°C)
            time_history: Time stamps (hours)
            heater_history: Heater state (True=ON, False=OFF)
            ambient_history: Ambient temperature (°C)

        Returns:
            Dictionary with learned parameters and fit quality
        """
        # Validate all histories have same length
        min_len = min(
            len(temp_history),
            len(time_history),
            len(heater_history),
            len(ambient_history),
        )

        if min_len < 3:
            return {
                "success": False,
                "reason": "insufficient_data",
                "heating_rate": None,
                "cooling_coeff": None,
            }

        # Slice all histories to same length to prevent IndexError
        temp_history = temp_history[-min_len:]
        time_history = time_history[-min_len:]
        heater_history = heater_history[-min_len:]
        ambient_history = ambient_history[-min_len:]

        # Calculate temperature rates (dT/dt)
        heating_rates = []
        cooling_rates = []

        for i in range(1, len(temp_history)):
            dt = time_history[i] - time_history[i - 1]
            if dt <= 0:
                continue

            dtemp = temp_history[i] - temp_history[i - 1]
            rate = dtemp / dt  # °C/hour

            # Temperature difference from ambient
            temp_above_ambient = temp_history[i - 1] - ambient_history[i - 1]

            if heater_history[i - 1]:
                # Heater ON: rate = heating_rate - cooling_coeff * (T - T_ambient)
                heating_rates.append((rate, temp_above_ambient))
            else:
                # Heater OFF: rate = -cooling_coeff * (T - T_ambient)
                cooling_rates.append((rate, temp_above_ambient))

        # Estimate cooling coefficient from cooling periods
        if cooling_rates:
            # rate = -cooling_coeff * temp_above_ambient
            # cooling_coeff = -rate / temp_above_ambient
            coeffs = []
            for rate, temp_diff in cooling_rates:
                if abs(temp_diff) > 0.1:  # Avoid division by near-zero
                    coeff = -rate / temp_diff
                    if coeff > 0:  # Sanity check
                        coeffs.append(coeff)

            self.cooling_coeff = float(np.median(coeffs)) if coeffs else 0.1
        else:
            self.cooling_coeff = 0.1  # Default fallback

        # Estimate heating rate from heating periods
        if heating_rates:
            # rate = heating_rate - cooling_coeff * temp_above_ambient
            # heating_rate = rate + cooling_coeff * temp_above_ambient
            net_heating_rates = []
            for rate, temp_diff in heating_rates:
                net_rate = rate + self.cooling_coeff * temp_diff
                net_heating_rates.append(net_rate)

            self.heating_rate = float(np.median(net_heating_rates))
        else:
            self.heating_rate = 1.1  # Default fallback (1.1°C/hour, ~2°F/hour equivalent)

        self.has_model = True

        return {
            "success": True,
            "reason": None,
            "heating_rate": self.heating_rate,
            "cooling_coeff": self.cooling_coeff,
        }

    def compute_action(
        self,
        current_temp: float,
        target_temp: float,
        ambient_temp: float,
        heater_currently_on: Optional[bool] = None,
    ) -> dict:
        """Compute optimal heater action using MPC.

        Args:
            current_temp: Current fermentation temperature (°C)
            target_temp: Target temperature (°C)
            ambient_temp: Ambient/room temperature (°C)
            heater_currently_on: Current heater state (for continuity preference)

        Returns:
            Dictionary with control decision:
            - heater_on: True/False/None (None if no model)
            - reason: Explanation for decision
            - predicted_temp: Predicted temperature at end of horizon
            - cost: Optimization cost (lower is better)
        """
        if not self.has_model:
            return {
                "heater_on": None,
                "reason": "no_model",
                "predicted_temp": None,
                "cost": None,
            }

        # If already above target, don't heat
        if current_temp >= target_temp:
            return {
                "heater_on": False,
                "reason": "above_target",
                "predicted_temp": current_temp,
                "cost": 0,
            }

        # Compute number of time steps in horizon
        n_steps = int(self.horizon_hours / self.dt_hours)

        # Evaluate both heater ON and OFF for first action
        best_action = None
        best_cost = float("inf")
        best_trajectory = None

        for first_action in [True, False]:
            # Simple heuristic: maintain first action for entire horizon
            # More sophisticated MPC would try all 2^n_steps sequences
            heater_sequence = [first_action] * n_steps

            # Predict trajectory
            trajectory = self.predict_trajectory(
                current_temp, heater_sequence, ambient_temp
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

            # Small penalty for switching heater state (reduce cycling)
            if heater_currently_on is not None and first_action != heater_currently_on:
                cost += 0.1

            if cost < best_cost:
                best_cost = cost
                best_action = first_action
                best_trajectory = trajectory

        # Determine reason
        if best_action:
            if best_trajectory[-1] < target_temp:
                reason = "heating_to_target"
            else:
                reason = "maintaining_target"
        else:
            reason = "preventing_overshoot"

        return {
            "heater_on": best_action,
            "reason": reason,
            "predicted_temp": best_trajectory[-1] if best_trajectory else current_temp,
            "cost": best_cost,
        }

    def predict_trajectory(
        self,
        initial_temp: float,
        heater_sequence: list[bool],
        ambient_temp: float,
    ) -> list[float]:
        """Predict temperature trajectory given heater sequence.

        Args:
            initial_temp: Starting temperature (°C)
            heater_sequence: Sequence of heater states over horizon
            ambient_temp: Ambient temperature (°C)

        Returns:
            List of predicted temperatures at each time step
        """
        if not self.has_model:
            return [initial_temp] * len(heater_sequence)

        trajectory = []
        temp = initial_temp

        for heater_on in heater_sequence:
            # Calculate temperature change rate
            temp_above_ambient = temp - ambient_temp

            if heater_on:
                # Heater ON: add heating power, subtract natural cooling
                rate = self.heating_rate - self.cooling_coeff * temp_above_ambient
            else:
                # Heater OFF: only natural cooling
                rate = -self.cooling_coeff * temp_above_ambient

            # Clamp rate to physical limits
            rate = np.clip(rate, -self.max_temp_rate, self.max_temp_rate)

            # Update temperature
            temp = temp + rate * self.dt_hours
            trajectory.append(float(temp))

        return trajectory
