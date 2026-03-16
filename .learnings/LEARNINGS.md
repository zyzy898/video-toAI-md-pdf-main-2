# Learnings`n
## [LRN-20260310-001] correction

**Logged**: 2026-03-10T00:00:00+08:00
**Priority**: high
**Status**: pending
**Area**: frontend

### Summary
When user asks to align only button positions and SVGs with Vue, avoid full-style migration.

### Details
I previously over-applied Vue styles and layout. User clarified to keep React background/color scheme and only align header copy, button positions, and SVG assets.

### Suggested Action
Before broad UI refactors, confirm the required scope and default to minimal-diff changes.

### Metadata
- Source: user_feedback
- Related Files: web-react/src/App.tsx, web-react/src/index.css
- Tags: scope_control, migration

---
## [LRN-20260316-001] best_practice

**Logged**: 2026-03-16T15:40:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: tests

### Summary
When testing chunk-upload flow, test data must respect server-side minimum chunk size constraints to avoid false regression signals.

### Details
In smoke tests, using `chunk_size=3` triggered an unexpected `400` on the second chunk. This was not a backend regression: `/upload_chunk_init` normalizes chunk size with a lower bound of `256 * 1024`, so `total_size=6` results in only one chunk. Sending `chunk_index=1` is therefore invalid by design.

### Suggested Action
For chunk-upload tests:
1. Read/align with backend bounds (`DEFAULT_UPLOAD_CHUNK_SIZE`, min `256KB`, max limit).
2. Use `total_size` and `chunk_size` values that actually produce the intended `total_chunks`.
3. Treat out-of-range chunk index failures as expected behavior unless bounds are met.

### Metadata
- Source: conversation
- Related Files: app.py
- Tags: chunk-upload, smoke-test, false-negative, backend

### Resolution
- **Resolved**: 2026-03-16T15:41:00+08:00
- **Commit/PR**: local_workspace_change
- **Notes**: Updated smoke test payload to use realistic chunk sizes and verified full chunk flow passed.

---

## [LRN-20260316-002] best_practice

**Logged**: 2026-03-16T15:42:00+08:00
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
For large OOP refactors, preserve compatibility by keeping old function interfaces and proving parity with automated structural checks.

### Details
The backend was refactored into service classes (`RiskBlocklistService`, `UploadSessionService`, `VideoProcessingService`, etc.) while keeping all existing route handlers and helper function names. Risk was controlled by:
- maintaining wrapper functions with original names/signatures,
- comparing old/new route sets and top-level function sets,
- comparing old/new function signatures via AST.
This reduced behavioral risk while improving maintainability.

### Suggested Action
During future architecture refactors:
1. Introduce class-based services behind compatibility wrappers.
2. Run route/function/signature parity checks against `HEAD`.
3. Add smoke tests for critical paths before and after refactor.

### Metadata
- Source: conversation
- Related Files: app.py
- Tags: refactor, oop, backward-compatibility, regression-prevention
- See Also: LRN-20260316-001

### Resolution
- **Resolved**: 2026-03-16T15:43:00+08:00
- **Commit/PR**: local_workspace_change
- **Notes**: Confirmed no route/function/signature loss and all key smoke endpoints passed.

---

## [LRN-20260315-001] best_practice

**Logged**: 2026-03-15T23:30:00+08:00
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
Prevent Chinese mojibake in source files by enforcing UTF-8 write/read flow and adding a post-edit encoding check.

### Details
Several user-facing strings in `app.py` became mojibake (for example `璇疯緭鍏?API Key`) after iterative edits. This typically happens when text is copied from a console/session using a different code page, or when file writes are not explicitly UTF-8. Because these strings are API error messages and logs, mojibake directly impacts usability and troubleshooting.

### Suggested Action
1. Always save edited markdown/text/code with UTF-8 explicitly (especially when using PowerShell file output commands).
2. Avoid copying localized terminal output directly into source strings.
3. After text-heavy edits, run a quick mojibake scan in touched files:
   - `rg -n "鍒|娌|璇|鏂|缂|瓒|鏈|杈撳|瑙嗛|鍐呭|涓嶆敮" app.py`
4. Run syntax validation after cleanup:
   - `python -m py_compile app.py`
5. If mojibake is found, replace by intent (based on endpoint behavior), not by blind conversion.

