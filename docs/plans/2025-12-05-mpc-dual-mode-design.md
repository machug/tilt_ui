# MPC Dual-Mode Temperature Control Design

**Date:** 2025-12-05
**Issue:** [#64 - Extend MPC temperature controller to support dual-mode (heater + cooler) operation](https://github.com/machug/brewsignal/issues/64)
**Status:** Design Approved

## Problem Statement

The current MPC (Model Predictive Control) temperature controller in `backend/ml/control/mpc.py` is **heater-only**. It learns a heating rate and natural cooling coefficient, optimizing heater ON/OFF actions over a prediction horizon. However, BrewSignal's PID-based temperature controller (`backend/temp_controller.py`) already supports **dual-mode** operation with independent heater and cooler entities per batch.

The MPC cannot take full advantage of active cooling capabilities, limiting its ability to maintain tight temperature control in warmer environments.

Additionally, the MPC currently uses **Fahrenheit** for all calculations and parameters, violating the project standard (CLAUDE.md) that requires **Celsius** for all internal calculations.

## Goals

1. Extend MPC thermal model to support active cooling (cooler ON state)
2. Convert all MPC code from Fahrenheit to Celsius
3. Maintain full backward compatibility for heater-only batches
4. Enforce mutual exclusion (heater and cooler never run simultaneously)
5. Achieve tighter temperature control with faster response to deviations

## Design Overview

**Approach:** Parallel thermal models with shared ambient coefficient (Approach 1)

### Thermal Model Parameters

**Extended parameter set:**

```python
class MPCTemperatureController:
    # Thermal model parameters (learned from data)
    self.heating_rate: Optional[float] = None      # °C/hour when heater ON
    self.cooling_rate: Optional[float] = None      # °C/hour when cooler ON (active cooling)
    self.ambient_coeff: Optional[float] = None     # Natural cooling coefficient
    self.has_model: bool = False                   # True if any model learned
    self.has_cooling: bool = False                 # True if cooling model available
```

**Operating modes:**
1. **Heater-only mode**: `has_cooling = False`, only `heating_rate` and `ambient_coeff` learned
2. **Dual-mode**: `has_cooling = True`, all three parameters learned
3. **No model**: `has_model = False`, controller returns None for all actions

### Thermal Equations (Celsius)

- **Heater ON, Cooler OFF**: `dT/dt = heating_rate - ambient_coeff * (T - T_ambient)`
- **Heater OFF, Cooler ON**: `dT/dt = -cooling_rate - ambient_coeff * (T - T_ambient)`
- **Both OFF**: `dT/dt = -ambient_coeff * (T - T_ambient)`
- **Both ON**: **INVALID** (mutual exclusion enforced)

**Physical interpretation:**
- `heating_rate`: Net power from heater element (always positive, °C/hour)
- `cooling_rate`: Net cooling from active cooler (always positive, applied as negative dT/dt, °C/hour)
- `ambient_coeff`: Heat exchange with environment (typically 0.05-0.2 for insulated chambers, dimensionless)

## Component Design

### 1. Temperature Unit Conversion

**Changes:**
- Convert all parameters, comments, and docstrings from °F to °C
- Update test fixtures to use Celsius values
- No conversion functions needed (callers must provide Celsius)

**Example conversions:**
- 68°F → 20°C
- 70°F → 21.1°C
- 2°F/hour → 1.1°C/hour (approximate)

**Risk mitigation:**
- Update all tests to verify Celsius behavior
- Explicit unit specifications in all docstrings
- Search codebase for any integration points that might need adjustment

### 2. Extended Learning Algorithm

**Modified signature:**

```python
def learn_thermal_model(
    self,
    temp_history: list[float],      # °C
    time_history: list[float],       # hours
    heater_history: list[bool],
    ambient_history: list[float],    # °C
    cooler_history: Optional[list[bool]] = None,  # NEW: optional cooler state
) -> dict:
```

**Algorithm steps:**

1. **Validate inputs** (existing logic preserved)
   - Check minimum length (3+ points)
   - Slice all histories to same length

2. **Separate data into regimes:**
   - **Idle periods**: Both heater and cooler OFF
   - **Heating periods**: Heater ON, cooler OFF
   - **Cooling periods**: Cooler ON, heater OFF
   - **Invalid periods**: Both ON (log warning, skip)

3. **Learn ambient_coeff from idle periods:**
   ```
   rate = -ambient_coeff * temp_above_ambient
   ambient_coeff = -rate / temp_above_ambient
   Use median of valid coefficients, default to 0.1
   ```

4. **Learn heating_rate from heating periods:**
   ```
   rate = heating_rate - ambient_coeff * temp_above_ambient
   heating_rate = rate + ambient_coeff * temp_above_ambient
   Use median, default to 1.0°C/hour
   ```

5. **Learn cooling_rate from cooling periods (if cooler_history provided):**
   ```
   rate = -cooling_rate - ambient_coeff * temp_above_ambient
   cooling_rate = -rate - ambient_coeff * temp_above_ambient
   Use median (must be positive), set has_cooling = True
   ```

**Return value:**

```python
{
    "success": bool,
    "reason": Optional[str],           # If success=False
    "heating_rate": Optional[float],
    "cooling_rate": Optional[float],   # None if no cooling data
    "ambient_coeff": Optional[float],
    "has_cooling": bool,
}
```

**Fallback behavior:**
- Insufficient data → `success=False, reason="insufficient_data"`
- No cooler data → heater-only mode (`has_cooling=False`)
- Mutual exclusion violations → log warning, skip those data points

### 3. Extended Control Loop

**Modified signature:**

```python
def compute_action(
    self,
    current_temp: float,           # °C
    target_temp: float,            # °C
    ambient_temp: float,           # °C
    heater_currently_on: Optional[bool] = None,
    cooler_currently_on: Optional[bool] = None,  # NEW
) -> dict:
```

**Return value:**

```python
{
    "heater_on": Optional[bool],      # True/False/None (None if no model)
    "cooler_on": Optional[bool],      # True/False/None (None if no model/cooling)
    "reason": str,                    # Explanation for decision
    "predicted_temp": Optional[float], # Predicted temp at end of horizon (°C)
    "cost": Optional[float],          # Optimization cost (lower is better)
}
```

**Control logic:**

1. **Early exits:**
   - No model → return all None
   - Above target and no cooling → turn off heater

2. **Evaluate all valid actions:**
   - **Action 1**: Heater ON, Cooler OFF
   - **Action 2**: Both OFF
   - **Action 3**: Cooler ON, Heater OFF (only if `has_cooling=True`)

3. **For each action:**
   - Predict temperature trajectory over horizon (4 hours, 15-min steps)
   - Compute cost using quadratic penalty with 10x overshoot multiplier
   - Add small penalty (0.1) for state changes to reduce cycling

4. **Select best action:**
   - Minimum cost wins
   - Return heater_on, cooler_on, predicted trajectory, reason

**Reason codes:**
- `"no_model"`: No thermal model learned yet
- `"above_target_no_cooling"`: Above target, no cooling available
- `"heating_to_target"`: Heater ON to reach target
- `"cooling_to_target"`: Cooler ON to reach target
- `"preventing_overshoot"`: Action prevents temperature overshoot
- `"preventing_undershoot"`: Action prevents temperature undershoot
- `"maintaining_target"`: At target, maintaining current state

### 4. Extended Trajectory Prediction

**Modified signature:**

```python
def predict_trajectory(
    self,
    initial_temp: float,              # °C
    heater_sequence: list[bool],
    cooler_sequence: list[bool],      # NEW
    ambient_temp: float,              # °C
) -> list[float]:
```

**Algorithm:**

```python
trajectory = []
temp = initial_temp

for heater_on, cooler_on in zip(heater_sequence, cooler_sequence):
    # Enforce mutual exclusion
    if heater_on and cooler_on:
        raise ValueError("Mutual exclusion violation")

    temp_above_ambient = temp - ambient_temp

    if heater_on:
        rate = self.heating_rate - self.ambient_coeff * temp_above_ambient
    elif cooler_on and self.has_cooling:
        rate = -self.cooling_rate - self.ambient_coeff * temp_above_ambient
    else:
        rate = -self.ambient_coeff * temp_above_ambient

    # Clamp to physical limits
    rate = np.clip(rate, -self.max_temp_rate, self.max_temp_rate)

    # Update temperature
    temp = temp + rate * self.dt_hours
    trajectory.append(temp)

return trajectory
```

**Key features:**
- Mutual exclusion enforced with runtime assertion
- Graceful handling when `has_cooling=False`
- Rate clamping prevents unrealistic predictions
- Ambient effect always applied

## Test Coverage

### Updated Existing Tests (Convert to Celsius)

All existing tests in `tests/test_mpc.py` need temperature values converted from Fahrenheit to Celsius:

- `test_initialization()` - No changes needed (no temperatures)
- `test_requires_system_model()` - Update test temps: 68°F → 20°C, 70°F → 21.1°C, 65°F → 18.3°C
- `test_computes_heater_action_heating()` - Update temps
- `test_prevents_overshoot_when_approaching_target()` - Update temps and verify rates scale correctly
- `test_handles_cooling_scenario()` - Update temps
- `test_predicts_future_temperature_trajectory()` - Update temps

### New Dual-Mode Tests

1. **`test_learns_cooling_rate_from_cooler_data()`**
   - Provide mixed heater/cooler history
   - Verify `cooling_rate` learned correctly
   - Verify `has_cooling = True`

2. **`test_backward_compatibility_heater_only()`**
   - Don't provide `cooler_history`
   - Verify heater-only mode (`has_cooling = False`)
   - Verify existing heater logic unchanged

3. **`test_computes_cooler_action_when_above_target()`**
   - Current temp 22°C, target 20°C, ambient 18°C
   - Verify `cooler_on = True, heater_on = False`
   - Verify reason includes "cooling"

4. **`test_mutual_exclusion_in_predictions()`**
   - Verify trajectory prediction raises error if both ON
   - Verify control loop never returns both ON

5. **`test_mutual_exclusion_violation_in_learning()`**
   - Provide history with both heater and cooler ON
   - Verify warning logged
   - Verify those points skipped in learning

6. **`test_prevents_overshoot_with_active_cooling()`**
   - Current temp 21.5°C, target 20°C, cooler currently ON
   - MPC should turn cooler OFF early to prevent undershoot
   - Verify predicted temp doesn't go below target

7. **`test_prevents_undershoot_with_active_heating()`**
   - Current temp 19.5°C, target 20°C, heater currently ON
   - MPC should turn heater OFF early to prevent overshoot
   - Verify predicted temp doesn't go above target

8. **`test_dual_mode_both_off_in_deadband()`**
   - Current temp exactly at target
   - Verify both heater and cooler OFF
   - Verify reason includes "maintaining"

## Integration Points

### PID Controller Integration

The PID controller (`backend/temp_controller.py`) will need to call the extended MPC methods:

**Current heater-only call pattern:**
```python
# Learn model
mpc.learn_thermal_model(
    temp_history=[...],  # in °C
    time_history=[...],
    heater_history=[...],
    ambient_history=[...],
)

# Compute action
action = mpc.compute_action(
    current_temp=20.0,  # °C
    target_temp=21.1,   # °C
    ambient_temp=18.3,  # °C
    heater_currently_on=True,
)

# Use result
if action["heater_on"] is not None:
    # Apply heater action
```

**Extended dual-mode call pattern:**
```python
# Learn model (with cooler data if available)
mpc.learn_thermal_model(
    temp_history=[...],  # in °C
    time_history=[...],
    heater_history=[...],
    ambient_history=[...],
    cooler_history=[...] if has_cooler else None,  # NEW
)

# Compute action (with cooler state)
action = mpc.compute_action(
    current_temp=20.0,  # °C
    target_temp=21.1,   # °C
    ambient_temp=18.3,  # °C
    heater_currently_on=True,
    cooler_currently_on=False,  # NEW
)

# Use results
if action["heater_on"] is not None:
    # Apply heater action
if action["cooler_on"] is not None and has_cooler:
    # Apply cooler action
```

**Note:** Integration with the actual PID control loop is **out of scope** for this design. This issue focuses only on extending the MPC class itself. Integration will be handled separately.

## Benefits

1. **Tighter temperature control** in warmer environments with active cooling
2. **Faster response** to temperature deviations (active cooling vs passive)
3. **Overshoot prevention** for both heating and cooling (addresses Issue #60)
4. **Project standard compliance** (Celsius throughout)
5. **Unified control strategy** between PID and MPC modes
6. **Future-proof** for fermentation chambers with both heating and cooling

## Implementation Checklist

- [ ] Convert all MPC code from Fahrenheit to Celsius
  - [ ] Update parameter names and comments
  - [ ] Update docstrings with °C units
  - [ ] Update `max_temp_rate` default (1.0 → ~0.56 for equivalent F→C rate)
- [ ] Add `cooling_rate` and `has_cooling` parameters to class
- [ ] Update `learn_thermal_model()` to accept `cooler_history`
  - [ ] Separate data into three regimes
  - [ ] Learn `cooling_rate` from cooler-ON periods
  - [ ] Add mutual exclusion violation detection
  - [ ] Update return value to include cooling parameters
- [ ] Update `compute_action()` to accept `cooler_currently_on`
  - [ ] Evaluate heater/cooler combinations
  - [ ] Return both `heater_on` and `cooler_on`
  - [ ] Update reason codes
- [ ] Update `predict_trajectory()` to accept `cooler_sequence`
  - [ ] Add mutual exclusion enforcement
  - [ ] Add cooling rate calculations
- [ ] Update all existing tests to use Celsius
- [ ] Add new dual-mode test scenarios:
  - [ ] `test_learns_cooling_rate_from_cooler_data()`
  - [ ] `test_backward_compatibility_heater_only()`
  - [ ] `test_computes_cooler_action_when_above_target()`
  - [ ] `test_mutual_exclusion_in_predictions()`
  - [ ] `test_mutual_exclusion_violation_in_learning()`
  - [ ] `test_prevents_overshoot_with_active_cooling()`
  - [ ] `test_prevents_undershoot_with_active_heating()`
  - [ ] `test_dual_mode_both_off_in_deadband()`
- [ ] Update documentation
  - [ ] Update docstrings in `mpc.py`
  - [ ] Update `docs/plans/2025-11-29-ml-enhancements.md` with dual-mode details

## Related Files

- `backend/ml/control/mpc.py` - MPC implementation
- `backend/temp_controller.py` - PID controller with dual-mode support (integration out of scope)
- `tests/test_mpc.py` - MPC test suite
- `docs/plans/2025-11-29-ml-enhancements.md` - ML enhancements plan

## References

- Issue #64: Extend MPC temperature controller to support dual-mode operation
- Issue #60: Cooling overshoot triggering unnecessary heating (solved by MPC's thermal inertia modeling)
- `CLAUDE.md`: Temperature control architecture documentation
