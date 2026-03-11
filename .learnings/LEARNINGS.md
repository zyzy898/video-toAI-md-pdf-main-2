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
