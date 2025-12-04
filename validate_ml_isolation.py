#!/usr/bin/env python3
"""Validate ML per-device state isolation on Raspberry Pi.

This script demonstrates that:
1. MLPipelineManager creates separate pipelines per device
2. Each device maintains isolated Kalman/anomaly/prediction state
3. No cross-contamination between RED and BLUE Tilts
"""

import sys
sys.path.insert(0, '/opt/brewsignal')

from backend.ml.pipeline_manager import MLPipelineManager
from backend.ml.config import MLConfig

def main():
    print("=" * 60)
    print("ML PIPELINE ISOLATION VALIDATION")
    print("=" * 60)

    # Initialize manager
    config = MLConfig()
    manager = MLPipelineManager(config=config)

    print("\n✓ MLPipelineManager initialized")
    print(f"  - Kalman filter: {'enabled' if config.enable_kalman_filter else 'disabled'}")
    print(f"  - Anomaly detection: {'enabled' if config.enable_anomaly_detection else 'disabled'}")
    print(f"  - Predictions: {'enabled' if config.enable_predictions else 'disabled'}")
    print(f"  - MPC: {'enabled' if config.enable_mpc else 'disabled'}")

    # Simulate RED Tilt readings (low SG, declining)
    print("\n" + "-" * 60)
    print("Processing RED Tilt readings (SG 1.050 → 1.040)...")
    print("-" * 60)

    for i in range(10):
        result = manager.process_reading(
            device_id="RED",
            sg=1.050 - i * 0.001,
            temp=68.0,
            rssi=-60,
            time_hours=float(i * 4),
            ambient_temp=65.0,
        )

    print(f"✓ RED: Processed 10 readings")
    print(f"  - Final SG filtered: {result['kalman']['sg_filtered']:.4f}")
    print(f"  - Final temp filtered: {result['kalman']['temp_filtered']:.1f}°F")
    print(f"  - Anomaly detected: {result['anomaly']['is_anomaly']}")

    # Simulate BLUE Tilt readings (high SG, stuck)
    print("\n" + "-" * 60)
    print("Processing BLUE Tilt readings (SG 1.080, stuck)...")
    print("-" * 60)

    for i in range(10):
        result = manager.process_reading(
            device_id="BLUE",
            sg=1.080,  # Stuck at same value
            temp=75.0,
            rssi=-50,
            time_hours=float(i * 4),
            ambient_temp=65.0,
        )

    print(f"✓ BLUE: Processed 10 readings")
    print(f"  - Final SG filtered: {result['kalman']['sg_filtered']:.4f}")
    print(f"  - Final temp filtered: {result['kalman']['temp_filtered']:.1f}°F")
    print(f"  - Anomaly detected: {result['anomaly']['is_anomaly']}")

    # Verify isolation
    print("\n" + "=" * 60)
    print("ISOLATION VERIFICATION")
    print("=" * 60)

    pipeline_red = manager.get_pipeline("RED")
    pipeline_blue = manager.get_pipeline("BLUE")

    # Check history lengths
    print("\n1. History Lengths (should be equal but separate)")
    print(f"   RED  sg_history: {len(pipeline_red.sg_history)} entries")
    print(f"   BLUE sg_history: {len(pipeline_blue.sg_history)} entries")

    # Check SG ranges
    red_sg_range = (min(pipeline_red.sg_history), max(pipeline_red.sg_history))
    blue_sg_range = (min(pipeline_blue.sg_history), max(pipeline_blue.sg_history))

    print("\n2. SG Ranges (should not overlap)")
    print(f"   RED:  {red_sg_range[0]:.4f} - {red_sg_range[1]:.4f}")
    print(f"   BLUE: {blue_sg_range[0]:.4f} - {blue_sg_range[1]:.4f}")

    # Check temp ranges
    red_temp_range = (min(pipeline_red.temp_history), max(pipeline_red.temp_history))
    blue_temp_range = (min(pipeline_blue.temp_history), max(pipeline_blue.temp_history))

    print("\n3. Temperature Ranges (should not overlap)")
    print(f"   RED:  {red_temp_range[0]:.1f}°F - {red_temp_range[1]:.1f}°F")
    print(f"   BLUE: {blue_temp_range[0]:.1f}°F - {blue_temp_range[1]:.1f}°F")

    # Verify no contamination
    sg_overlap = not (red_sg_range[1] < blue_sg_range[0] or blue_sg_range[1] < red_sg_range[0])
    temp_overlap = not (red_temp_range[1] < blue_temp_range[0] or blue_temp_range[1] < red_temp_range[0])

    print("\n" + "=" * 60)
    if not sg_overlap and not temp_overlap:
        print("✅ SUCCESS: No state contamination between devices!")
        print("   Each device maintains isolated state.")
    else:
        print("❌ FAILURE: State contamination detected!")
        print("   Device histories are mixing.")
        return 1

    print("=" * 60)

    # List active pipelines
    active = manager.list_active_pipelines()
    print(f"\n📊 Active pipelines: {', '.join(active)}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
