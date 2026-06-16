#!/usr/bin/env python3
"""Read-only Apple Mail and Calendar triage CLI."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

VERSION = "0.1.0"


class CliError(Exception):
    def __init__(self, message: str, *, code: str = "error", exit_code: int = 1, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.exit_code = exit_code
        self.details = details or {}


@dataclass(frozen=True)
class GlobalOptions:
    json_output: bool
    timeout: int


def emit_success(data: Any, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps({"ok": True, "data": data}, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        if isinstance(data, str):
            print(data)
        else:
            print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def emit_error(error: CliError, *, json_output: bool) -> None:
    payload = {"ok": False, "error": {"code": error.code, "message": error.message}}
    if error.details:
        payload["error"]["details"] = error.details
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
    else:
        print(f"error: {error.message}", file=sys.stderr)


def run_osascript_jxa(script: str, *, timeout: int) -> Any:
    exe = shutil.which("osascript")
    if not exe:
        raise CliError("osascript was not found on PATH", code="missing_osascript")

    with tempfile.NamedTemporaryFile("w", suffix=".jxa.js", delete=False) as handle:
        handle.write(script)
        path = handle.name
    try:
        proc = subprocess.run(
            [exe, "-l", "JavaScript", path],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CliError(
            f"osascript timed out after {timeout}s",
            code="osascript_timeout",
            details={"timeoutSeconds": timeout},
        ) from exc
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass

    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        hint = permission_hint(stderr)
        raise CliError(
            "Apple automation failed" + (f": {stderr}" if stderr else ""),
            code="osascript_failed",
            details={"stderr": stderr, "hint": hint},
        )

    output = proc.stdout.strip()
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise CliError(
            "osascript returned non-JSON output",
            code="bad_osascript_json",
            details={"stdout": output[:4000]},
        ) from exc


def permission_hint(stderr: str) -> str:
    low = stderr.lower()
    if "not authorized" in low or "not allowed" in low or "privacy" in low or "permission" in low:
        return "Grant automation access in System Settings → Privacy & Security → Automation, and Full Disk Access if your macOS build requires it."
    if "application isn’t running" in low or "application isn't running" in low:
        return "Open the target Apple app once, then retry."
    return "If this is the first run, approve the macOS Automation permission prompt for Terminal or your Codex host."


def jxa_string(value: str) -> str:
    return json.dumps(value)


def mail_recent_script(hours: int, limit: int, mailbox: str) -> str:
    return f"""
ObjC.import('stdlib');
function safe(fn, fallback) {{ try {{ var value = fn(); return value == null ? fallback : value; }} catch (e) {{ return fallback; }} }}
function iso(value) {{ try {{ return value ? new Date(value).toISOString() : null; }} catch (e) {{ return null; }} }}
function text(value, max) {{
  if (value == null) return '';
  var s = String(value).replace(/\\r/g, '\\n').replace(/[ \\t]+/g, ' ').trim();
  if (max && s.length > max) return s.slice(0, max) + '…';
  return s;
}}
var app = Application('Mail');
app.includeStandardAdditions = true;
var cutoff = Date.now() - ({hours} * 60 * 60 * 1000);
var wantedMailbox = {jxa_string(mailbox)};
var maxItems = {limit};
var out = [];
function pushMessage(m, accountName, mailboxName) {{
  var dateObj = safe(function() {{ return m.dateReceived(); }}, null);
  var ts = dateObj ? new Date(dateObj).getTime() : 0;
  if (ts < cutoff) return;
  out.push({{
    id: text(safe(function() {{ return m.id(); }}, ''), 0),
    subject: text(safe(function() {{ return m.subject(); }}, ''), 300),
    sender: text(safe(function() {{ return m.sender(); }}, ''), 300),
    mailbox: mailboxName,
    account: accountName,
    dateReceived: iso(dateObj),
    read: !!safe(function() {{ return m.readStatus(); }}, false),
    flagged: !!safe(function() {{ return m.flaggedStatus(); }}, false),
    preview: text(safe(function() {{ return m.content(); }}, ''), 500)
  }});
}}
var accounts = app.accounts();
for (var ai = 0; ai < accounts.length; ai++) {{
  var account = accounts[ai];
  var accountName = text(safe(function() {{ return account.name(); }}, ''), 0);
  var boxes = [];
  if (wantedMailbox) {{
    try {{ boxes = [account.mailboxes.byName(wantedMailbox)]; }} catch (e) {{ boxes = []; }}
  }} else {{
    try {{ boxes = [account.mailboxes.byName('INBOX')]; }} catch (e) {{ boxes = account.mailboxes(); }}
  }}
  for (var bi = 0; bi < boxes.length; bi++) {{
    var box = boxes[bi];
    var mailboxName = text(safe(function() {{ return box.name(); }}, wantedMailbox || ''), 0);
    var messages = safe(function() {{ return box.messages(); }}, []);
    for (var mi = 0; mi < messages.length; mi++) {{
      pushMessage(messages[mi], accountName, mailboxName);
      if (out.length >= maxItems * 4) break;
    }}
  }}
}}
out.sort(function(a, b) {{ return String(b.dateReceived || '').localeCompare(String(a.dateReceived || '')); }});
out = out.slice(0, maxItems);
JSON.stringify({{source: 'Apple Mail', hours: {hours}, limit: {limit}, mailbox: wantedMailbox || null, messages: out}});
"""


def mail_search_script(query: str, limit: int, mailbox: str) -> str:
    # Search is intentionally local/simple so it works across Mail account types.
    return f"""
