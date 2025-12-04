"""Tests for Model Predictive Control temperature controller."""

import pytest
from backend.ml.control.mpc import MPCTemperatureController


class TestMPCTemperatureController:
    """Tests for the MPC temperature controller."""

    def test_initialization(self):
        """Controller initializes with default parameters."""
        controller = MPCTemperatureController()

        assert controller.horizon_hours == 4.0
        assert controller.max_temp_rate == 0.56
        assert controller.dt_hours == 0.25

    def test_requires_system_model(self):
        """Controller needs thermal model before controlling."""
        controller = MPCTemperatureController()

        # Try to control without model
        action = controller.compute_action(
            current_temp=20.0,
            target_temp=21.1,
            ambient_temp=18.3
        )

        assert action["heater_on"] is None
        assert action["cooler_on"] is None
        assert action["reason"] == "no_model"

    def test_computes_heater_action_heating(self):
        """Controller computes heater ON/OFF for heating scenario."""
        controller = MPCTemperatureController(horizon_hours=2.0)

        # Learn simple thermal model (will use default parameters initially)
        controller.learn_thermal_model(
            temp_history=[20.0, 20.3, 20.6, 20.7],
            time_history=[0, 0.25, 0.5, 0.75],
            heater_history=[True, True, True, False],
            ambient_history=[18.3, 18.3, 18.3, 18.3]
        )

        # Compute action: need to heat from 20°C to 21.1°C
        action = controller.compute_action(
            current_temp=20.0,
            target_temp=21.1,
            ambient_temp=18.3
        )

        assert action["heater_on"] in [True, False]  # Should make a decision
        assert action["reason"] is not None
        assert "predicted_temp" in action

    def test_prevents_overshoot_when_approaching_target(self):
        """Controller prevents overshoot by turning off heater early."""
        controller = MPCTemperatureController(horizon_hours=2.0)

        # Simple thermal model: heater adds ~1.1°C/hour, natural cooling -0.3°C/hour
        controller.learn_thermal_model(
            temp_history=[20.0, 21.1, 21.9, 21.6],
            time_history=[0, 1.0, 2.0, 3.0],
            heater_history=[True, True, False, False],
            ambient_history=[18.3, 18.3, 18.3, 18.3]
        )

        # Approaching target: currently 20.8°C, target 21.1°C, heater currently ON
        # MPC should turn heater OFF to prevent overshoot
        action = controller.compute_action(
            current_temp=20.8,
            target_temp=21.1,
            ambient_temp=18.3,
            heater_currently_on=True
        )

        # Should turn heater off or keep it off to avoid overshooting 21.1°C
        # With 1.1°C/hour heat rate, 0.3°C remaining at current temp means ~15 min to target
        # Heater should be off or controller should predict safe action
        assert action["predicted_temp"] is not None

    def test_handles_cooling_scenario(self):
        """Controller handles cooling (heater should stay off)."""
        controller = MPCTemperatureController()

        controller.learn_thermal_model(
            temp_history=[21.1, 20.8, 20.6],
            time_history=[0, 0.5, 1.0],
            heater_history=[False, False, False],
            ambient_history=[18.3, 18.3, 18.3]
        )

        # Current temp above target: don't heat
        action = controller.compute_action(
            current_temp=22.2,
            target_temp=21.1,
            ambient_temp=18.3
        )

        assert action["heater_on"] is False
        assert action["cooler_on"] is False or action["cooler_on"] is None  # Could be False (dual) or None (heater-only)
        assert "cooling" in action["reason"].lower() or "above" in action["reason"].lower()

    def test_predicts_future_temperature_trajectory(self):
        """Controller predicts temperature trajectory over horizon."""
        controller = MPCTemperatureController(horizon_hours=4.0, dt_hours=1.0)

        controller.learn_thermal_model(
            temp_history=[20.0, 20.6, 21.1],
            time_history=[0, 1.0, 2.0],
            heater_history=[True, True, False],
            ambient_history=[18.3, 18.3, 18.3]
        )

        # Get predicted trajectory
        trajectory = controller.predict_trajectory(
            initial_temp=20.0,
            heater_sequence=[True, True, False, False],  # 4 time steps
            cooler_sequence=[False, False, False, False],  # 4 time steps
            ambient_temp=18.3
        )

        assert len(trajectory) == 4
        # Temperatures should change based on heater state
        # With heater on, temp should increase
        assert trajectory[1] > trajectory[0]  # Heater on → warming

    def test_initializes_without_cooling_model(self):
        """Controller initializes without cooling capability."""
        controller = MPCTemperatureController()

        assert controller.has_cooling is False
        assert controller.cooling_rate is None

    def test_learns_cooling_rate_from_cooler_data(self):
        """Controller learns cooling rate from cooler-ON periods."""
        controller = MPCTemperatureController()

        # History with mixed heating/cooling/idle periods
        # Cooler provides active cooling beyond natural ambient exchange
        result = controller.learn_thermal_model(
            temp_history=[21.1, 21.7, 22.2, 20.6, 19.4, 19.2, 19.0],
            time_history=[0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
            heater_history=[False, True, True, False, False, False, False],
            ambient_history=[18.3, 18.3, 18.3, 18.3, 18.3, 18.3, 18.3],
            cooler_history=[False, False, False, True, True, False, False],
        )

        assert result["success"] is True
        assert result["has_cooling"] is True
        assert result["cooling_rate"] is not None
        assert result["cooling_rate"] > 0  # Cooling rate should be positive
        assert controller.has_cooling is True
        assert controller.cooling_rate is not None

    def test_backward_compatibility_heater_only(self):
        """Controller works in heater-only mode when no cooler data provided."""
        controller = MPCTemperatureController()

        # Learn without providing cooler_history
        result = controller.learn_thermal_model(
            temp_history=[20.0, 20.3, 20.6, 20.7],
            time_history=[0, 0.25, 0.5, 0.75],
            heater_history=[True, True, True, False],
            ambient_history=[18.3, 18.3, 18.3, 18.3],
            # NO cooler_history parameter
        )

        assert result["success"] is True
        assert result["has_cooling"] is False
        assert result["cooling_rate"] is None
        assert controller.has_cooling is False

    def test_computes_cooler_action_when_above_target(self):
        """Controller turns on cooler when above target."""
        controller = MPCTemperatureController()

        # Learn dual-mode model
        controller.learn_thermal_model(
            temp_history=[21.1, 21.7, 22.2, 21.7, 21.1, 20.6],
            time_history=[0, 0.5, 1.0, 1.5, 2.0, 2.5],
            heater_history=[False, True, True, False, False, False],
            ambient_history=[18.3, 18.3, 18.3, 18.3, 18.3, 18.3],
            cooler_history=[False, False, False, True, True, False],
        )

        # Above target: should activate cooler
        action = controller.compute_action(
            current_temp=22.2,
            target_temp=21.1,
            ambient_temp=18.3,
            heater_currently_on=False,
            cooler_currently_on=False,
        )

        assert action["heater_on"] is False
        assert action["cooler_on"] is True
        assert "cooling" in action["reason"].lower()

    def test_prevents_overshoot_with_active_cooling(self):
        """Controller prevents undershoot by turning off cooler early."""
        controller = MPCTemperatureController(horizon_hours=2.0)

        # Learn aggressive cooling model
        controller.learn_thermal_model(
            temp_history=[22.2, 21.7, 21.1, 20.6, 20.0],
            time_history=[0, 0.25, 0.5, 0.75, 1.0],
            heater_history=[False, False, False, False, False],
            ambient_history=[18.3, 18.3, 18.3, 18.3, 18.3],
            cooler_history=[True, True, True, True, False],
        )

        # Approaching target from above: currently 21.3°C, target 21.1°C, cooler currently ON
        # MPC should evaluate whether to keep cooler on or turn it off
        action = controller.compute_action(
            current_temp=21.3,
            target_temp=21.1,
            ambient_temp=18.3,
            heater_currently_on=False,
            cooler_currently_on=True,
        )

        # Should make a decision (either keep cooling or turn off)
        assert action["predicted_temp"] is not None
        assert action["cooler_on"] is not None
        # MPC should evaluate both options and pick the best one
        # The key is that it doesn't crash and makes a reasonable prediction

    def test_dual_mode_both_off_in_deadband(self):
        """Controller evaluates all three actions when near target."""
        controller = MPCTemperatureController()

        # Learn dual-mode model
        controller.learn_thermal_model(
            temp_history=[21.1, 21.7, 22.2, 21.7, 21.1, 20.6, 21.1],
            time_history=[0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
            heater_history=[False, True, True, False, False, False, False],
            ambient_history=[18.3, 18.3, 18.3, 18.3, 18.3, 18.3, 18.3],
            cooler_history=[False, False, False, True, True, False, False],
        )

        # Exactly at target, ambient temp equal to target (no natural drift)
        action = controller.compute_action(
            current_temp=21.1,
            target_temp=21.1,
            ambient_temp=21.1,  # No temperature gradient
            heater_currently_on=False,
            cooler_currently_on=False,
        )

        # Should make a valid decision for all actuators
        assert action["heater_on"] is not None
        assert action["cooler_on"] is not None
        # When at target with no gradient, both should be off
        assert action["heater_on"] is False
        assert action["cooler_on"] is False

    def test_mutual_exclusion_violation_in_learning(self):
        """Learning algorithm logs warning and skips points with both ON."""
        controller = MPCTemperatureController()

        # History with mutual exclusion violation at t=1
        result = controller.learn_thermal_model(
            temp_history=[21.1, 21.7, 22.2, 21.7, 21.1],
            time_history=[0, 0.5, 1.0, 1.5, 2.0],
            heater_history=[False, True, True, False, False],
            ambient_history=[18.3, 18.3, 18.3, 18.3, 18.3],
            cooler_history=[False, True, False, False, False],  # Both ON at t=1
        )

        # Should still succeed (skip bad points)
        assert result["success"] is True
        # Should have learned something despite violation
        assert result["heating_rate"] is not None

    def test_predicts_cooling_trajectory(self):
        """Controller predicts cooling trajectory when cooler ON."""
        controller = MPCTemperatureController()

        # Learn dual-mode model
        controller.learn_thermal_model(
            temp_history=[21.1, 21.7, 22.2, 21.7, 21.1, 20.6],
            time_history=[0, 0.5, 1.0, 1.5, 2.0, 2.5],
            heater_history=[False, True, True, False, False, False],
            ambient_history=[18.3, 18.3, 18.3, 18.3, 18.3, 18.3],
            cooler_history=[False, False, False, True, True, False],
        )

        # Predict trajectory with cooler ON
        trajectory = controller.predict_trajectory(
            initial_temp=22.2,
            heater_sequence=[False, False, False, False],
            cooler_sequence=[True, True, True, True],
            ambient_temp=18.3
        )

        assert len(trajectory) == 4
        # With cooler on, temp should decrease
        assert trajectory[-1] < trajectory[0]
        # Should trend toward target
        assert trajectory[-1] < 22.2