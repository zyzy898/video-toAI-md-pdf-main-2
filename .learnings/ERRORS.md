## [ERR-20260313-001] powershell-command-separator

**Logged**: 2026-03-13T21:20:00+08:00
**Priority**: low
**Status**: resolved
**Area**: docs

### Summary
Used `&&` in PowerShell command and caused parser error.

### Error
```text
标记“&&”不是此版本中的有效语句分隔符。
```

### Context
- Command attempted: `git status --short README.md && Get-Content -Raw README.md`
- Shell: PowerShell

### Suggested Fix
Run commands separately, or use `;` in PowerShell.

### Metadata
- Reproducible: yes
- Related Files: README.md

### Resolution
- **Resolved**: 2026-03-13T21:21:00+08:00
- **Commit/PR**: N/A
- **Notes**: Switched to separate commands for status check and file read.

---

## [ERR-20260316-001] python-ast-bom-parse

**Logged**: 2026-03-16T15:44:00+08:00
**Priority**: low
**Status**: resolved
**Area**: backend

### Summary
AST parsing failed on `app.py` due to UTF-8 BOM when reading source as plain `utf-8`.

### Error
```text
SyntaxError: invalid non-printable character U+FEFF
```

### Context
- Operation attempted: parse current and `HEAD` source with `ast.parse` for function/route parity checks.
- `app.py` contains BOM, and direct parse without stripping BOM failed.

### Suggested Fix
Read with `utf-8-sig` or strip `\ufeff` before AST parsing/compilation checks.

### Metadata
- Reproducible: yes
- Related Files: app.py

### Resolution
- **Resolved**: 2026-03-16T15:45:00+08:00
- **Commit/PR**: N/A
- **Notes**: Added BOM stripping helper in verification script and checks passed.

---

## [ERR-20260316-002] smoke-test-unmocked-timeout

**Logged**: 2026-03-16T15:46:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: tests

### Summary
A debug smoke test accidentally hit real risk-processing path, causing ffmpeg/subprocess side effects and command timeout.

### Error
```text
command timed out after 10237 milliseconds
```

### Context
- Operation attempted: inspect chunk-upload error details.
- Script did not mock risk-moderation path, which triggered screenshot extraction on non-video bytes and spawned noisy subprocess logs.

### Suggested Fix
For endpoint smoke tests, always monkeypatch external/model-heavy paths and keep request payloads deterministic.

### Metadata
- Reproducible: yes
- Related Files: app.py, video_analyzer_agent.py
- See Also: LRN-20260316-001

### Resolution
- **Resolved**: 2026-03-16T15:47:00+08:00
- **Commit/PR**: N/A
- **Notes**: Restored full mocks and reran smoke tests with all checkpoints passing.

---

## [ERR-20260315-001] model-api-authentication

**Logged**: 2026-03-15T15:10:00+08:00
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
Model provider returned HTTP 401 for an invalid API key, but the app surfaced raw upstream text that was hard to troubleshoot.

### Error
```text
Error code: 401 - {'error': {'message': 'Authentication Fails, Your api key: ****c7e6 is invalid', 'type': 'authentication_error', 'param': None, 'code': 'invalid_request_error'}}, request_id: 20260315144919iwxbhPnTR32i9QnMZdAZ
```

### Context
- Operation attempted: `/test_model` and analysis flows with provider credentials.
- Symptom: frontend showed raw provider error text; users could not quickly tell if the key/base_url combination was mismatched.

### Suggested Fix
Normalize provider exceptions into user-friendly Chinese errors, preserve `request_id`, and map authentication failures to HTTP 401.

### Metadata
- Reproducible: yes
- Related Files: app.py, web-react/src/App.tsx

### Resolution
- **Resolved**: 2026-03-15T15:35:00+08:00
- **Commit/PR**: local_workspace_change
- **Notes**: Added centralized error normalization in `app.py` and expanded frontend authentication keyword mapping.

---

## [ERR-20260313-002] rg-regex-escaping

**Logged**: 2026-03-13T23:18:00+08:00
**Priority**: low
**Status**: resolved
**Area**: frontend

### Summary
Used an over-complex `rg` regex with braces/quotes and triggered regex parse error.

### Error
```text
rg: regex parse error: unclosed group
```

### Context
- Command attempted: one-shot `rg` query containing `{`, `?`, quotes and alternation.
- Goal: verify newly added API key visibility code paths.

### Suggested Fix
Use multiple simple `rg` queries (or fixed-string `-F`) instead of a single complex regex.

### Metadata
- Reproducible: yes
- Related Files: web-react/src/App.tsx
- See Also: ERR-20260313-001

### Resolution
- **Resolved**: 2026-03-13T23:19:00+08:00
- **Commit/PR**: N/A
- **Notes**: Replaced with simple `rg` calls for each keyword.

---

## [ERR-20260314-001] powershell-command-separator

**Logged**: 2026-03-14T12:09:00+08:00
**Priority**: low
**Status**: resolved
**Area**: backend

### Summary
Used `&&` in PowerShell while chaining inspection commands, causing parser failure during implementation.

### Error
```text
ParserError: token '&&' is not a valid statement separator in this version.
```

### Context
- Command attempted: chained `rg ... && Get-Content ...` while tracing history routes in `app.py`.
- Shell: PowerShell.

### Suggested Fix
Use separate commands or `;` as separator when running in PowerShell.

### Metadata
- Reproducible: yes
- Related Files: app.py
- See Also: ERR-20260313-001

### Resolution
- **Resolved**: 2026-03-14T12:09:00+08:00
- **Commit/PR**: N/A
- **Notes**: Switched to `multi_tool_use.parallel` and separate commands.

---
