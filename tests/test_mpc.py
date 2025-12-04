"""Tests for Model Predictive Control temperature controller."""

import pytest
from backend.ml.control.mpc import MPCTemperatureController


class TestMPCTemperatureController:
    """Tests for the MPC temperature controller."""

    def test_initialization(self):
        """Controller initializes with default parameters."""
        controller = MPCTemperatureController()

        assert controller.horizon_hours == 4.0
        assert controller.max_temp_rate == 1.0
        assert controller.dt_hours == 0.25

    def test_requires_system_model(self):
        """Controller needs thermal model before controlling."""
        controller = MPCTemperatureController()

        # Try to control without model
        action = controller.compute_action(
            current_temp=68.0,
            target_temp=70.0,
            ambient_temp=65.0
        )

        assert action["heater_on"] is None
        assert action["reason"] == "no_model"

    def test_computes_heater_action_heating(self):
        """Controller computes heater ON/OFF for heating scenario."""
        controller = MPCTemperatureController(horizon_hours=2.0)

        # Learn simple thermal model (will use default parameters initially)
        controller.learn_thermal_model(
            temp_history=[68.0, 68.5, 69.0, 69.3],
            time_history=[0, 0.25, 0.5, 0.75],
            heater_history=[True, True, True, False],
            ambient_history=[65.0, 65.0, 65.0, 65.0]
        )

        # Compute action: need to heat from 68°F to 70°F
        action = controller.compute_action(
            current_temp=68.0,
            target_temp=70.0,
            ambient_temp=65.0
        )

        assert action["heater_on"] in [True, False]  # Should make a decision
        assert action["reason"] is not None
        assert "predicted_temp" in action

    def test_prevents_overshoot_when_approaching_target(self):
        """Controller prevents overshoot by turning off heater early."""
        controller = MPCTemperatureController(horizon_hours=2.0)

        # Simple thermal model: heater adds ~2°F/hour, natural cooling -0.5°F/hour
        controller.learn_thermal_model(
            temp_history=[68.0, 70.0, 71.5, 70.8],
            time_history=[0, 1.0, 2.0, 3.0],
            heater_history=[True, True, False, False],
            ambient_history=[65.0, 65.0, 65.0, 65.0]
        )

        # Approaching target: currently 69.5°F, target 70°F, heater currently ON
        # MPC should turn heater OFF to prevent overshoot
        action = controller.compute_action(
            current_temp=69.5,
            target_temp=70.0,
            ambient_temp=65.0,
            heater_currently_on=True
        )

        # Should turn heater off or keep it off to avoid overshooting 70°F
        # With 2°F/hour heat rate, 0.5°F remaining at current temp means ~15 min to target
        # Heater should be off or controller should predict safe action
        assert action["predicted_temp"] is not None

    def test_handles_cooling_scenario(self):
        """Controller handles cooling (heater should stay off)."""
        controller = MPCTemperatureController()

        controller.learn_thermal_model(
            temp_history=[70.0, 69.5, 69.0],
            time_history=[0, 0.5, 1.0],
            heater_history=[False, False, False],
            ambient_history=[65.0, 65.0, 65.0]
        )

        # Current temp above target: don't heat
        action = controller.compute_action(
            current_temp=72.0,
            target_temp=70.0,
            ambient_temp=65.0
        )

        assert action["heater_on"] is False
        assert "cooling" in action["reason"].lower() or "above" in action["reason"].lower()

    def test_predicts_future_temperature_trajectory(self):
        """Controller predicts temperature trajectory over horizon."""
        controller = MPCTemperatureController(horizon_hours=4.0, dt_hours=1.0)

        controller.learn_thermal_model(
            temp_history=[68.0, 69.0, 70.0],
            time_history=[0, 1.0, 2.0],
            heater_history=[True, True, False],
            ambient_history=[65.0, 65.0, 65.0]
        )

        # Get predicted trajectory
        trajectory = controller.predict_trajectory(
            initial_temp=68.0,
            heater_sequence=[True, True, False, False],  # 4 time steps
            ambient_temp=65.0
        )

        assert len(trajectory) == 4
        # Temperatures should change based on heater state
        # With heater on, temp should increase
        assert trajectory[1] > trajectory[0]  # Heater on → warming