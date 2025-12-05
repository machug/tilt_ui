# ML Pipeline Integration - Implementation Handover

## Context

This worktree contains the implementation plan for **Task 8: ML Pipeline Integration** from the ML enhancements roadmap.

**Goal:** Integrate ML pipeline (Kalman filtering, anomaly detection, predictions) into production reading handler, standardize all temperatures to Celsius, and remove legacy smoothing service.

## What's Been Completed

✅ **Design Phase Complete:**
- Full design document: `docs/plans/2025-12-05-ml-pipeline-integration.md`
- Implementation plan: `docs/plans/2025-12-05-ml-pipeline-implementation-plan.md`
- Worktree created and dependencies installed
- Baseline tests passing (59 passed, 2 warnings)

✅ **Brainstorming Complete:**
- Approach selected: Per-device ML pipelines (Approach 1)
- Temperature strategy: Celsius everywhere, convert F→C at Tilt BLE boundary
- User confirmed: Breaking changes acceptable (single user app)
- Full database migration F→C approved

## Implementation Plan Overview

**11 Tasks:**
1. Database Schema Migration - Add ML Output Columns
2. Temperature Unit Migration - Convert F to C
3. MLPipelineManager Implementation
4. Helper Function - Calculate Time Since Batch Start
5. Update Reading Handler - Tilt F to C Conversion
6. Integrate ML Pipeline into Reading Handler
7. Remove Legacy Smoothing Service
8. Integration Testing
9. Update Pydantic Response Schemas
10. Documentation and Final Testing
11. Manual Testing on Development Machine

**Approach:** TDD with bite-sized steps (write test → verify fail → implement → verify pass → commit)

## Key Technical Decisions

**Temperature Units:**
- **Storage:** All temperatures in Celsius (readings, calibration_points)
- **Conversion:** F→C immediately at Tilt BLE boundary
- **Validation:** 0-100°C range (was 32-212°F)
- **Migration:** One-time F→C conversion of all existing data

**ML Integration:**
- **Architecture:** Per-device `MLPipeline` instances managed by `MLPipelineManager`
- **Components:** Kalman filter, anomaly detector, curve fitter (MPC deferred)
- **Error Handling:** Graceful degradation to calibrated values on ML failure
- **Storage:** New columns for ML outputs (sg_filtered, temp_filtered, confidence, etc.)

**Legacy Removal:**
- Remove `backend/services/smoothing.py` entirely
- Kalman filtering replaces moving average smoothing

## Current State

**Working directory:** `/home/ladmin/Projects/tilt_ui/.worktrees/feature/ml-integration`

**Branch:** `feature/ml-integration`

**Baseline test status:**
```
======================== 59 passed, 2 warnings in 1.58s ========================
```

**ML components available:**
- `backend/ml/pipeline.py` - MLPipeline orchestrator (complete)
- `backend/ml/sensor_fusion/kalman.py` - Kalman filter (complete)
- `backend/ml/anomaly/detector.py` - Anomaly detection (complete)
- `backend/ml/predictions/curve_fitter.py` - Fermentation predictions (complete)
- `backend/ml/config.py` - ML configuration (complete)

**Need to create:**
- `backend/ml/pipeline_manager.py` - Per-device pipeline manager
- Database migrations for ML columns and F→C conversion
- Integration with reading handler
- Tests for all new components

## Important Files to Review

**Implementation plan (start here):**
```
docs/plans/2025-12-05-ml-pipeline-implementation-plan.md
```

**Design document:**
```
docs/plans/2025-12-05-ml-pipeline-integration.md
```

**Current reading handler:**
```
backend/main.py:44-148 (handle_tilt_reading function)
```

**Reading model:**
```
backend/models.py:110-153
```

**ML pipeline (already implemented):**
```
backend/ml/pipeline.py
```

## How to Execute

### Option 1: Subagent-Driven Development (Recommended)

**Use the subagent-driven-development skill:**

```
I'm using the subagent-driven-development skill to implement the ML pipeline integration plan.
```

The skill will:
- Dispatch fresh subagent per task
- Review code between tasks
- Maintain quality gates
- Fast iteration with verification

### Option 2: Manual Execution

Work through tasks sequentially following TDD pattern:
1. Read task in implementation plan
2. Write test (verify it fails)
3. Implement minimal code
4. Verify test passes
5. Commit
6. Move to next task

## Testing Strategy

**Run tests frequently:**
```bash
# All tests
pytest -v

# Specific test file
pytest tests/test_ml_pipeline_manager.py -v

# With coverage
pytest --cov=backend --cov-report=term-missing
```

**Expected baseline:** 59 tests passing

**After implementation:** Should have 70+ tests passing (new ML tests added)

## Deployment Notes

**DO NOT deploy to Raspberry Pi until:**
- All tests passing
- Manual testing on dev machine complete
- Database migration tested on copy of production DB

**Temperature migration is BREAKING:**
- Existing data will be converted F→C
- Acceptable per user (single user app)
- Irreversible (backup recommended)

## Common Pitfalls to Avoid

1. **Don't skip tests** - TDD is critical for ML integration
2. **Temperature units** - Always use Celsius after conversion, never mix F/C
3. **Graceful degradation** - ML errors must not break core functionality
4. **Import errors** - Verify all imports after removing smoothing service
5. **Database migrations** - Test on fresh DB and existing DB

## Success Criteria

- [ ] All temperatures in Celsius (database, ML, internal processing)
- [ ] ML pipeline integrated with reading handler
- [ ] Kalman filtering active for all paired devices
- [ ] ML outputs stored in database
- [ ] WebSocket broadcasts include ML data
- [ ] Smoothing service removed
- [ ] All existing tests pass
- [ ] No performance regression (<50ms p99)

## Questions?

Refer to:
- Implementation plan for step-by-step guidance
- Design document for architecture decisions
- `CLAUDE.md` for project conventions
- Recent commits for context on ML work

---

**Ready to implement!** Start with Task 1 in the implementation plan and work through sequentially. Use TDD approach for all tasks.
