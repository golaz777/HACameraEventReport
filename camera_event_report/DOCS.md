# Camera Event Report

Watches your cameras while you are away, saves a snapshot every time motion is
detected, and — when you get home — checks every snapshot for **people** and
builds an HTML report.

The point is to answer one question quickly: *was someone actually here?* A
windy tree, a passing car and an intruder all trip a motion sensor, but only one
of them puts a person in frame.

## Requirements

- Cameras exposed to Home Assistant as `camera.*` entities that support
  snapshots (test this on the built-in **Camera Test** page before relying on it).
- A **binary sensor** per camera that reports motion (`binary_sensor.*`).
- A toggle entity to mark when you are away — an `input_boolean`, a `person`
  entity, a `device_tracker`, anything with on/off state.

Without a toggle entity, **monitoring never runs**. This is the single most
common configuration mistake.

## Setup

1. Create a toggle if you do not already have one — Settings → Devices &
   Services → Helpers → Create helper → Toggle. Call it e.g. `Away mode`.
2. Add each camera to `cameras`, pairing the camera entity with its motion
   sensor.
3. Set `monitoring.toggle_entity` to your toggle.
4. Start the add-on and open the panel from the sidebar.
5. Open **Camera Test** and trigger a test snapshot for each camera. Fix any
   failures here before going further.

Turn the toggle **on** when you leave. Turn it **off** when you return — that is
what triggers analysis and the report.

## Options

| Option | Type | Default | Description |
|---|---|---|---|
| `cameras` | list | `[]` | Cameras to watch — see below |
| `monitoring.toggle_entity` | string | `""` | Entity that starts/stops monitoring. **Required** |
| `event_cooldown_seconds` | int | `30` | Minimum gap between recorded events per camera. Stops one continuous motion from filling the report |
| `media_path` | string | `/data/camera_events` | Where snapshots and reports are written. The default is persistent |
| `retention_days` | int (optional) | `30` | Delete event data older than this on startup. Leave empty to keep everything forever |
| `detection.enabled` | bool | `true` | Analyse snapshots for people after monitoring ends |
| `detection.confidence` | float | `0.4` | Minimum score (0–1) for a detection to count as a person |
| `notification.ha_persistent` | bool | `true` | Create a Home Assistant notification when you return |
| `report.email.enabled` | bool | `false` | Also email the report |
| `report.email.smtp_host` | string | `""` | SMTP server hostname |
| `report.email.smtp_port` | int | `587` | SMTP port |
| `report.email.smtp_user` | string | `""` | SMTP username |
| `report.email.smtp_password` | password | `""` | SMTP password |
| `report.email.recipient` | string | `""` | Recipient. Separate several with `;` |
| `report.email.sender` | string | `""` | From address |

### Cameras

Each entry needs the camera entity and the motion sensor that belongs to it:

| Key | Type | Description |
|---|---|---|
| `entity_id` | string | The camera, e.g. `camera.front_door` |
| `motion_entity` | string | Its motion sensor, e.g. `binary_sensor.front_door_motion` |
| `name` | string (optional) | Label used in reports. Defaults to the entity id suffix, e.g. `front_door` |

### Example

```yaml
cameras:
  - entity_id: camera.front_door
    motion_entity: binary_sensor.front_door_motion
    name: Front Door
  - entity_id: camera.back_yard
    motion_entity: binary_sensor.back_yard_motion
    name: Back Yard

monitoring:
  toggle_entity: input_boolean.away_mode

detection:
  enabled: true
  confidence: 0.4

notification:
  ha_persistent: true

event_cooldown_seconds: 30
media_path: /data/camera_events
retention_days: 30

report:
  email:
    enabled: false
    smtp_host: smtp.gmail.com
    smtp_port: 587
    smtp_user: you@gmail.com
    smtp_password: your-app-password
    recipient: you@gmail.com
    sender: you@gmail.com
```

## Human detection

When monitoring ends, every snapshot from that session is classified as
containing a person or not. This runs **entirely on your hardware** using a
bundled SSD MobileNet V1 model — no API key, no cloud service, and no snapshot
ever leaves the machine.

Each snapshot ends up in one of three states:

| Badge | Meaning |
|---|---|
| **Human** | A person was found, at or above your confidence threshold |
| **Clear** | The snapshot was analysed and no person was found |
| **—** | The snapshot was never analysed — usually a failed capture |

"Clear" and "—" are deliberately different. The report will not tell you a frame
was free of people if it never actually looked at it.

Results appear in the report (a **Person** column plus a `Humans detected: N of
M` summary), as a badge on the Reports list, and in the Home Assistant
notification, which leads with the human count when someone was found.

### Tuning

`detection.confidence` is the dial:

- **Missing real people?** Lower it — try `0.3`, then `0.25`.
- **False alarms from pets, cars or headlights?** Raise it — try `0.5` or `0.6`.

Analysis happens once, after you get home, so it costs nothing while you are
away. A typical session of a few dozen snapshots takes a couple of seconds.

### Using the results elsewhere

Verdicts are written into each day's `events.json` under `media_path` as
`human_detected` (`true`/`false`/`null`) and `human_confidence`, so your own
scripts and automations can read them.

### Architecture support

Detection needs `onnxruntime`, which has no builds for **armhf**, **armv7** or
**i386**. On those systems the add-on installs and runs exactly as it otherwise
would — it logs one warning at startup and skips the analysis step. Everything
else, including snapshots and reports, works normally.

On `aarch64` and `amd64` you will see `Human detection ready` in the log at
startup. That line is the quickest confirmation it loaded.

## The web panel

Open it from the sidebar.

- **Reports** — every saved report, newest first, filterable by date range and
  minimum event count. Sessions where a person was found carry a badge.
- **Live** — a real-time feed of motion events with snapshots as they happen.
- **Analytics** — motion patterns by day, by camera and by hour.
- **Camera Test** — trigger a snapshot on demand to verify a camera works.

## How it works

1. The add-on subscribes to Home Assistant state changes.
2. Your toggle turns **on** → monitoring starts.
3. A motion sensor fires → a snapshot is captured and recorded, subject to the
   per-camera cooldown.
4. Your toggle turns **off** → every snapshot from the session is analysed for
   people, and an HTML report is generated.
5. The report is saved, a notification is sent, and an email goes out if
   configured.

Reports and snapshots are written to `media_path`, grouped by day.

## Troubleshooting

**Nothing is ever recorded.**
`monitoring.toggle_entity` is almost certainly empty or pointing at an entity
that does not exist. Monitoring does not run without it. Check the log at
startup.

**Snapshots are missing or blank.**
Use the **Camera Test** page. If a camera fails there, the problem is between
Home Assistant and the camera, not in this add-on.

**No human verdicts in the report.**
Check the startup log. `Human detection ready` means it loaded; a warning about
a missing dependency means your architecture has no `onnxruntime` build (see
above); a warning about a missing model means the image did not build cleanly.
Also confirm `detection.enabled` is `true`.

**People are being missed, or pets trigger it.**
Adjust `detection.confidence` — see Tuning above.

**Too many near-identical events.**
Raise `event_cooldown_seconds`.

**Running out of disk.**
Lower `retention_days`. Old day folders are purged at startup.

**An update will not install.**
Use **Update**, never **Rebuild** — Rebuild re-builds the version you already
have. If Update stays greyed out, run `ha addons reload` or restart the
Supervisor. Never uninstall to update; that wipes your configuration.

## Privacy

Snapshots, reports and detection all stay on your Home Assistant machine. The
only outbound connection the add-on ever makes is to your SMTP server, and only
if you enable email reports.
