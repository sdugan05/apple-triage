import json
import unittest
from unittest import mock

from apple_triage import main as cli


class CliTests(unittest.TestCase):
    def test_doctor_without_probe_does_not_touch_apple_apps(self):
        args = cli.build_parser().parse_args(["--json", "doctor"])
        opts = cli.GlobalOptions(json_output=True, timeout=1)
        with mock.patch.object(cli, "run_osascript_jxa") as runner:
            data = cli.command_doctor(args, opts)
        runner.assert_not_called()
        self.assertEqual(data["version"], cli.VERSION)
        self.assertFalse(data["privacy"]["writes"])

    def test_daily_report_summary_keeps_actionable_buckets(self):
        mail = {
            "messages": [
                {"subject": "A", "read": False, "flagged": False},
                {"subject": "B", "read": True, "flagged": True},
            ]
        }
        calendar = {"events": [{"summary": "Standup"}]}
        report = cli.summarize_daily(mail, calendar)
        self.assertEqual(report["inputs"]["mailCount"], 2)
        self.assertEqual(report["inputs"]["unreadMailCount"], 1)
        self.assertEqual(report["inputs"]["flaggedMailCount"], 1)
        self.assertEqual(report["inputs"]["calendarEventCount"], 1)
        self.assertEqual(report["mail"]["unread"][0]["subject"], "A")
        self.assertEqual(report["mail"]["flagged"][0]["subject"], "B")

    def test_json_error_shape_is_stable(self):
        err = cli.CliError("Nope", code="nope", details={"x": 1})
        with mock.patch("sys.stderr") as stderr:
            cli.emit_error(err, json_output=True)
        payload = json.loads("".join(call.args[0] for call in stderr.write.call_args_list if call.args))
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "nope")
        self.assertEqual(payload["error"]["details"], {"x": 1})

    def test_parser_rejects_zero_limits(self):
        with self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["mail", "recent", "--limit", "0"])


if __name__ == "__main__":
    unittest.main()