### Metadata
- Source: conversation
- Related Files: app.py, updata.md
- Tags: encoding, mojibake, utf8, backend, prevention

### Resolution
- **Resolved**: 2026-03-15T23:35:00+08:00
- **Commit/PR**: local_workspace_change
- **Notes**: Repaired mojibake in upload/analyze/test_model/batch error paths and standardized human-readable Chinese messages by functional context.

---
## [LRN-20260311-001] correction

**Logged**: 2026-03-11T00:00:00+08:00
**Priority**: high
**Status**: pending
**Area**: frontend

### Summary
If the user says they still cannot perceive button motion, avoid state-gated animation and make idle state visibly animated too.

### Details
I previously tied the strongest flow and pulse to `is-running` only, and the idle button effect was too subtle for the current full-width layout. User feedback indicated the motion was still not visible enough.

### Suggested Action
Use always-on base motion (idle flow + soft pulse), then layer a stronger running-state animation on top. Also tune NoiseBackground speed/noise for wide buttons.

### Metadata
- Source: user_feedback
- Related Files: web-react/src/App.tsx, web-react/src/index.css
- Tags: animation-visibility, ux, correction
- See Also: LRN-20260310-001

---
## [LRN-20260312-001] correction

**Logged**: 2026-03-12T00:00:00+08:00
**Priority**: high
**Status**: resolved
**Area**: frontend

### Summary
For bottom-center toast, avoid mixing X-axis centering transforms in both positioning classes and animation keyframes.

### Details
Initial fix switched to `left-1/2` + `-translate-x-1/2`, but the toast still appeared offset in this UI context. A more stable approach is to center with layout (`fixed inset-x-0` + `flex justify-center`) and keep toast animation on Y-axis only, so centering is never affected by transform composition.

### Suggested Action
Use a full-width fixed wrapper to center overlays, and ensure related keyframes do not include horizontal translate.

### Metadata
- Source: user_feedback
- Related Files: web-react/src/App.tsx, web-react/src/index.css
- Tags: toast, positioning, transform, correction
- See Also: LRN-20260311-001

### Resolution
- **Resolved**: 2026-03-12T00:00:00+08:00
- **Commit/PR**: local_workspace_change
- **Notes**: Wrapped toast in fixed full-width flex container and removed X-axis translate from `toastIn` keyframes.

---
## [LRN-20260312-002] correction

**Logged**: 2026-03-12T00:00:00+08:00
**Priority**: high
**Status**: resolved
**Area**: frontend

### Summary
When users report reveal animation stutter, prefer single-layer transform+opacity animation and remove stagger/scale effects.

### Details
The FPS field reveal used multi-step effects (scale and staggered child animations). Even after initial tuning, user feedback still reported non-smooth behavior. Simplifying to one short container animation reduced perceived jank.

### Suggested Action
For toggle reveal UI, start from minimal animation (single container fade/translate) and only add complexity if performance stays smooth.

### Metadata
- Source: user_feedback
- Related Files: web-react/src/index.css
- Tags: animation, performance, correction
- See Also: LRN-20260311-001, LRN-20260312-001

### Resolution
- **Resolved**: 2026-03-12T00:00:00+08:00
- **Commit/PR**: local_workspace_change
- **Notes**: Removed FPS child staggering and scale transform; kept only a short container fade+translate animation.

---
## [LRN-20260312-003] correction

**Logged**: 2026-03-12T00:00:00+08:00
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
For edited-step regenerate, prompt-only constraints are not sufficient; add output alignment checks and deterministic fallback.

### Details
User feedback showed step titles could update while generated document body still drifted from edited descriptions. The regenerate path already sent edited steps, but model output remained probabilistic. Relying on strict prompt text alone does not guarantee fidelity.

### Suggested Action
In strict regenerate mode, verify generated markdown includes edited step titles/descriptions. If not aligned, fallback to a deterministic markdown builder from user-edited steps.

### Metadata
- Source: user_feedback
- Related Files: app.py, video_analyzer_agent.py
- Tags: regenerate, prompt-robustness, fallback, correction
- See Also: LRN-20260312-001

### Resolution
- **Resolved**: 2026-03-12T00:00:00+08:00
- **Commit/PR**: local_workspace_change
- **Notes**: Added strict alignment validator and fallback markdown builder in `generate_step_document` when `respect_step_content=True`.

---
