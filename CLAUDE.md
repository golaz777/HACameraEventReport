# CLAUDE.md

Guidance for AI assistants working in this repository.

## Project

Home Assistant add-on that monitors cameras for motion while away and
generates HTML reports with snapshots. Python (`aiohttp`) backend in
`camera_event_report/src/`, Jinja2 templates for the ingress web UI in
`camera_event_report/src/templates/`.

## Repository layout

This repo is a **Home Assistant add-on repository**: `repository.yaml` at the
root describes the repo, and the add-on itself lives in the
`camera_event_report/` subdirectory (its slug), which is the Docker build
context. `tests/` and `pyproject.toml` stay at the repo root; pytest imports
`src` via `pythonpath = ["camera_event_report"]`. Do not move the add-on back to
the root — the store requires this subdirectory layout.

## Web UI

- All page CSS is **inlined** in the templates (Home Assistant ingress-safe —
  nothing is served as a separate static asset; asset URLs must honour
  `X-Ingress-Path`). Do not introduce external CSS/JS files.
- `base.html.j2` holds the shared layout and the `:root` design-token system;
  all in-app pages `{% extends %}` it and most styling is token-driven.
- `report.html.j2` is a **standalone** file written to disk and viewed on its
  own, so it carries a self-contained copy of the theme tokens. Keep its
  palette in sync with `base.html.j2` when the theme changes.
- `_lightbox.html.j2` is a shared include; its chrome uses fixed light-on-dark
  colors (not theme tokens) because it sits over a dark photo backdrop.

## Releasing

The version lives in **one place**: `version:` in
`camera_event_report/config.yaml`. There is no Dockerfile label or `build.yaml`
to keep in sync. The root `repository.yaml` is static and carries **no
version**, so it never needs updating on a release.

To cut a release:

1. Bump `version:` in `camera_event_report/config.yaml` (semver — minor for
   features/visual changes, patch for fixes).
2. Add a matching `## [x.y.z] - YYYY-MM-DD` entry at the top of `CHANGELOG.md`.
3. Commit, then merge to `main` and push (only when the user asks).

### Updating the add-on in Home Assistant

Home Assistant caches the add-on store and will not see a version bump until
the cache is refreshed. After pushing:

- **Add-on Store → ⋮ → Check for updates**, then hard-refresh the browser, then
  click **Update** on the add-on page.
- **Use Update, never Rebuild.** Rebuild re-builds the currently installed
  version and causes the *"Local and store versions … differ, use Update
  instead of Rebuild"* error with a greyed-out Update button.
- If Update stays greyed out: `ha addons reload` (then `ha addons info
  camera_event_report`), or restart the Supervisor. Never uninstall/reinstall
  to update — it wipes the add-on configuration.

## Conventions

- Conventional Commits (`feat:`, `fix:`, `chore(release):`, `refactor:`, …).
- On the default branch, create a feature/release branch before committing.
- Commit or push only when explicitly asked.
