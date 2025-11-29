# BrewSignal Rebrand Design

**Status:** Approved
**Date:** 2025-12-01
**Scope:** Rename "Tilt UI" to "BrewSignal" with clean break - no backwards compatibility layer.

## Summary

Full rebrand from "Tilt UI" to "BrewSignal" with agnostic, descriptive naming for environment variables and paths. This is a clean break - existing users will need to update their configurations.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Backwards compat for env vars | No | Clean break simplifies codebase |
| Env var naming style | Agnostic with `SCANNER_` prefix | Future-proof, descriptive |
| Data paths | Agnostic names | `fermentation.db` describes domain, not product |
| Repo rename | Include in plan | Document as manual step |
| localStorage keys | Rename `tiltui_*` → `brewsignal_*` | Clean break, user prefs reset |
| Static assets in git | Remove from tracking | Build at deploy time, cleaner repo |
| Version baseline | 1.3.0 (VERSION file) | Fix pyproject.toml mismatch, bump to 2.0.0 |

## Environment Variables

**Clean rename, no aliasing:**

| Current | New |
|---------|-----|
| `TILT_MOCK=true` | `SCANNER_MOCK=true` |
| `TILT_FILES=/path` | `SCANNER_FILES_PATH=/path` |
| `TILT_RELAY=host` | `SCANNER_RELAY_HOST=host` |

**Location:** `backend/scanner.py`

## User-Facing Branding

| Location | File | Current | New |
|----------|------|---------|-----|
| FastAPI app title | `backend/main.py` | "Tilt UI" | "BrewSignal" |
| Browser tab title | `frontend/src/routes/+layout.svelte` | "Tilt UI" | "BrewSignal" |
| Page titles | `+page.svelte`, `logging/`, `calibration/`, `system/` | "X \| Tilt UI" | "X \| BrewSignal" |
| Nav logo | `frontend/src/routes/+layout.svelte` | "Tilt**UI**" | "Brew**Signal**" |
| README title | `README.md` | "# Tilt UI" | "# BrewSignal" |
| Package name | `pyproject.toml` | "tilt-ui" | "brewsignal" |
| Changelog | `CHANGELOG.md` | "Tilt UI" | "BrewSignal" |
| Handover doc | `HANDOVER.md` | "Tilt UI" | "BrewSignal" |

## localStorage Keys

| Current | New |
|---------|-----|
| `tiltui_alerts_dismissed` | `brewsignal_alerts_dismissed` |
| `tiltui_alerts_dismissed_time` | `brewsignal_alerts_dismissed_time` |
| `tiltui_chart_refresh_minutes` | `brewsignal_chart_refresh_minutes` |

**Note:** User preferences will reset after upgrade.

## Data & Paths

| Item | Current | New |
|------|---------|-----|
| SQLite database | `data/tiltui.db` | `data/fermentation.db` |
| Systemd service | `deploy/tiltui.service` | `deploy/brewsignal.service` |
| Install directory | `/opt/tiltui` | `/opt/brewsignal` |
| Static assets | Tracked in git | Build at deploy time |

## Repo Rename (Manual Step)

1. Rename GitHub repo from `tilt_ui` to `brewsignal`
2. Update local git remote: `git remote set-url origin <new-url>`
3. GitHub auto-redirects old URLs

## Files to Modify

### Backend
- `backend/scanner.py` - env var names, docstring
- `backend/main.py` - FastAPI title, startup messages
- `backend/database.py` - database filename

### Frontend
- `frontend/src/routes/+layout.svelte` - title, nav logo
- `frontend/src/routes/+page.svelte` - page title, localStorage keys
- `frontend/src/routes/logging/+page.svelte` - page title
- `frontend/src/routes/calibration/+page.svelte` - page title
- `frontend/src/routes/system/+page.svelte` - page title
- `frontend/src/lib/components/TiltChart.svelte` - localStorage key
- `frontend/src/lib/api.ts` - comment

### Docs & Config
- `README.md` - title, description, env var docs, all references
- `CHANGELOG.md` - header, add 2.0.0 entry
- `HANDOVER.md` - title, paths, env vars
- `pyproject.toml` - package name, description, version
- `VERSION` - bump to 2.0.0
- `.gitignore` - add `backend/static/`

### Deploy
- `deploy/tiltui.service` → `deploy/brewsignal.service`
- `deploy/install.sh` - all references

## What NOT to Rename

- Internal code names: `tilt_id`, `TiltReading`, `TiltScanner`, `TiltCard` - these refer to the Tilt *device type*, not the product
- Historical plan docs in `docs/plans/` - they document what was done at the time
- `TILTPI_REVERSE_ENGINEERING.md` - about the TiltPi hardware

## Testing

1. Run backend tests (114 tests)
2. Build frontend
3. Verify env vars work with new names
4. Verify API title shows "BrewSignal"
5. Grep for remaining "Tilt UI" strings

## Migration Notes for Users

```
## Breaking Changes - v2.0.0

This release renames the project from "Tilt UI" to "BrewSignal".

### Environment Variables
- `TILT_MOCK` → `SCANNER_MOCK`
- `TILT_FILES` → `SCANNER_FILES_PATH`
- `TILT_RELAY` → `SCANNER_RELAY_HOST`

### Database
- Rename: `mv data/tiltui.db data/fermentation.db`

### Systemd Service
1. `sudo systemctl stop tiltui`
2. `sudo cp deploy/brewsignal.service /etc/systemd/system/`
3. `sudo systemctl daemon-reload`
4. `sudo systemctl enable brewsignal`
5. `sudo systemctl start brewsignal`

### User Preferences
Chart refresh rate and dismissed alerts will reset.
```
