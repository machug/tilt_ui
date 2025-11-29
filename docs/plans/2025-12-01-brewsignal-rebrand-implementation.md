# BrewSignal Rebrand Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rename "Tilt UI" to "BrewSignal" with agnostic env vars and paths.

**Architecture:** Clean break rebrand - no backwards compatibility. Rename all user-facing strings, env vars (`TILT_*` → `SCANNER_*`), localStorage keys (`tiltui_*` → `brewsignal_*`), and data paths. Internal module/variable names (like `tilt_id`, `TiltReading`) unchanged - those refer to the device type, not the product.

**Tech Stack:** Python/FastAPI backend, SvelteKit frontend, SQLite database.

**Pre-rebrand version:** 1.3.0 (VERSION file is authoritative, pyproject.toml must be synced)

---

## Task 1: Sync pyproject.toml Version to 1.3.0

**Files:**
- Modify: `pyproject.toml:3`

**Step 1: Fix version mismatch**

Change line 3 from:
```toml
version = "1.0.0"
```
To:
```toml
version = "1.3.0"
```

**Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "fix: sync pyproject.toml version to 1.3.0 (matches VERSION file)"
```

---

## Task 2: Remove backend/static/ from Git Tracking

**Files:**
- Modify: `.gitignore`
- Remove from tracking: `backend/static/`

**Step 1: Add to .gitignore**

Add these lines to `.gitignore`:
```
# Built frontend assets (rebuild with: cd frontend && npm run build)
backend/static/
```

**Step 2: Remove from git tracking (keep files locally)**

```bash
git rm -r --cached backend/static/
```

**Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: stop tracking backend/static/, rebuild at deploy time

Frontend assets should be built fresh during deployment rather than
committed to the repository. Build with: cd frontend && npm run build"
```

---

## Task 3: Rename Environment Variables in Scanner

**Files:**
- Modify: `backend/scanner.py:1-9` (docstring)
- Modify: `backend/scanner.py:277-294` (env var reads)

**Step 1: Update the docstring**

Change lines 1-9 from:
```python
"""
BLE Scanner for Tilt Hydrometers.

Supports four modes:
1. Mock mode (TILT_MOCK=true): Generates fake readings for development
2. File mode (TILT_FILES=<path>): Reads from local TiltPi JSON files
3. Relay mode (TILT_RELAY=<ip>): Fetches from remote TiltPi
4. Real mode: Scans BLE for actual Tilt devices
"""
```

To:
```python
"""
BLE Scanner for Tilt Hydrometers.

Supports four modes:
1. Mock mode (SCANNER_MOCK=true): Generates fake readings for development
2. File mode (SCANNER_FILES_PATH=<path>): Reads from local TiltPi JSON files
3. Relay mode (SCANNER_RELAY_HOST=<ip>): Fetches from remote TiltPi
4. Real mode: Scans BLE for actual Tilt devices
"""
```

**Step 2: Update env var reads**

Change lines 277-289 from:
```python
        if os.environ.get("TILT_MOCK", "").lower() in ("true", "1", "yes"):
            logger.info("Scanner mode: MOCK")
            self._scanner = MockScanner()
            self._interval = 5.0  # Mock every 5 seconds
        elif files_path := os.environ.get("TILT_FILES"):
            # File mode: read from local TiltPi JSON files
            logger.info("Scanner mode: FILES (%s)", files_path)
            self._scanner = FileScanner(files_path)
            self._interval = 5.0  # Check files every 5 seconds
        elif relay_host := os.environ.get("TILT_RELAY"):
            logger.info("Scanner mode: RELAY (%s)", relay_host)
            self._scanner = RelayScanner(relay_host)
            self._interval = 5.0
```

To:
```python
        if os.environ.get("SCANNER_MOCK", "").lower() in ("true", "1", "yes"):
            logger.info("Scanner mode: MOCK")
            self._scanner = MockScanner()
            self._interval = 5.0  # Mock every 5 seconds
        elif files_path := os.environ.get("SCANNER_FILES_PATH"):
            # File mode: read from local TiltPi JSON files
            logger.info("Scanner mode: FILES (%s)", files_path)
            self._scanner = FileScanner(files_path)
            self._interval = 5.0  # Check files every 5 seconds
        elif relay_host := os.environ.get("SCANNER_RELAY_HOST"):
            logger.info("Scanner mode: RELAY (%s)", relay_host)
            self._scanner = RelayScanner(relay_host)
            self._interval = 5.0
```

