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
