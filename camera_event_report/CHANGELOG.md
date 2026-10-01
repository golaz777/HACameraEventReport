# Changelog

All notable changes to Camera Event Report are documented here.

## [1.6.1] - 2026-10-01

### Fixed
- **Reports could be viewed, exported or deleted outside the media folder.**
  An encoded slash (`%2F`) in the date part of a report URL was decoded into
  an absolute path. The date must now be a real `YYYY-MM-DD` folder name and
  the file must resolve inside `media_path`.

## [1.6.0] - 2026-10-01

### Added
- **Home Assistant entities** — `binary_sensor.camera_event_report_monitoring`,
  `sensor.camera_event_report_session_events`,
  `sensor.camera_event_report_last_motion` and
  `sensor.camera_event_report_last_report`.
- **Home Assistant events** — `camera_event_report_motion` and
  `camera_event_report_report_ready`, for your own automations.
- **Export** — download any report as a ZIP with the original snapshots,
  `events.csv`, `events.json` and `SHA256SUMS`.
- New `homeassistant` options (`publish_entities`, `fire_events`), both on by
  default.

### Fixed
- **Restarting the add-on during an away session no longer truncates the
  report.** The session start is now saved in `<media_path>/session.json` and
  restored on startup.

## [1.5.1] - 2026-10-01

### Fixed
- **Changelog was not shown in Home Assistant.** The Supervisor reads an
  add-on's `CHANGELOG.md` from the add-on's own directory, next to
  `config.yaml`; this file previously lived at the repository root, where Home
  Assistant never looks. Nothing about the add-on's behaviour changed.

Human detection arrived in 1.5.0 — see the entry below for what it does and
how to configure it.

## [1.5.0] - 2026-10-01

### Added
- **Human detection in snapshots** — when away monitoring ends, every snapshot
  from the session is analysed locally with an SSD MobileNet V1 ONNX model and
  marked as containing a person or not. Runs entirely on-device: no API keys,
  no cloud, no images leaving your hardware.
- The saved report gains a **Person** column (Human / Clear / — for frames that
  were not analysed) and a `Humans detected: N of M snapshot(s)` summary line.
- The Reports page shows a **human badge** on any session where a person was
  found, so an intruder is visible without opening the report.
- The Home Assistant persistent notification now leads with the human count
  when a person was detected.
- Verdicts are stored in each day's `events.json` as `human_detected` and
  `human_confidence` for use by your own automations.
- New `detection` options: `enabled` (default `true`) and `confidence`
  (default `0.4`).

### Fixed
- **Report event counts never appeared on the Reports page** — the parser that
  recovers the event count from a saved report did not account for the `<span>`
  wrapper in the summary block, so every report showed no count.

### Notes
- Detection needs `onnxruntime`, which publishes no wheels for the `armhf`,
  `armv7` and `i386` architectures. On those the add-on installs and runs
  exactly as before, logging one warning and skipping analysis.
- The bundled model weights are MIT licensed — see `NOTICE` for provenance
  and checksum.

## [1.4.1] - 2026-07-15

### Fixed
- **Add-on Store repository structure** — adding the GitHub repo as a custom
  repository failed with *"is not a valid add-on repository."* The add-on files
  now live in a `camera_event_report/` subdirectory with a `repository.yaml` at
  the repo root, matching Home Assistant's required repository layout so the
  store accepts the URL.

## [1.4.0] - 2026-06-30

### Changed
- **Mobile-friendly navigation** — on narrow screens the topbar's four pill links (Reports, Live, Camera Test, Analytics) used to overflow into an invisible horizontal-scroll strip, making the last items hard to reach. Below 640px the pills now collapse behind a hamburger button that opens a full-width dropdown of the same links; it closes on link tap, outside-click, or Escape. Desktop is unchanged.

## [1.3.0] - 2026-06-29

### Changed
- **Clean & bright redesign** — the web UI moves from the dark slate theme to an airy light one: white surfaces, soft indigo-tinted shadows, rounder corners, and a brighter blue accent. The topbar gains a gradient brand mark and pill navigation whose active page is shown as a filled gradient chip, and the Analytics stat cards get a gradient accent bar with larger numbers. Saved Motion Reports adopt the matching light theme; the fullscreen snapshot lightbox keeps its dark photo backdrop. No features or behavior changed.

## [1.2.2] - 2026-06-29

### Added
- **Motion Report image navigation** — the snapshot lightbox in generated reports now supports browsing between images with the Left/Right arrow keys (or on-screen arrows), with a time/camera caption. Applies to newly generated reports.

## [1.2.1] - 2026-06-29

### Added
- **Live snapshot lightbox** — click any event row on the "Live" page to view its snapshot fullscreen, with a camera/timestamp caption. Navigate between snapshots with the Left/Right arrow keys (or on-screen arrows); close with Escape, the × button, or by clicking the backdrop.

## [1.2.0] - 2026-06-29

### Added
- **Live page backlog** — the "Live" tab now loads today's already-detected events immediately on open (capped to the 50 most recent), instead of only showing events that arrive after the page connects. Reconnects no longer duplicate cards.
- **Delete All reports** — new button on the "Camera Reports" page removes every report at once (with confirmation), backed by a `DELETE /reports/delete-all` endpoint.

## [1.1.0] - 2026-04-22

### Added
- **Event filtering** — filter reports by date range and minimum event count
- **Analytics dashboard** — new "Analytics" tab shows motion statistics
  - Events per day (bar chart)
  - Events per camera (bar chart)
  - Events by hour of day (heatmap)
  - Summary stats: total events, peak day, busiest camera
- **EventStore enhancements** — `read_range()` for multi-day queries, `list_dates()` for date enumeration

## [1.0.2] - 2026-04-22

### Added
- **Live event stream dashboard** — new "Live" tab in the web panel shows motion events in real time as they occur, no page refresh needed. Each event displays the camera name, timestamp, and a snapshot thumbnail. Connects via Server-Sent Events (SSE) with automatic reconnection.

## [1.0.1] - 2025

### Added
- Automatic retention policy — purges event data older than a configurable number of days on startup (`retention_days` option)

## [1.0.0] - 2025

### Added
- Initial stable release
- Motion monitoring for multiple cameras via Home Assistant entity state changes
- Snapshot capture on motion with configurable cooldown
- Timestamped HTML reports grouped by day, viewable in the HA sidebar (ingress)
- HA persistent notifications on return home
- Optional email delivery via SMTP
- Camera test panel to verify snapshot capture
- Monitoring toggle via any HA entity (`input_boolean`, `person`, etc.)
