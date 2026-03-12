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
