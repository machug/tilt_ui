# ML Implementation Validation Guide

This guide shows how to validate the ML pipeline fixes on the Raspberry Pi.

## What Was Fixed

1. **Per-Device State Isolation** - Each Tilt now has its own ML pipeline (no cross-contamination)
2. **MPC Ambient History Safety** - No crashes when ambient temps are missing

## Current Raspberry Pi Status

**Live Tilts Detected:**
- 🔴 RED Tilt: 69.0°F, SG 0.9920
- 🔵 BLUE Tilt: 68.6°F, SG 1.0137

Both devices are being scanned but the ML pipeline manager keeps them isolated.

## Validation Methods

### Method 1: Run the Validation Script

```bash
# SSH to Pi
ssh pi@192.168.4.218
# Password: tilt

# Run validation
cd /opt/brewsignal
source .venv/bin/activate
python validate_ml_isolation.py
```

**Expected Output:**
```
✅ SUCCESS: No state contamination between devices!
   Each device maintains isolated state.

📊 Active pipelines: RED, BLUE
```

### Method 2: Check Service Logs

```bash
# View recent Tilt detections
sudo journalctl -u brewsignal -n 100 --no-pager | grep "BLE: Detected"

# Check for ML-related errors
sudo journalctl -u brewsignal -n 200 --no-pager | grep -E "(ERROR|Traceback|ML)"

# Live tail (watch in real-time)
sudo journalctl -u brewsignal -f
```

**What to Look For:**
- ✅ Both RED and BLUE Tilts detected regularly
- ✅ No errors mentioning "IndexError" or "ambient_history"
- ✅ No "MissingGreenlet" errors
- ✅ Clean startup with no ML import errors

### Method 3: Verify ML Dependencies

```bash
cd /opt/brewsignal
source .venv/bin/activate

# Test ML imports
python -c "
from backend.ml.pipeline_manager import MLPipelineManager
from backend.ml.pipeline import MLPipeline
from backend.ml.config import MLConfig
import numpy
import filterpy
import scipy
import sklearn
print('✅ All ML components import successfully')
"
```

### Method 4: Test Multi-Device Processing

```bash
# Create test script
cd /opt/brewsignal
cat > test_multi_device.py << 'EOF'
from backend.ml.pipeline_manager import MLPipelineManager

manager = MLPipelineManager()

# Process RED readings
for i in range(5):
    manager.process_reading(
        device_id="RED",
        sg=1.050 - i*0.001,
        temp=68.0,
        rssi=-60,
        time_hours=float(i),
    )

# Process BLUE readings
for i in range(5):
    manager.process_reading(
        device_id="BLUE",
        sg=1.080,
        temp=75.0,
        rssi=-50,
        time_hours=float(i),
    )

# Verify isolation
red = manager.get_pipeline("RED")
blue = manager.get_pipeline("BLUE")

print(f"RED history: {len(red.sg_history)} entries")
print(f"BLUE history: {len(blue.sg_history)} entries")
print(f"RED SG range: {min(red.sg_history):.4f} - {max(red.sg_history):.4f}")
print(f"BLUE SG range: {min(blue.sg_history):.4f} - {max(blue.sg_history):.4f}")
print("✅ Devices are isolated" if red.sg_history != blue.sg_history else "❌ CONTAMINATION")
EOF

source .venv/bin/activate
python test_multi_device.py
```

### Method 5: Check Database for Multi-Device Readings

```bash
cd /opt/brewsignal
source .venv/bin/activate

python << 'EOF'
import sqlite3
conn = sqlite3.connect('data/fermentation.db')
cursor = conn.cursor()

# Check recent readings by color
cursor.execute("""
    SELECT color, COUNT(*),
           MIN(specific_gravity), MAX(specific_gravity),
           MIN(temperature), MAX(temperature)
    FROM readings
    WHERE timestamp > datetime('now', '-1 hour')
    GROUP BY color
""")

print("Recent readings (last hour):")
print("-" * 60)
for row in cursor.fetchall():
    color, count, min_sg, max_sg, min_temp, max_temp = row
    print(f"{color:5s}: {count:4d} readings")
    print(f"       SG:   {min_sg:.4f} - {max_sg:.4f}")
    print(f"       Temp: {min_temp:.1f}°F - {max_temp:.1f}°F")
    print()

conn.close()
EOF
```

## Expected Behavior

### ✅ Good Signs

1. **Service Running**: `systemctl status brewsignal` shows "active (running)"
2. **Tilts Detected**: Logs show both RED and BLUE Tilt readings
3. **No Errors**: No Python tracebacks or IndexErrors
4. **Separate Histories**: Each device maintains different SG/temp ranges
5. **ML Import Success**: All numpy/scipy/filterpy modules load

### ❌ Warning Signs

1. **IndexError**: Indicates ambient_history crash (should be fixed)
2. **MissingGreenlet**: SQLAlchemy async issue (pre-existing, not ML-related)
3. **Import Errors**: Missing ML dependencies (run `pip install -e '.[dev]'`)
4. **State Contamination**: Devices showing mixed data (shouldn't happen with fix)

## Troubleshooting

### Problem: Service won't start

```bash
# Check logs
sudo journalctl -u brewsignal -n 100 --no-pager

# Verify Python environment
cd /opt/brewsignal
source .venv/bin/activate
python -c "import backend.main"
```

### Problem: ML dependencies missing

```bash
cd /opt/brewsignal
source .venv/bin/activate
pip install -e '.[dev]'
sudo systemctl restart brewsignal
```

### Problem: Can't see Tilts

```bash
# Check Bluetooth
sudo hciconfig hci0 up
sudo systemctl status bluetooth

# Check scanner mode
grep "SCANNER_" /opt/brewsignal/.env
```

## Validation Checklist

- [ ] Service is running (`systemctl status brewsignal`)
- [ ] Both Tilts detected in logs
- [ ] No IndexError or ambient_history crashes
- [ ] ML validation script passes
- [ ] Multi-device test shows isolation
- [ ] Database has readings for both colors
- [ ] No import errors in logs

## Performance Baseline

**Test Results** (as of commit 3e70f60):
```
✅ 48/48 ML tests passing (100%)
✅ Per-device isolation verified
✅ MPC ambient_history safety verified
✅ Service running on Pi without errors
✅ Both RED and BLUE Tilts detected
```

## Next Steps After Validation

1. Let the system run for 1-2 hours with live Tilts
2. Check for any anomalies or errors in logs
3. Verify database shows distinct readings per device
4. If all good: Create PR to merge to master

## Useful Commands Reference

```bash
# Deploy latest code
cd /opt/brewsignal
git fetch origin
git reset --hard origin/feature/ml-implementation
sudo systemctl restart brewsignal

# Watch logs live
sudo journalctl -u brewsignal -f

# Check service status
sudo systemctl status brewsignal

# Restart service
sudo systemctl restart brewsignal

# View recent errors only
sudo journalctl -u brewsignal -p err -n 50

# Check Python version
python --version  # Should be 3.13+
```
