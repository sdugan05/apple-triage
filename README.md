# apple-triage

Read-only Apple Mail and Apple Calendar CLI for daily Codex triage reports.

The command uses macOS `osascript` with JavaScript for Automation (JXA). It does not send, delete, archive, create, update, or accept anything.

## Install

On the target Mac:

```sh
./install.sh
```

This installs:

- `apple-triage` under `~/.local/bin`
- the companion Codex skill under `~/.codex/skills/apple-triage`

Ensure `~/.local/bin` is on PATH. The installer prints the exact zsh line if it is missing.

Alternative Make targets:

```sh
make install-skill   # CLI + Codex skill
make install-local   # CLI only
make uninstall
```

## Share with a friend

Zip or clone this folder onto their Mac, then have them run:

```sh
cd apple-triage
./install.sh
apple-triage --json doctor
apple-triage --json doctor --probe
```

No API keys or config files are needed. The first probe/live read may trigger macOS Automation permission prompts for Mail and Calendar.

## First run

```sh
apple-triage --json doctor
apple-triage --json doctor --probe
```

`doctor --probe` may trigger macOS permission prompts. Grant Automation access for Terminal, iTerm, OMP, or the Codex host that runs the command. On some systems, Full Disk Access may also be required.

If `doctor --probe` reports an Automation or permission error, stop and ask the user to approve Mail and Calendar access for the app running the command, then retry:

```sh
apple-triage --json doctor --probe
```

## Commands

```sh
apple-triage --json mail recent --hours 24 --limit 50
apple-triage --json mail search --query 'from:alice@example.com' --limit 25
apple-triage --json mail search --query 'subject:invoice' --limit 25
apple-triage --json calendar list
apple-triage --json calendar upcoming --days 1 --limit 50
apple-triage --json report daily --hours 24 --days 1
```

Calendar filtering:

```sh
apple-triage --json calendar upcoming --days 7 --calendar Work --calendar Personal
```

Some Apple Calendar sources are slow through Automation. `calendar upcoming` and `report daily` use a per-calendar timeout and include skipped sources in `skippedCalendars`. Filter with `--calendar Work` or raise `--calendar-timeout 10` if a specific calendar is slow but important.

When choosing a calendar for a smoke test, prefer `Work` if present. Otherwise choose the first non-holiday, non-birthday calendar from `calendar list`.

Raw escape hatch for custom read-only JXA scripts:

```sh
apple-triage --json raw mail --script ./mail-read-only.jxa.js
apple-triage --json raw calendar --script ./calendar-read-only.jxa.js
```

Raw scripts must print valid JSON via `JSON.stringify(...)`.

## JSON policy

With `--json`, success is always:

```json
{
  "ok": true,
  "data": {}
}
```

Errors are always:

```json
{
  "ok": false,
  "error": {
    "code": "stable_error_code",
    "message": "human-readable message",
    "details": {}
  }
}
```

No credentials are used or printed. Apple Mail and Calendar data is returned as local JSON only.

For `report daily`, the commonly summarized fields are:

- `data.inputs.unreadMailCount`
- `data.inputs.flaggedMailCount`
- `data.inputs.calendarEventCount`
- `data.inputs.skippedCalendarCount`
- `data.mail.unread`
- `data.mail.flagged`
- `data.calendar.upcoming`
- `data.calendar.skippedCalendars`

## Codex smoke test

For an end-to-end read-only validation on a target Mac:

```sh
./install.sh
apple-triage --json doctor > /tmp/apple-triage-doctor.json
apple-triage --json doctor --probe > /tmp/apple-triage-probe.json
apple-triage --json calendar list > /tmp/apple-triage-calendars.json
```

Pick a real calendar name from `/tmp/apple-triage-calendars.json`, then run:

```sh
CALENDAR_NAME="Work"
apple-triage --json --timeout 180 report daily --hours 24 --days 1 --calendar "$CALENDAR_NAME" > /tmp/apple-triage-daily.json
```

Validate the saved outputs:

```sh
python3 - <<'PY'
import json

for name in ["doctor", "probe", "calendars", "daily"]:
    path = f"/tmp/apple-triage-{name}.json"
    data = json.load(open(path))
    print(f"{name}: valid_json=true ok={data.get('ok')}")
PY
```

Extract a compact summary without dumping long mail previews:

```sh
python3 - <<'PY'
import json

data = json.load(open("/tmp/apple-triage-daily.json"))["data"]
print("inputs:", data["inputs"])
print("unread:")
for item in data["mail"]["unread"][:10]:
    print("-", item["sender"], "|", item["subject"], "|", item["dateReceived"])
print("flagged:")
for item in data["mail"]["flagged"][:10]:
    print("-", item["sender"], "|", item["subject"], "|", item["dateReceived"])
print("events:")
for event in data["calendar"]["upcoming"]:
    print("-", event["calendar"], "|", event["summary"], "|", event["start"], "to", event["end"], "|", event.get("location", ""))
print("skipped:", data["calendar"]["skippedCalendars"])
PY
```

Summarize the result as: unread mail count and notable unread items, flagged mail count and items, upcoming events in local time, skipped calendars, and any errors. Prioritize security/account alerts, direct asks, real people, finance/legal/travel, then newsletters and promotions.

## Daily Codex triage prompt

```text
Run `apple-triage --json --timeout 180 report daily --hours 24 --days 1`, then summarize: urgent unread mail, flagged mail, meetings today, scheduling conflicts, and suggested replies. Do not send or modify anything. If calendar reads are slow, first run `apple-triage --json calendar list`, then retry with a known calendar such as `--calendar Work`.
```


## Codex documentation

The repo includes a companion skill at:

```text
.codex/skills/apple-triage/SKILL.md
```

`./install.sh` copies it into:

```text
~/.codex/skills/apple-triage/SKILL.md
```

That skill tells future Codex sessions which command to run first, how to handle macOS permissions, which daily report command to use, and what actions are forbidden without explicit approval.

## Privacy and safety

- Read-only AppleScript/JXA automation.
- No network access.
- No writes to Mail or Calendar.
- No token/config file.
- The raw escape hatch is intended for read-only scripts; inspect scripts before running them.
