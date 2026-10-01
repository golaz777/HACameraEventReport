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

## Human detection

`src/detector.py` analyses a completed session's snapshots with a bundled SSD
MobileNet V1 ONNX model (`camera_event_report/models/ssd_mobilenet_v1_12.onnx`,
copied into the image by the Dockerfile). Key constraints:

- `onnxruntime` is an **optional** dependency — it has no wheels for the
  `armhf`/`armv7`/`i386` architectures declared in `config.yaml`, so the
  Dockerfile installs it in a non-fatal step and `HumanDetector` degrades to
  `available = False` on ImportError. Never make it a hard requirement in
  `requirements.txt`.
- `MotionEvent.human_detected` is **tri-state**: `None` means not analysed,
  `False` means analysed with nobody there. Do not collapse them.
- The model takes **raw uint8 NHWC** pixels (it resizes internally — do not
  normalise or letterbox) and its outputs must be requested **by name**;
  positional order is not boxes/classes/scores/num. COCO class ids are
  1-based, so person is `1`. See `NOTICE` for the full interface.
- `report.py`'s `_EVENT_COUNT_RE` / `_HUMAN_COUNT_RE` parse counts back out of
  saved report HTML. Changing the summary block in `report.html.j2` breaks the
  Reports page; there are regression tests for this in `tests/test_report.py`.

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

## Add-on presentation files

Home Assistant reads these from the **add-on directory**, next to `config.yaml`
— never from the repo root (same trap as the changelog):

- `DOCS.md` — the Documentation tab. Documents every option in `config.yaml`'s
  `schema:`; when you add an option, add it here too.
- `README.md` — the short store blurb. The repo-root `README.md` is the GitHub
  landing page and is a **separate file with overlapping content** — if you
  change the option reference or feature list, check whether both need it.
- `icon.png` — 128x128, square.
- `logo.png` — 250x100. Both use a solid brand panel so they stay legible on
  light and dark HA themes.

## Releasing

The version lives in **one place**: `version:` in
`camera_event_report/config.yaml`. There is no Dockerfile label or `build.yaml`
to keep in sync. The root `repository.yaml` is static and carries **no
version**, so it never needs updating on a release.

To cut a release:

1. Bump `version:` in `camera_event_report/config.yaml` (semver — minor for
   features/visual changes, patch for fixes).
2. Add a matching `## [x.y.z] - YYYY-MM-DD` entry at the top of
   **`camera_event_report/CHANGELOG.md`**. It must live in the add-on
   directory, next to `config.yaml` — that is where the Supervisor reads it
   from, and it is what Home Assistant shows for the add-on. A changelog at
   the repo root is invisible to HA; the root `CHANGELOG.md` is only a pointer
   stub.
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

- Run tests with `python -m pytest --force-enable-socket`. A globally installed
  `pytest_homeassistant_custom_component` plugin blocks sockets and makes the
  aiohttp tests in `test_web.py` fail spuriously without that flag.
- Conventional Commits (`feat:`, `fix:`, `chore(release):`, `refactor:`, …).
- On the default branch, create a feature/release branch before committing.
- Commit or push only when explicitly asked.
