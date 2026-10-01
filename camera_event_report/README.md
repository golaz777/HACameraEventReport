# Camera Event Report

Watch your cameras while you are away, then find out whether anyone was
actually there.

Motion sensors cannot tell a person from a windy tree, a passing car or the
cat. This add-on captures a snapshot every time motion is detected while you
are out, and when you get home it checks every one of them for **people** and
builds an HTML report with the answer at the top.

## What it does

- Captures a snapshot per motion event, with a per-camera cooldown so one long
  movement does not flood the report
- **Detects humans on-device** — no API key, no cloud, no snapshot ever leaves
  your hardware
- Flags each snapshot as **Human**, **Clear**, or not analysed, and summarises
  the session as *"Humans detected: N of M"*
- Notifies you in Home Assistant when you return, leading with the human count
  if someone was found
- Web panel with saved reports, a live event feed, analytics and a camera test
  page
- Optional email delivery and automatic cleanup of old events
- **Home Assistant entities and events** — monitoring state, motion counts and
  report results as entities, plus `camera_event_report_motion` /
  `camera_event_report_report_ready` events for your own automations
- **Evidence export** — download any report as a ZIP with the original
  snapshots, CSV/JSON event data and SHA-256 checksums

## Quick start

1. Create a toggle helper to mark when you are away (e.g. `Away mode`).
2. Add your cameras, pairing each one with its motion sensor.
3. Point `monitoring.toggle_entity` at your toggle — **without it, monitoring
   never runs.**

Turn the toggle on when you leave, off when you get back. The report is waiting.

See the **Documentation** tab for the full option reference, detection tuning
and troubleshooting.