function safe(fn, fallback) {{ try {{ var value = fn(); return value == null ? fallback : value; }} catch (e) {{ return fallback; }} }}
function iso(value) {{ try {{ return value ? new Date(value).toISOString() : null; }} catch (e) {{ return null; }} }}
function text(value, max) {{
  if (value == null) return '';
  var s = String(value).replace(/\\r/g, '\\n').replace(/[ \\t]+/g, ' ').trim();
  if (max && s.length > max) return s.slice(0, max) + '…';
  return s;
}}
function matches(m, q) {{
  var subject = text(safe(function() {{ return m.subject(); }}, ''), 0).toLowerCase();
  var sender = text(safe(function() {{ return m.sender(); }}, ''), 0).toLowerCase();
  var content = text(safe(function() {{ return m.content(); }}, ''), 0).toLowerCase();
  if (q.indexOf('from:') === 0) return sender.indexOf(q.slice(5).trim()) >= 0;
  if (q.indexOf('subject:') === 0) return subject.indexOf(q.slice(8).trim()) >= 0;
  return subject.indexOf(q) >= 0 || sender.indexOf(q) >= 0 || content.indexOf(q) >= 0;
}}
var app = Application('Mail');
var q = {jxa_string(query.lower())};
var wantedMailbox = {jxa_string(mailbox)};
var maxItems = {limit};
var out = [];
var accounts = app.accounts();
for (var ai = 0; ai < accounts.length; ai++) {{
  var account = accounts[ai];
  var accountName = text(safe(function() {{ return account.name(); }}, ''), 0);
  var boxes = [];
  if (wantedMailbox) {{
    try {{ boxes = [account.mailboxes.byName(wantedMailbox)]; }} catch (e) {{ boxes = []; }}
  }} else {{
    boxes = safe(function() {{ return account.mailboxes(); }}, []);
  }}
  for (var bi = 0; bi < boxes.length; bi++) {{
    var box = boxes[bi];
    var mailboxName = text(safe(function() {{ return box.name(); }}, ''), 0);
    var messages = safe(function() {{ return box.messages(); }}, []);
    for (var mi = 0; mi < messages.length; mi++) {{
      var m = messages[mi];
      if (!matches(m, q)) continue;
      var dateObj = safe(function() {{ return m.dateReceived(); }}, null);
      out.push({{
        id: text(safe(function() {{ return m.id(); }}, ''), 0),
        subject: text(safe(function() {{ return m.subject(); }}, ''), 300),
        sender: text(safe(function() {{ return m.sender(); }}, ''), 300),
        mailbox: mailboxName,
        account: accountName,
        dateReceived: iso(dateObj),
        read: !!safe(function() {{ return m.readStatus(); }}, false),
        flagged: !!safe(function() {{ return m.flaggedStatus(); }}, false),
        preview: text(safe(function() {{ return m.content(); }}, ''), 500)
      }});
      if (out.length >= maxItems) break;
    }}
    if (out.length >= maxItems) break;
  }}
  if (out.length >= maxItems) break;
}}
out.sort(function(a, b) {{ return String(b.dateReceived || '').localeCompare(String(a.dateReceived || '')); }});
JSON.stringify({{source: 'Apple Mail', query: {jxa_string(query)}, limit: maxItems, mailbox: wantedMailbox || null, messages: out}});
"""


def calendar_upcoming_script(days: int, limit: int, calendars: list[str]) -> str:
    names = json.dumps(calendars)
    return f"""
