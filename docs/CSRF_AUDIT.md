# CSRF Audit — Pre-Refactor Forensic Baseline

## Classification

| METHOD | PATH | AUTH? | MUTATES? | CURRENT CSRF | RECOMMENDED CSRF |
|--------|------|-------|----------|--------------|-------------------|
| GET    | /login                  | no  | no  | n/a      | n/a |
| POST   | /login                  | no  | yes | REQUIRED  | REQUIRED (current OK) |
| POST   | /logout                 | yes | yes | REQUIRED  | REQUIRED (current OK) |
| GET    | /                       | no  | no  | n/a      | n/a |
| GET    | /players                | no  | no  | n/a      | n/a |
| GET    | /add_player             | yes | no  | n/a      | n/a |
| GET    | /game_stats             | no  | no  | n/a      | n/a |
| GET    | /add_game_record        | yes | no  | n/a      | n/a |
| GET    | /stats                  | no  | no  | n/a      | n/a |
| GET    | /matchup_stats          | no  | no  | n/a      | n/a |
| GET    | /pdf_viewer             | no  | no  | n/a      | n/a |
| GET    | /upload_pdf             | yes | no  | n/a      | n/a |
| GET    | /import_pdf             | no  | no  | n/a      | n/a |
| GET    | /api/players            | no  | no  | n/a      | n/a |
| POST   | /api/players            | yes | yes | **EXEMPT** ❌ | **REQUIRED** — high risk |
| GET    | /api/players/<id>       | no  | no  | n/a      | n/a |
| PUT    | /api/players/<id>       | yes | yes | **EXEMPT** ❌ | **REQUIRED** — high risk |
| DELETE | /api/players/<id>       | yes | yes | **EXEMPT** ❌ | **REQUIRED** — high risk |
| GET    | /api/players/batters    | no  | no  | n/a      | n/a |
| GET    | /api/players/pitchers   | no  | no  | n/a      | n/a |
| POST   | /api/game_records       | yes | yes | **EXEMPT** ❌ | **REQUIRED** — high risk |
| DELETE | /api/matchup/game_record/<id> | yes | yes | **EXEMPT** ❌ | **REQUIRED** — high risk |
| POST   | /api/pdf/import_all     | yes | yes | **EXEMPT** ❌ | **REQUIRED** — high risk |
| POST   | /api/pdf/import_one     | yes | yes | **EXEMPT** ❌ | **REQUIRED** — high risk |
| POST   | /api/pdf/upload         | yes | yes | **EXEMPT** ❌ | **REQUIRED** — high risk |
| POST   | /api/pdf/confirm_import | yes | yes | **EXEMPT** ❌ | **REQUIRED** — high risk |
| GET    | /api/stats/*            | no  | no  | n/a      | n/a |
| GET    | /api/matchup/*          | no  | no  | n/a      | n/a |
| GET    | /api/visualization/*    | no  | no  | n/a      | n/a |
| GET    | /api/export/csv         | no  | no  | n/a      | n/a |

## Findings

**Phase B's blanket `/api/*` exemption is unsafe.**

`@admin_required` verifies authentication (session cookie present and valid) but does NOT verify intent (that the request came from our app, not a malicious site). An attacker page like `<form action="https://baseball.app/api/players/X" method="POST">` would auto-submit with the admin's session cookie and bypass `@admin_required`.

All 8 mutation API endpoints are vulnerable.

## Remediation Plan (this phase)

1. Add `<meta name="csrf-token" content="{{ csrf_token() }}">` to `base.html`
2. Create `static/js/api.js` with `fetchJson(url, options)` that auto-attaches `X-CSRFToken` header from the meta tag for non-GET methods
3. Update frontend callers (currently inline `fetch()` in templates) to use `fetchJson`
4. Remove the blanket `before_request` CSRF exemption
6. Replace with **explicit** `@csrf.exempt` decorators ONLY on genuinely machine-to-machine endpoints (if any). Currently: none.

## What gets tested in Phase E0

- `POST /api/players` WITHOUT `X-CSRFToken` header → 400
- `POST /api/players` WITH valid `X-CSRFToken` header → flows to `@admin_required`
- All GET endpoints remain unaffected
- Login form (HTML POST) still requires CSRF token (regression test)