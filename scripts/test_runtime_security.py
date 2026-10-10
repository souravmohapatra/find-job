"""Offline checks for startup compatibility without dropping payload hardening."""

import copy
import os
import runpy
import unittest
from pathlib import Path
from unittest.mock import patch

from backup import archive_command
from deployment_config import configuration, runtime_security_option

check = runpy.run_path(str(Path(__file__).with_name("check-deployment.py")))["check"]


class RuntimeSecurityTests(unittest.TestCase):
    def test_default_retains_docker_and_payload_hardening(self):
        with patch.dict(os.environ):
            os.environ.pop("DOCKER_NO_NEW_PRIVILEGES", None)
            config = configuration()
            check(config)
            self.assertEqual(runtime_security_option(config), "no-new-privileges:true")

    def test_snap_exception_keeps_payload_hardening_and_helper_setting(self):
        with patch.dict(os.environ, DOCKER_NO_NEW_PRIVILEGES="false"):
            config = configuration()
            check(config)
            self.assertEqual(runtime_security_option(config), "no-new-privileges:false")
            command = archive_command("synthetic-volume", "synthetic-helper")
            self.assertIn("no-new-privileges:false", command)
            index = command.index("setpriv")
            self.assertEqual(command[index : index + 3], ["setpriv", "--no-new-privs", "python"])
            unsafe = copy.deepcopy(config)
            unsafe["services"]["fetcher"]["entrypoint"] = ["uvicorn"]
            with self.assertRaisesRegex(AssertionError, "before its payload"):
                check(unsafe)
            unsafe = copy.deepcopy(config)
            unsafe["services"]["worker"]["security_opt"] = []
            with self.assertRaisesRegex(AssertionError, "Inconsistent"):
                check(unsafe)
            unsafe = copy.deepcopy(config)
            unsafe["services"]["api"]["healthcheck"]["test"] = ["CMD", "python"]
            with self.assertRaisesRegex(AssertionError, "Health checks"):
                check(unsafe)
            unsafe = copy.deepcopy(config)
            unsafe["services"]["api"].pop("command")
            with self.assertRaisesRegex(AssertionError, "explicit service command"):
                check(unsafe)
            unsafe = copy.deepcopy(config)
            unsafe["services"]["api"]["tmpfs"] = ["/tmp:size=128m", "mode=1777"]
            with self.assertRaisesRegex(AssertionError, "tmpfs options"):
                check(unsafe)
            self.assertIn(
                "no-new-privileges:false",
                archive_command(
                    "synthetic-volume", "synthetic-helper", runtime_security_option(config)
                ),
            )

    def test_invalid_setting_is_rejected_before_runtime_work(self):
        with patch.dict(os.environ, DOCKER_NO_NEW_PRIVILEGES="invalid"):
            with self.assertRaisesRegex(ValueError, "true or false"):
                runtime_security_option(configuration())

    def test_fetch_isolation_enabled_without_evidence_is_rejected(self):
        config = configuration()
        config["services"]["fetcher"]["environment"]["JOBFINDER_FETCH_ISOLATION_VERIFIED"] = "true"
        with patch("pathlib.Path.exists", return_value=False):
            with self.assertRaisesRegex(AssertionError, "cannot be 'true' without verified"):
                check(config)

if __name__ == "__main__":
    unittest.main()
