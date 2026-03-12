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
