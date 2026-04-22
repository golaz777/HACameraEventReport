# Changelog

All notable changes to Camera Event Report are documented here.

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
