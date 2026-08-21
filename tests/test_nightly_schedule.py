import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTROL_SCRIPT = PROJECT_ROOT / "bin" / "nightly-schedule"
SOURCE_PLIST = (
    PROJECT_ROOT
    / "launchd"
    / "com.marcus.ionna-rechargery-tracker.plist"
)


class NightlyScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temporary_directory.name)
        self.home = self.temp_path / "home"
        self.fake_bin = self.temp_path / "bin"
        self.launchctl_state = self.temp_path / "launchctl-loaded"
        self.launchctl_log = self.temp_path / "launchctl.log"
        self.home.mkdir()
        self.fake_bin.mkdir()

        fake_launchctl = self.fake_bin / "launchctl"
        fake_launchctl.write_text(
            """#!/bin/zsh
print -r -- \"$*\" >> \"${LAUNCHCTL_LOG}\"
case \"${1:-}\" in
  print) [[ -f \"${LAUNCHCTL_STATE}\" ]] ;;
  bootstrap) : > \"${LAUNCHCTL_STATE}\" ;;
  bootout) rm -f \"${LAUNCHCTL_STATE}\" ;;
  kickstart) ;;
  *) exit 2 ;;
esac
""",
            encoding="utf-8",
        )
        fake_launchctl.chmod(0o755)
        self.environment = {
            **os.environ,
            "HOME": str(self.home),
            "LAUNCHCTL_LOG": str(self.launchctl_log),
            "LAUNCHCTL_STATE": str(self.launchctl_state),
            "PATH": f"{self.fake_bin}:{os.environ['PATH']}",
        }

    def tearDown(self):
        self.temporary_directory.cleanup()

    def run_control(self, command):
        return subprocess.run(
            [str(CONTROL_SCRIPT), command],
            cwd=PROJECT_ROOT,
            env=self.environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_plist_runs_once_daily_with_project_environment(self):
        with SOURCE_PLIST.open("rb") as plist_file:
            configuration = plistlib.load(plist_file)

        self.assertEqual(
            configuration["Label"], "com.marcus.ionna-rechargery-tracker"
        )
        self.assertEqual(
            configuration["StartCalendarInterval"], {"Hour": 3, "Minute": 0}
        )
        self.assertFalse(configuration["RunAtLoad"])
        self.assertFalse(configuration["KeepAlive"])
        self.assertEqual(
            Path(configuration["ProgramArguments"][0]),
            PROJECT_ROOT / ".venv" / "bin" / "python",
        )
        self.assertEqual(Path(configuration["WorkingDirectory"]), PROJECT_ROOT)

    def test_on_run_status_and_off_lifecycle(self):
        status = self.run_control("status")
        self.assertEqual(status.returncode, 0)
        self.assertIn("OFF", status.stdout)

        enabled = self.run_control("on")
        self.assertEqual(enabled.returncode, 0, enabled.stderr)
        self.assertIn("ON", enabled.stdout)
        installed_plist = (
            self.home
            / "Library"
            / "LaunchAgents"
            / "com.marcus.ionna-rechargery-tracker.plist"
        )
        self.assertTrue(installed_plist.exists())
        self.assertTrue(self.launchctl_state.exists())

        status = self.run_control("status")
        self.assertIn("ON", status.stdout)
        started = self.run_control("run")
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertIn("Started one collection", started.stdout)
        self.assertIn("kickstart -k", self.launchctl_log.read_text(encoding="utf-8"))

        disabled = self.run_control("off")
        self.assertEqual(disabled.returncode, 0, disabled.stderr)
        self.assertIn("OFF", disabled.stdout)
        self.assertFalse(installed_plist.exists())
        self.assertFalse(self.launchctl_state.exists())

    def test_run_requires_the_schedule_to_be_on(self):
        result = self.run_control("run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Run 'bin/nightly-schedule on' first", result.stderr)


if __name__ == "__main__":
    unittest.main()