function safe(fn, fallback) {{ try {{ var value = fn(); return value == null ? fallback : value; }} catch (e) {{ return fallback; }} }}
function iso(value) {{ try {{ return value ? new Date(value).toISOString() : null; }} catch (e) {{ return null; }} }}
function text(value, max) {{
  if (value == null) return '';
  var s = String(value).replace(/\\r/g, '\\n').replace(/[ \\t]+/g, ' ').trim();
  if (max && s.length > max) return s.slice(0, max) + '…';
  return s;
}}
var app = Application('Calendar');
var selected = {names};
var selectedMap = {{}};
for (var si = 0; si < selected.length; si++) selectedMap[String(selected[si]).toLowerCase()] = true;
var start = new Date();
var end = new Date(Date.now() + ({days} * 24 * 60 * 60 * 1000));
var maxItems = {limit};
var out = [];
var cals = app.calendars();
for (var ci = 0; ci < cals.length; ci++) {{
  var cal = cals[ci];
  var calName = text(safe(function() {{ return cal.name(); }}, ''), 0);
  if (selected.length && !selectedMap[calName.toLowerCase()]) continue;
  var events = safe(function() {{
    return cal.events.whose({{ _and: [{{ startDate: {{ _lessThan: end }} }}, {{ endDate: {{ _greaterThan: start }} }}] }})();
  }}, []);
  for (var ei = 0; ei < events.length; ei++) {{
    var ev = events[ei];
    var evStart = safe(function() {{ return ev.startDate(); }}, null);
    var evEnd = safe(function() {{ return ev.endDate(); }}, null);
    out.push({{
      id: text(safe(function() {{ return ev.uid(); }}, safe(function() {{ return ev.id(); }}, '')), 0),
      calendar: calName,
      summary: text(safe(function() {{ return ev.summary(); }}, ''), 300),
      start: iso(evStart),
      end: iso(evEnd),
      location: text(safe(function() {{ return ev.location(); }}, ''), 300),
      description: text(safe(function() {{ return ev.description(); }}, ''), 700),
      allday: !!safe(function() {{ return ev.alldayEvent(); }}, false)
    }});
  }}
}}
out.sort(function(a, b) {{ return String(a.start || '').localeCompare(String(b.start || '')); }});
out = out.slice(0, maxItems);
JSON.stringify({{source: 'Apple Calendar', days: {days}, limit: maxItems, calendars: selected, events: out}});
"""


def calendar_list_script() -> str:
    return """
function safe(fn, fallback) { try { var value = fn(); return value == null ? fallback : value; } catch (e) { return fallback; } }
function text(value) { return value == null ? '' : String(value).trim(); }
var app = Application('Calendar');
var out = [];
var cals = app.calendars();
for (var i = 0; i < cals.length; i++) {
  var cal = cals[i];
  out.push({ index: i, id: text(safe(function() { return cal.id(); }, '')), name: text(safe(function() { return cal.name(); }, '')), writable: !!safe(function() { return cal.writable(); }, false) });
}
JSON.stringify({ source: 'Apple Calendar', calendars: out });
"""



def calendar_events_for_index_script(index: int, days: int) -> str:
    return f"""