**Step 3: Run tests**

```bash
uv run pytest backend/tests/ -q
```

Expected: 114 passed

**Step 4: Commit**

```bash
git add backend/scanner.py
git commit -m "refactor: rename TILT_* env vars to SCANNER_*

- TILT_MOCK → SCANNER_MOCK
- TILT_FILES → SCANNER_FILES_PATH
- TILT_RELAY → SCANNER_RELAY_HOST

BREAKING CHANGE: Environment variable names changed"
```

---

## Task 4: Rename Database Path

**Files:**
- Modify: `backend/database.py:10`

**Step 1: Update database filename**

Change line 10 from:
```python
DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR}/tiltui.db"
```

To:
```python
DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR}/fermentation.db"
```

**Step 2: Run tests**

```bash
uv run pytest backend/tests/ -q
```

Expected: 114 passed (tests use in-memory DB)

**Step 3: Commit**

```bash
git add backend/database.py
git commit -m "refactor: rename database from tiltui.db to fermentation.db

BREAKING CHANGE: Existing users must rename/move their database file"
```

---

## Task 5: Update FastAPI App Title and Startup Messages

**Files:**
- Modify: `backend/main.py:94,118,135`

**Step 1: Update app title and messages**

Change line 94 from:
```python
    print("Starting Tilt UI...")
```
To:
```python
    print("Starting BrewSignal...")
```

Change line 118 from:
```python
    print("Shutting down Tilt UI...")
```
To:
```python
    print("Shutting down BrewSignal...")
```

Change line 135 from:
```python
app = FastAPI(title="Tilt UI", version=VERSION, lifespan=lifespan)
```
To:
```python
app = FastAPI(title="BrewSignal", version=VERSION, lifespan=lifespan)
```

**Step 2: Run tests**

```bash
uv run pytest backend/tests/ -q
```

Expected: 114 passed

**Step 3: Commit**

```bash
git add backend/main.py
git commit -m "refactor: rename FastAPI app title to BrewSignal"
```

---

## Task 6: Update Frontend Layout Branding

**Files:**
- Modify: `frontend/src/routes/+layout.svelte:75,95-96`

**Step 1: Update page title**

Change line 75 from:
```svelte
	<title>Tilt UI</title>
```
To:
```svelte
	<title>BrewSignal</title>
```

**Step 2: Update nav logo**

Change lines 95-96 from:
```svelte
				<span class="text-lg font-semibold tracking-tight" style="color: var(--text-primary);">
					Tilt<span style="color: var(--accent);">UI</span>
				</span>
```
To:
```svelte
				<span class="text-lg font-semibold tracking-tight" style="color: var(--text-primary);">
					Brew<span style="color: var(--accent);">Signal</span>
				</span>
```

**Step 3: Commit**

```bash
git add frontend/src/routes/+layout.svelte
git commit -m "refactor: rename layout branding to BrewSignal"
```

---

## Task 7: Update Frontend Page Titles

**Files:**
- Modify: `frontend/src/routes/+page.svelte:49`
- Modify: `frontend/src/routes/logging/+page.svelte:80`
- Modify: `frontend/src/routes/calibration/+page.svelte:163`
- Modify: `frontend/src/routes/system/+page.svelte:481`

**Step 1: Update dashboard page title**

In `frontend/src/routes/+page.svelte`, change line 49 from:
```svelte
	<title>Dashboard | Tilt UI</title>
```
To:
```svelte
	<title>Dashboard | BrewSignal</title>
```

**Step 2: Update logging page title**

In `frontend/src/routes/logging/+page.svelte`, change line 80 from:
```svelte
	<title>Logging | Tilt UI</title>
```
To:
```svelte
	<title>Logging | BrewSignal</title>
```

**Step 3: Update calibration page title**

In `frontend/src/routes/calibration/+page.svelte`, change line 163 from:
```svelte
	<title>Calibration | Tilt UI</title>
```
To:
```svelte
	<title>Calibration | BrewSignal</title>
```

