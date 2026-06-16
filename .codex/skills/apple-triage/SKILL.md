---
name: apple-triage
description: Use the local apple-triage CLI to read Apple Mail and Apple Calendar for read-only daily triage reports. Use when asked for inbox triage, calendar triage, schedule review, or a daily briefing from Apple apps.
---

# Apple Triage

Use the installed `apple-triage` command. It is read-only and local: no network, no mail sends, no deletes, no calendar writes.

## First command

```sh
command -v apple-triage && apple-triage --json doctor
```

If the command is missing and this repository is available, install it:

```sh
./install.sh
```

If access has not been granted yet, run:

```sh
apple-triage --json doctor --probe
```

This may trigger macOS Automation permission prompts for Mail and Calendar. Ask the user to approve them in System Settings if the probe reports permission errors.

## Daily triage path

```sh
apple-triage --json --timeout 180 report daily --hours 24 --days 1
```

For faster and more complete calendar reads, filter known calendars:

```sh
apple-triage --json --timeout 180 report daily --hours 24 --days 1 --calendar Work
```

If output includes `skippedCalendars`, mention that those calendar sources timed out.

Summarize:

- urgent unread mail
- flagged mail
- meetings today
- scheduling conflicts or tight transitions
- likely reply/action suggestions

Do not send replies or modify Mail/Calendar unless the user explicitly asks and a separate write-capable tool exists.

## Discovery commands

```sh
apple-triage --json calendar list
apple-triage --json calendar upcoming --days 7 --calendar Work
apple-triage --json mail recent --hours 24 --limit 50
apple-triage --json mail search --query 'from:alice@example.com' --limit 25
```

## Raw escape hatch

Only run raw scripts you have read first:

```sh
apple-triage --json raw mail --script ./read-only-mail-query.jxa.js
apple-triage --json raw calendar --script ./read-only-calendar-query.jxa.js
```

Raw scripts must print `JSON.stringify(...)`. Treat raw scripts as code execution with the user's local Apple app permissions.

## Never do without explicit approval

- Send email.
- Delete, archive, move, or mark mail read.
- Create, edit, delete, accept, or decline calendar events.
- Run uninspected raw scripts.