function safe(fn, fallback) {{ try {{ var value = fn(); return value == null ? fallback : value; }} catch (e) {{ return fallback; }} }}
function iso(value) {{ try {{ return value ? new Date(value).toISOString() : null; }} catch (e) {{ return null; }} }}
function text(value, max) {{
  if (value == null) return '';
  var s = String(value).replace(/\\r/g, '\\n').replace(/[ \\t]+/g, ' ').trim();
  if (max && s.length > max) return s.slice(0, max) + '…';
  return s;
}}
var app = Application('Calendar');
var cal = app.calendars()[{index}];
var calName = text(safe(function() {{ return cal.name(); }}, ''), 0);
var start = new Date();
var end = new Date(Date.now() + ({days} * 24 * 60 * 60 * 1000));
var events = cal.events.whose({{ _and: [{{ startDate: {{ _lessThan: end }} }}, {{ endDate: {{ _greaterThan: start }} }}] }})();
var out = [];
for (var ei = 0; ei < events.length; ei++) {{
  var ev = events[ei];
  var evStart = safe(function() {{ return ev.startDate(); }}, null);
  var evEnd = safe(function() {{ return ev.endDate(); }}, null);
  out.push({{
    id: text(safe(function() {{ return ev.uid(); }}, safe(function() {{ return ev.id(); }}, '')), 0),
    calendar: calName,
    summary: text(safe(function() {{ return ev.summary(); }}, ''), 300),
    start: iso(evStart),
    end: iso(evEnd),
    location: text(safe(function() {{ return ev.location(); }}, ''), 300),
    description: text(safe(function() {{ return ev.description(); }}, ''), 700),
    allday: !!safe(function() {{ return ev.alldayEvent(); }}, false)
  }});
}}
JSON.stringify({{ index: {index}, calendar: calName, events: out }});
"""

def summarize_daily(mail: dict[str, Any], calendar: dict[str, Any]) -> dict[str, Any]:
    messages = mail.get("messages", []) if isinstance(mail, dict) else []
    events = calendar.get("events", []) if isinstance(calendar, dict) else []
    skipped_calendars = calendar.get("skippedCalendars", []) if isinstance(calendar, dict) else []
    unread = [m for m in messages if not m.get("read")]
    flagged = [m for m in messages if m.get("flagged")]
    now = datetime.now(timezone.utc).isoformat()
    return {
        "generatedAt": now,
        "inputs": {
            "mailCount": len(messages),
            "unreadMailCount": len(unread),
            "flaggedMailCount": len(flagged),
            "calendarEventCount": len(events),
            "skippedCalendarCount": len(skipped_calendars),
        },
        "mail": {
            "unread": unread[:20],
            "flagged": flagged[:20],
            "recent": messages[:20],
        },
        "calendar": {
            "upcoming": events[:30],
            "skippedCalendars": skipped_calendars,
        },
    }


def command_doctor(args: argparse.Namespace, opts: GlobalOptions) -> dict[str, Any]:
    checks = {
        "version": VERSION,
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "commands": {
            "osascript": shutil.which("osascript"),
            "sqlite3": shutil.which("sqlite3"),
        },
        "privacy": {
            "usesAutomation": True,
            "writes": False,
            "setup": "First live read may prompt for Automation access to Mail and Calendar.",
        },
    }
    if args.probe:
        probes: dict[str, Any] = {}
        for name, script in (("mail", "JSON.stringify({app: Application('Mail').name()});"), ("calendar", "JSON.stringify({app: Application('Calendar').name()});")):
            try:
                probes[name] = {"ok": True, "result": run_osascript_jxa(script, timeout=opts.timeout)}
            except CliError as exc:
                probes[name] = {"ok": False, "code": exc.code, "message": exc.message, "details": exc.details}
        checks["probes"] = probes
    return checks


def command_mail_recent(args: argparse.Namespace, opts: GlobalOptions) -> Any:
    return run_osascript_jxa(mail_recent_script(args.hours, args.limit, args.mailbox or ""), timeout=opts.timeout)


def command_mail_search(args: argparse.Namespace, opts: GlobalOptions) -> Any:
    return run_osascript_jxa(mail_search_script(args.query, args.limit, args.mailbox or ""), timeout=opts.timeout)


def command_calendar_list(args: argparse.Namespace, opts: GlobalOptions) -> Any:
    return run_osascript_jxa(calendar_list_script(), timeout=opts.timeout)


def collect_calendar_upcoming(days: int, limit: int, selected: list[str], *, timeout: int, per_calendar_timeout: int) -> dict[str, Any]:
    listing = run_osascript_jxa(calendar_list_script(), timeout=timeout)
    calendars = listing.get("calendars", []) if isinstance(listing, dict) else []
    selected_map = {name.lower() for name in selected}
    events: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for calendar in calendars:
        name = str(calendar.get("name", ""))
        if selected_map and name.lower() not in selected_map:
            continue
        try:
            result = run_osascript_jxa(
                calendar_events_for_index_script(int(calendar["index"]), days),
                timeout=min(timeout, per_calendar_timeout),
            )
        except CliError as exc:
            skipped.append({"calendar": name, "code": exc.code, "message": exc.message})
            continue
        events.extend(result.get("events", []) if isinstance(result, dict) else [])
        if len(events) >= limit:
            break
    events.sort(key=lambda event: str(event.get("start") or ""))
    return {
        "source": "Apple Calendar",
        "days": days,
        "limit": limit,
        "calendars": selected,
        "events": events[:limit],
        "skippedCalendars": skipped,
    }


def command_calendar_upcoming(args: argparse.Namespace, opts: GlobalOptions) -> Any:
    return collect_calendar_upcoming(
        args.days,
        args.limit,
        args.calendar or [],
        timeout=opts.timeout,
        per_calendar_timeout=args.calendar_timeout,
    )


def command_report_daily(args: argparse.Namespace, opts: GlobalOptions) -> Any:
    mail = run_osascript_jxa(mail_recent_script(args.hours, args.mail_limit, args.mailbox or ""), timeout=opts.timeout)
    calendar = collect_calendar_upcoming(
        args.days,
        args.event_limit,
        args.calendar or [],
        timeout=opts.timeout,
        per_calendar_timeout=args.calendar_timeout,
    )
    return summarize_daily(mail, calendar)


def command_raw(args: argparse.Namespace, opts: GlobalOptions) -> Any:
    path = Path(args.script).expanduser()
    if not path.is_file():
        raise CliError(f"script not found: {path}", code="script_not_found")
    script = path.read_text()
    result = run_osascript_jxa(script, timeout=opts.timeout)
    return {"target": args.target, "script": str(path), "result": result}


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="apple-triage",
        description="Read-only Apple Mail and Calendar CLI for daily Codex triage reports.",
    )
    parser.add_argument("--version", action="version", version=f"apple-triage {VERSION}")
    parser.add_argument("--json", action="store_true", help="Emit stable JSON envelope: {ok,data} or {ok:false,error}.")
    parser.add_argument("--timeout", type=positive_int, default=60, help="osascript timeout in seconds. Default: 60.")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Check local dependencies and optional Apple automation access.")
    doctor.add_argument("--probe", action="store_true", help="Run lightweight Mail/Calendar automation probes; may trigger macOS permission prompts.")
    doctor.set_defaults(handler=command_doctor)

    mail = sub.add_parser("mail", help="Read Apple Mail.")
    mail_sub = mail.add_subparsers(dest="mail_command", required=True)
    recent = mail_sub.add_parser("recent", help="List recent messages.")
    recent.add_argument("--hours", type=positive_int, default=24)
    recent.add_argument("--limit", type=positive_int, default=50)
    recent.add_argument("--mailbox", default="INBOX", help="Mailbox name per account. Use empty string to scan all account mailboxes.")
    recent.set_defaults(handler=command_mail_recent)
    search = mail_sub.add_parser("search", help="Search messages by text, from:<text>, or subject:<text>.")
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=positive_int, default=25)
    search.add_argument("--mailbox", default="", help="Optional mailbox name. Default scans all account mailboxes.")
    search.set_defaults(handler=command_mail_search)

    calendar = sub.add_parser("calendar", help="Read Apple Calendar.")
    cal_sub = calendar.add_subparsers(dest="calendar_command", required=True)
    cal_list = cal_sub.add_parser("list", help="List calendars.")
    cal_list.set_defaults(handler=command_calendar_list)
    upcoming = cal_sub.add_parser("upcoming", help="List upcoming events.")
    upcoming.add_argument("--days", type=positive_int, default=1)
    upcoming.add_argument("--limit", type=positive_int, default=50)
    upcoming.add_argument("--calendar", action="append", help="Calendar name to include. Repeatable.")
    upcoming.add_argument("--calendar-timeout", type=positive_int, default=5, help="Per-calendar read timeout in seconds. Default: 5.")
    upcoming.set_defaults(handler=command_calendar_upcoming)

    report = sub.add_parser("report", help="Build triage reports from Mail and Calendar.")
    report_sub = report.add_subparsers(dest="report_command", required=True)
    daily = report_sub.add_parser("daily", help="Read recent mail and upcoming calendar into one report JSON.")
    daily.add_argument("--hours", type=positive_int, default=24)
    daily.add_argument("--days", type=positive_int, default=1)
    daily.add_argument("--mail-limit", type=positive_int, default=100)
    daily.add_argument("--event-limit", type=positive_int, default=100)
    daily.add_argument("--mailbox", default="INBOX")
    daily.add_argument("--calendar", action="append", help="Calendar name to include. Repeatable.")
    daily.add_argument("--calendar-timeout", type=positive_int, default=5, help="Per-calendar read timeout in seconds. Default: 5.")
    daily.set_defaults(handler=command_report_daily)

    raw = sub.add_parser("raw", help="Run a read-only JXA script escape hatch and parse JSON output.")
    raw.add_argument("target", choices=["mail", "calendar"], help="Declared target for auditability.")
    raw.add_argument("--script", required=True, help="Path to a JXA script that prints JSON.stringify(...).")
    raw.set_defaults(handler=command_raw)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    opts = GlobalOptions(json_output=args.json, timeout=args.timeout)
    try:
        handler: Callable[[argparse.Namespace, GlobalOptions], Any] = args.handler
        data = handler(args, opts)
        emit_success(data, json_output=opts.json_output)
        return 0
    except CliError as exc:
        emit_error(exc, json_output=opts.json_output)
        return exc.exit_code
    except KeyboardInterrupt:
        emit_error(CliError("interrupted", code="interrupted", exit_code=130), json_output=opts.json_output)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