**Step 4: Update system page title**

In `frontend/src/routes/system/+page.svelte`, change line 481 from:
```svelte
	<title>System | Tilt UI</title>
```
To:
```svelte
	<title>System | BrewSignal</title>
```

**Step 5: Commit**

```bash
git add frontend/src/routes/+page.svelte frontend/src/routes/logging/+page.svelte frontend/src/routes/calibration/+page.svelte frontend/src/routes/system/+page.svelte
git commit -m "refactor: rename all page titles to BrewSignal"
```

---

## Task 8: Rename localStorage Keys

**Files:**
- Modify: `frontend/src/routes/+page.svelte:12-13,39-40`
- Modify: `frontend/src/lib/components/TiltChart.svelte:14`

**Step 1: Update dashboard localStorage keys**

In `frontend/src/routes/+page.svelte`, change lines 12-13 from:
```typescript
		const dismissed = localStorage.getItem('tiltui_alerts_dismissed');
		const dismissedTime = localStorage.getItem('tiltui_alerts_dismissed_time');
```
To:
```typescript
		const dismissed = localStorage.getItem('brewsignal_alerts_dismissed');
		const dismissedTime = localStorage.getItem('brewsignal_alerts_dismissed_time');
```

Change lines 39-40 from:
```typescript
		localStorage.setItem('tiltui_alerts_dismissed', 'true');
		localStorage.setItem('tiltui_alerts_dismissed_time', Date.now().toString());
```
To:
```typescript
		localStorage.setItem('brewsignal_alerts_dismissed', 'true');
		localStorage.setItem('brewsignal_alerts_dismissed_time', Date.now().toString());
```

**Step 2: Update chart localStorage key**

In `frontend/src/lib/components/TiltChart.svelte`, change line 14 from:
```typescript
	const REFRESH_STORAGE_KEY = 'tiltui_chart_refresh_minutes';
```
To:
```typescript
	const REFRESH_STORAGE_KEY = 'brewsignal_chart_refresh_minutes';
```

**Step 3: Commit**

```bash
git add frontend/src/routes/+page.svelte frontend/src/lib/components/TiltChart.svelte
git commit -m "refactor: rename localStorage keys from tiltui_* to brewsignal_*

BREAKING CHANGE: User preferences (chart refresh, alert dismissals) will reset"
```

---

## Task 9: Update API Comment

**Files:**
- Modify: `frontend/src/lib/api.ts:1`

**Step 1: Update comment**

Change line 1 from:
```typescript
// API helper functions for Tilt UI
```
To:
```typescript
// API helper functions for BrewSignal
```

**Step 2: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "docs: update api.ts comment to BrewSignal"
```

---

## Task 10: Build Frontend

**Step 1: Install dependencies and build**

```bash
cd frontend && npm install && npm run build && cd ..
```

Expected: Build completes successfully, outputs to `backend/static/`

**Step 2: Verify build output exists**

```bash
ls backend/static/index.html
```

Expected: File exists

---

## Task 11: Update pyproject.toml Metadata

**Files:**
- Modify: `pyproject.toml:2,4`

**Step 1: Update package metadata**

Change line 2 from:
```toml
name = "tilt-ui"
```
To:
```toml
name = "brewsignal"
```

Change line 4 from:
```toml
description = "Modern web UI for Tilt Hydrometer monitoring"
```
To:
```toml
description = "Modern web UI for fermentation hydrometer monitoring"
```

**Step 2: Sync dependencies**

```bash
uv sync
```

Expected: Completes without error

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "refactor: rename package from tilt-ui to brewsignal"
```

---

## Task 12: Bump VERSION to 2.0.0

**Files:**
- Modify: `VERSION`
- Modify: `pyproject.toml:3`

**Step 1: Update VERSION file**

Change content from:
```
1.3.0
```
To:
```
2.0.0
```

**Step 2: Update pyproject.toml version**

Change line 3 from:
```toml
version = "1.3.0"
```
To:
```toml
version = "2.0.0"
```

**Step 3: Commit**

```bash
git add VERSION pyproject.toml
git commit -m "chore: bump version to 2.0.0 for rebrand release"
```

