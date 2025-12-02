# Device Pairing Workflow

## Overview

As of v2.3.0, BrewSignal requires devices to be explicitly paired before logging readings to the database. This prevents unwanted data pollution from nearby Tilt devices that aren't actively being used for fermentation monitoring.

## How It Works

### Detection vs. Pairing

- **Detection**: BrewSignal continuously scans for Tilt devices via Bluetooth. All detected devices appear on the dashboard with live readings.
- **Pairing**: Only paired devices have their readings logged to the database and can be assigned to batches.

### Workflow

1. **New Device Detected**: When a Tilt is first detected, it's created in the database with `paired=False`
2. **Dashboard Display**: The device appears on the dashboard with an "Unpaired" badge
3. **Manual Pairing**: Navigate to `/devices` and click "Pair Device"
4. **Reading Storage**: Once paired, readings are stored in the database
5. **Batch Assignment**: Only paired devices can be selected when creating a new batch

## Managing Devices

### Pairing a Device

1. Navigate to **Devices** page
2. Find the device in the "Detected Devices" section
3. Click **Pair Device**
4. The device moves to "Paired Devices" and readings start logging

### Unpairing a Device

1. Navigate to **Devices** page
2. Find the device in the "Paired Devices" section
3. Click **Unpair Device**
4. Reading storage stops immediately (but device remains detected)

## API Endpoints

### Pair Device
```
POST /api/tilts/{tilt_id}/pair
```

### Unpair Device
```
POST /api/tilts/{tilt_id}/unpair
```

### List Devices
```
GET /api/tilts
GET /api/devices?paired_only=true
```

## Migration Notes

Existing installations will have all previously detected Tilts set to `paired=False` by default. You'll need to manually pair devices after upgrading to continue logging readings.
