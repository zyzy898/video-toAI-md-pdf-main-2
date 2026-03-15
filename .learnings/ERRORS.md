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