---

## Task 13: Update README.md

**Files:**
- Modify: `README.md`

**Step 1: Update title (line 1)**

Change from:
```markdown
# Tilt UI
```
To:
```markdown
# BrewSignal
```

**Step 2: Update description (line 3)**

Change from:
```markdown
A modern web interface for monitoring fermentation hydrometers on Raspberry Pi. Supports Tilt, iSpindel, and GravityMon devices.
```
To:
```markdown
A modern web interface for monitoring fermentation hydrometers on Raspberry Pi. Supports Tilt, iSpindel, and GravityMon devices. *(Formerly Tilt UI)*
```

**Step 3: Update git clone (lines 32-34)**

Change from:
```markdown
git clone https://github.com/machug/tilt_ui.git
cd tilt_ui
```
To:
```markdown
git clone https://github.com/machug/brewsignal.git
cd brewsignal
```

**Step 4: Update systemd references (lines 50-56)**

Change from:
```markdown
sudo cp deploy/tiltui.service /etc/systemd/system/
...
sudo systemctl enable tiltui
sudo systemctl start tiltui
```
To:
```markdown
sudo cp deploy/brewsignal.service /etc/systemd/system/
...
sudo systemctl enable brewsignal
sudo systemctl start brewsignal
```

**Step 5: Update environment variables table (lines 63-67)**

Change from:
```markdown
| `TILT_MOCK` | Enable mock scanner for development | `false` |
| `TILT_FILES` | Path to TiltPi JSON files (legacy mode) | - |
| `TILT_RELAY` | IP of remote TiltPi to relay from | - |
```
To:
```markdown
| `SCANNER_MOCK` | Enable mock scanner for development | `false` |
| `SCANNER_FILES_PATH` | Path to TiltPi JSON files (legacy mode) | - |
| `SCANNER_RELAY_HOST` | IP of remote TiltPi to relay from | - |
```

**Step 6: Update scanner modes (lines 71-74)**

Change from:
```markdown
2. **Mock Mode** - Simulated readings for development (`TILT_MOCK=true`)
3. **File Mode** - Read from TiltPi JSON files (`TILT_FILES=/home/pi`)
4. **Relay Mode** - Fetch from remote TiltPi (`TILT_RELAY=192.168.1.100`)
```
To:
```markdown
2. **Mock Mode** - Simulated readings for development (`SCANNER_MOCK=true`)
3. **File Mode** - Read from TiltPi JSON files (`SCANNER_FILES_PATH=/home/pi`)
4. **Relay Mode** - Fetch from remote TiltPi (`SCANNER_RELAY_HOST=192.168.1.100`)
```

**Step 7: Update calibration reference (line 114)**

Change from:
```markdown
2. Note the raw value shown in Tilt UI
```
To:
```markdown
2. Note the raw value shown in BrewSignal
```

**Step 8: Update dev instructions (line 122)**

Change from:
```markdown
cd tilt_ui
```
To:
```markdown
cd brewsignal
```

**Step 9: Commit**

```bash
git add README.md
git commit -m "docs: rebrand README to BrewSignal"
```

---

## Task 14: Update CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Update header (line 3)**

Change from:
```markdown
All notable changes to Tilt UI will be documented in this file.
```
To:
```markdown
All notable changes to BrewSignal (formerly Tilt UI) will be documented in this file.
```

**Step 2: Add 2.0.0 entry after line 6**

Insert after line 6:
```markdown

## [2.0.0] - 2025-12-01

### Changed
- **Project Renamed** - "Tilt UI" is now "BrewSignal"
- Environment variables renamed to agnostic names:
  - `TILT_MOCK` → `SCANNER_MOCK`
  - `TILT_FILES` → `SCANNER_FILES_PATH`
  - `TILT_RELAY` → `SCANNER_RELAY_HOST`
- Database file renamed from `tiltui.db` to `fermentation.db`
- Systemd service renamed from `tiltui` to `brewsignal`
- localStorage keys renamed from `tiltui_*` to `brewsignal_*`
- Frontend assets no longer tracked in git (build at deploy time)

### Migration Guide
1. Rename database: `mv data/tiltui.db data/fermentation.db`
2. Update environment variables in your config/service file
3. If using systemd:
   - `sudo systemctl stop tiltui`
   - `sudo cp deploy/brewsignal.service /etc/systemd/system/`
   - `sudo systemctl daemon-reload`
   - `sudo systemctl enable brewsignal`
   - `sudo systemctl start brewsignal`
4. User preferences (chart refresh rate, dismissed alerts) will reset

```

**Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add 2.0.0 rebrand changelog entry"
```

---

## Task 15: Update HANDOVER.md

**Files:**
- Modify: `HANDOVER.md`

**Step 1: Update title (line 1)**

Change from:
```markdown
# Tilt UI Project Handover
```
To:
```markdown
# BrewSignal Project Handover
```

**Step 2: Update path reference (line 6)**

Change from:
```markdown
cd /home/ladmin/Projects/tilt_ui
```
To:
```markdown
cd /home/ladmin/Projects/brewsignal
```

**Step 3: Update env vars (lines 53-54)**

Change from:
```markdown
1. `TILT_MOCK=true` - Fake data (default for dev)
2. `TILT_RELAY=192.168.4.117` - Fetch from remote TiltPi
```
To:
```markdown
1. `SCANNER_MOCK=true` - Fake data (default for dev)
2. `SCANNER_RELAY_HOST=192.168.4.117` - Fetch from remote TiltPi
```

**Step 4: Update directory tree reference (line 60)**

Change from:
```markdown
tilt_ui/
```
To:
```markdown
brewsignal/
```

**Step 5: Commit**

```bash
git add HANDOVER.md
git commit -m "docs: rebrand HANDOVER.md to BrewSignal"
```

---

## Task 16: Rename and Update Systemd Service

**Files:**
- Rename: `deploy/tiltui.service` → `deploy/brewsignal.service`

**Step 1: Rename service file**

```bash
git mv deploy/tiltui.service deploy/brewsignal.service
```

**Step 2: Update service file contents**

Replace entire file with:
```ini
[Unit]
Description=BrewSignal - Beer Fermentation Dashboard
After=network.target bluetooth.target
Wants=bluetooth.target

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=/opt/brewsignal
Environment="PATH=/opt/brewsignal/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/opt/brewsignal/venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=5

# Security hardening
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/opt/brewsignal/data
PrivateTmp=true

# Bluetooth access
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_RAW

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=brewsignal

[Install]
WantedBy=multi-user.target
```

**Step 3: Commit**

```bash
git add deploy/brewsignal.service
git commit -m "refactor: rename systemd service to brewsignal"
```

---

## Task 17: Update Install Script

**Files:**
- Modify: `deploy/install.sh`

**Step 1: Update header (lines 1-3)**

Change from:
```bash
#!/bin/bash
# Tilt UI Installation Script
# Installs Tilt UI as a systemd service on Raspberry Pi
```
To:
```bash
#!/bin/bash
# BrewSignal Installation Script
# Installs BrewSignal as a systemd service on Raspberry Pi
```

**Step 2: Update variables (lines 13-15)**

Change from:
```bash
INSTALL_DIR="/opt/tiltui"
SERVICE_FILE="/etc/systemd/system/tiltui.service"
REPO_URL="https://github.com/yourusername/tilt_ui.git"
```
To:
```bash
INSTALL_DIR="/opt/brewsignal"
SERVICE_FILE="/etc/systemd/system/brewsignal.service"
REPO_URL="https://github.com/machug/brewsignal.git"
```

**Step 3: Update banner (line 18)**

Change from:
```bash
echo -e "${GREEN}  Tilt UI Installation Script${NC}"
```
To:
```bash
echo -e "${GREEN}  BrewSignal Installation Script${NC}"
```

**Step 4: Update service stop check (lines 55-57)**

Change from:
```bash
if systemctl is-active --quiet tiltui; then
    echo -e "\n${YELLOW}Stopping existing Tilt UI service...${NC}"
    systemctl stop tiltui
```
To:
```bash
if systemctl is-active --quiet brewsignal; then
    echo -e "\n${YELLOW}Stopping existing BrewSignal service...${NC}"
    systemctl stop brewsignal
```

**Step 5: Update service file copy (line 123)**

Change from:
```bash
cp "$SCRIPT_DIR/tiltui.service" "$SERVICE_FILE"
```
To:
```bash
cp "$SCRIPT_DIR/brewsignal.service" "$SERVICE_FILE"
```

**Step 6: Update service enable/start (lines 125-126)**

Change from:
```bash
systemctl enable tiltui
systemctl start tiltui
```
To:
```bash
systemctl enable brewsignal
systemctl start brewsignal
```

**Step 7: Update verification and output (lines 130-145)**

Change all `tiltui` references to `brewsignal` and update the success message:
```bash
if systemctl is-active --quiet brewsignal; then
    ...
    echo -e "BrewSignal is now running at: ${GREEN}http://$(hostname -I | awk '{print $1}'):8080${NC}"
    ...
    echo "  - View logs:    journalctl -u brewsignal -f"
    echo "  - Restart:      sudo systemctl restart brewsignal"
    echo "  - Stop:         sudo systemctl stop brewsignal"
    echo "  - Status:       sudo systemctl status brewsignal"
else
    echo -e "\n${RED}Service failed to start. Check logs:${NC}"
    echo "  journalctl -u brewsignal -n 50"
```

**Step 8: Commit**

```bash
git add deploy/install.sh
git commit -m "refactor: rebrand install script to BrewSignal"
```

---

## Task 18: Final Test and Verification

**Step 1: Run full test suite**

```bash
uv run pytest backend/tests/ -v
```

Expected: 114 passed

**Step 2: Build frontend fresh**

```bash
cd frontend && npm run build && cd ..
```

Expected: Build succeeds

**Step 3: Start server with mock mode**

```bash
SCANNER_MOCK=true uv run uvicorn backend.main:app --host 0.0.0.0 --port 8080 &
sleep 3
```

**Step 4: Verify API title**

```bash
curl -s http://localhost:8080/openapi.json | grep -o '"title":"[^"]*"'
```

Expected: `"title":"BrewSignal"`

**Step 5: Verify health endpoint**

```bash
curl -s http://localhost:8080/api/health
```

Expected: `{"status":"ok"}`

**Step 6: Stop server**

```bash
pkill -f uvicorn
```

**Step 7: Verify no remaining "Tilt UI" in user-facing code**

```bash
grep -r "Tilt UI" frontend/src backend/*.py README.md CHANGELOG.md HANDOVER.md deploy/ --include="*.py" --include="*.svelte" --include="*.ts" --include="*.md" --include="*.sh" --include="*.service" | grep -v "Formerly Tilt UI" | grep -v "formerly Tilt UI"
```

Expected: No output (or only historical plan docs)

---

## Summary

| Task | Description | Files Changed |
|------|-------------|---------------|
| 1 | Sync pyproject.toml version | `pyproject.toml` |
| 2 | Remove static/ from git | `.gitignore`, `backend/static/` |
| 3 | Rename env vars | `backend/scanner.py` |
| 4 | Rename database | `backend/database.py` |
| 5 | Update FastAPI title | `backend/main.py` |
| 6 | Update layout branding | `frontend/src/routes/+layout.svelte` |
| 7 | Update page titles | 4 page files |
| 8 | Rename localStorage keys | `+page.svelte`, `TiltChart.svelte` |
| 9 | Update API comment | `frontend/src/lib/api.ts` |
| 10 | Build frontend | (build only) |
| 11 | Update pyproject.toml name | `pyproject.toml` |
| 12 | Bump to 2.0.0 | `VERSION`, `pyproject.toml` |
| 13 | Update README | `README.md` |
| 14 | Update CHANGELOG | `CHANGELOG.md` |
| 15 | Update HANDOVER | `HANDOVER.md` |
| 16 | Rename service file | `deploy/brewsignal.service` |
| 17 | Update install script | `deploy/install.sh` |
| 18 | Final verification | (tests only) |

## Notes

- Internal code names like `tilt_id`, `TiltReading`, `TiltScanner` are **not renamed** - they refer to the Tilt device type, not the product name
- Historical plan docs in `docs/plans/` are not updated - they document what was done at the time
- The `TILTPI_REVERSE_ENGINEERING.md` file is not renamed - it's about the TiltPi hardware, not our product
