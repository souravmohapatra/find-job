"""Synthetic recovery regression tests; no production data or services are used."""

import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import backup
import restore
from recovery import PAYLOADS, VOLUMES, ciphertext_record, encrypt_bytes, encrypt_command, verify


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="jobfinder-recovery-test-")
        cls.root = Path(cls.temp.name)
        cls.home = cls.root / "keyring"
        cls.home.mkdir(mode=0o700)
        subprocess.run(
            [
                "gpg",
                "--no-options",
                "--homedir",
                str(cls.home),
                "--batch",
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                "",
                "--quick-generate-key",
                "Synthetic Backup <backup@example.invalid>",
                "rsa2048",
                "encr",
                "1d",
            ],
            capture_output=True,
            check=True,
            timeout=60,
        )
        keys = subprocess.run(
            ["gpg", "--homedir", str(cls.home), "--with-colons", "--list-keys"],
            capture_output=True,
            text=True,
            check=True,
        )
        cls.recipient = next(
            line.split(":")[9] for line in keys.stdout.splitlines() if line.startswith("fpr:")
        )

    @classmethod
    def tearDownClass(cls):
        subprocess.run(
            ["gpgconf", "--homedir", str(cls.home), "--kill", "gpg-agent"], capture_output=True
        )
        cls.temp.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=self.root)
        self.folder = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def snapshot(self):
        payloads = {}
        for name in PAYLOADS:
            path = self.folder / name
            encrypt_command(
                [sys.executable, "-c", "print('Synthetic private content')"],
                path,
                self.home,
                self.recipient,
            )
            self.assertNotIn(b"Synthetic private content", path.read_bytes())
            payloads[name] = ciphertext_record(path)
        manifest = {"format": 1, "payloads": payloads}
        encrypt_bytes(
            json.dumps(manifest).encode(),
            self.folder / "manifest.json.gpg",
            self.home,
            self.recipient,
        )
        return manifest

    def test_encrypted_stream_and_verified_manifest(self):
        expected = self.snapshot()
        self.assertEqual(verify(self.folder, self.home), expected)

    def test_encryption_needs_only_the_public_recipient_key(self):
        public_home = self.folder / "public-keyring"
        public_home.mkdir(mode=0o700)
        exported = subprocess.run(
            ["gpg", "--homedir", str(self.home), "--export", self.recipient],
            capture_output=True,
            check=True,
            timeout=30,
        )
        subprocess.run(
            ["gpg", "--no-options", "--homedir", str(public_home), "--batch", "--import"],
            input=exported.stdout,
            capture_output=True,
            check=True,
            timeout=30,
        )
        target = self.folder / "public-only.gpg"
        encrypt_bytes(b"Synthetic public-key-only backup", target, public_home, self.recipient)
        restored = subprocess.run(
            [
                "gpg",
                "--no-options",
                "--homedir",
                str(self.home),
                "--batch",
                "--decrypt",
                str(target),
            ],
            capture_output=True,
            check=True,
            timeout=30,
        )
        self.assertEqual(restored.stdout, b"Synthetic public-key-only backup")

    def test_corruption_is_rejected(self):
        self.snapshot()
        path = self.folder / PAYLOADS[0]
        value = bytearray(path.read_bytes())
        value[-12] ^= 1
        path.write_bytes(value)
        with self.assertRaisesRegex(ValueError, "payload checks"):
            verify(self.folder, self.home)

    def test_cipher_integrity_is_checked_even_if_manifest_hash_is_replaced(self):
        manifest = self.snapshot()
        path = self.folder / PAYLOADS[0]
        data = bytearray(path.read_bytes())
        data[-12] ^= 1
        path.write_bytes(data)
        manifest["payloads"][path.name] = ciphertext_record(path)
        (self.folder / "manifest.json.gpg").unlink()
        encrypt_bytes(
            json.dumps(manifest).encode(),
            self.folder / "manifest.json.gpg",
            self.home,
            self.recipient,
        )
        with self.assertRaisesRegex(ValueError, "payload verification failed"):
            verify(self.folder, self.home)

    def test_symlink_payload_is_rejected(self):
        self.snapshot()
        path = self.folder / PAYLOADS[0]
        path.unlink()
        path.symlink_to(self.folder / PAYLOADS[1])
        with self.assertRaisesRegex(ValueError, "payload checks"):
            verify(self.folder, self.home)

    @unittest.skipUnless(
        os.environ.get("JOBFINDER_RECOVERY_TEST_DB_CONTAINER"),
        "Opt-in disposable PostgreSQL stream roundtrip",
    )
    def test_real_postgres_encrypted_stream_roundtrip(self):
        container = os.environ["JOBFINDER_RECOVERY_TEST_DB_CONTAINER"]

        def docker(*args, data=None):
            return subprocess.run(
                ["docker", *args], input=data, capture_output=True, check=True, timeout=30
            ).stdout

        inspection = json.loads(docker("inspect", container))[0]
        labels = inspection["Config"]["Labels"]
        self.assertEqual(labels["com.docker.compose.project"], "jobfinder-test")
        self.assertEqual(labels["com.docker.compose.service"], "db")
        prefix = "jobfinder_test_recovery_" + uuid4().hex[:12]
        source, destination = prefix + "_source", prefix + "_restored"
        created = []
        try:
            for name in (source, destination):
                docker("exec", container, "createdb", "-p", "55439", "-U", "jobfinder", name)
                created.append(name)
            docker(
                "exec",
                "-i",
                container,
                "psql",
                "-p",
                "55439",
                "-U",
                "jobfinder",
                "-d",
                source,
                "-v",
                "ON_ERROR_STOP=1",
                data=(
                    b"CREATE TABLE sample(id int PRIMARY KEY, description text); "
                    b"INSERT INTO sample VALUES (1, 'Synthetic private content');"
                ),
            )
            target = self.folder / "database.dump.gpg"
            encrypt_command(
                [
                    "docker",
                    "exec",
                    container,
                    "pg_dump",
                    "-p",
                    "55439",
                    "-U",
                    "jobfinder",
                    "-d",
                    source,
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                ],
                target,
                self.home,
                self.recipient,
            )
            decrypt = [
                "gpg",
                "--no-options",
                "--homedir",
                str(self.home),
                "--batch",
                "--decrypt",
                str(target),
            ]
            subprocess.run(
                decrypt,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=30,
            )
            with subprocess.Popen(
                decrypt, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            ) as reader:
                restored = subprocess.run(
                    [
                        "docker",
                        "exec",
                        "-i",
                        container,
                        "pg_restore",
                        "-p",
                        "55439",
                        "-U",
                        "jobfinder",
                        "-d",
                        destination,
                        "--single-transaction",
                        "--no-owner",
                        "--no-acl",
                    ],
                    stdin=reader.stdout,
                    capture_output=True,
                    timeout=30,
                )
                self.assertEqual(restored.returncode, 0)
                self.assertEqual(reader.wait(timeout=30), 0)
            count = docker(
                "exec",
                container,
                "psql",
                "-p",
                "55439",
                "-U",
                "jobfinder",
                "-d",
                destination,
                "-Atc",
                "SELECT count(*) FROM sample WHERE id=1 "
                "AND description='Synthetic private content'",
            )
            self.assertEqual(count.strip(), b"1")
        finally:
            for name in reversed(created):
                docker("exec", container, "dropdb", "-p", "55439", "-U", "jobfinder", name)

    @unittest.skipUnless(
        os.environ.get("JOBFINDER_RECOVERY_TEST_DB_CONTAINER"),
        "Opt-in disposable Docker volume archive",
    )
    def test_real_volume_archive_encryption_preserves_private_file(self):
        volume = "jobfinder-recovery-test-" + uuid4().hex[:12]
        helper = volume + "-reader"

        def docker(*args):
            return subprocess.run(["docker", *args], capture_output=True, check=True, timeout=30)

        docker("volume", "create", "--label", "jobfinder.synthetic-recovery=true", volume)
        try:
            docker(
                "run",
                "--rm",
                "--pull",
                "never",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--cap-add",
                "CHOWN",
                "--mount",
                f"type=volume,src={volume},dst=/data",
                backup.HELPER,
                "python",
                "-c",
                "import os,pathlib; p=pathlib.Path('/data/synthetic CV.txt'); "
                "p.write_text('Synthetic private content'); os.chmod(p,0o600); "
                "os.chown(p,10001,10001); os.chmod('/data',0o700); "
                "os.chown('/data',10001,10001)",
            )
            target = self.folder / "documents.tar.gpg"
            encrypt_command(
                backup.archive_command(volume, helper), target, self.home, self.recipient
            )
            self.assertNotIn(b"Synthetic private content", target.read_bytes())
            decrypt = [
                "gpg",
                "--no-options",
                "--homedir",
                str(self.home),
                "--batch",
                "--decrypt",
                str(target),
            ]
            with subprocess.Popen(
                decrypt, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            ) as reader:
                with tarfile.open(fileobj=reader.stdout, mode="r|") as archive:
                    files = [
                        (entry, archive.extractfile(entry).read())
                        for entry in archive
                        if entry.isfile()
                    ]
                self.assertEqual(len(files), 1)
                self.assertEqual(files[0][0].mode, 0o600)
                self.assertEqual(files[0][1], b"Synthetic private content")
                reader.stdout.close()
                self.assertEqual(reader.wait(timeout=30), 0)
        finally:
            subprocess.run(["docker", "rm", "-f", helper], capture_output=True, timeout=30)
            docker("volume", "rm", volume)

    def test_restore_stream_rejects_consumer_failure(self):
        target = self.folder / "payload.gpg"
        encrypt_bytes(b"Synthetic data", target, self.home, self.recipient)
        with self.assertRaisesRegex(RuntimeError, "restore 7"):
            restore.decrypt_into(
                target,
                self.home,
                [sys.executable, "-c", "import sys; sys.stdin.read(); sys.exit(7)"],
            )

    def test_restore_archive_rejects_links_and_traversal(self):
        destination = self.folder / "unpacked"
        destination.mkdir()
        for name, kind in [("../outside", tarfile.REGTYPE), ("link", tarfile.SYMTYPE)]:
            data = io.BytesIO()
            with tarfile.open(fileobj=data, mode="w") as archive:
                entry = tarfile.TarInfo(name)
                entry.type = kind
                entry.linkname = "/tmp"
                archive.addfile(entry)
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    restore.EXTRACT.replace("'/restore'", repr(str(destination))),
                ],
                input=data.getvalue(),
                capture_output=True,
                timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.folder / "outside").exists())
        self.assertFalse((destination / "link").exists())

    @unittest.skipUnless(
        os.environ.get("JOBFINDER_RECOVERY_TEST_DB_CONTAINER"), "Opt-in full isolated restore drill"
    )
    def test_complete_isolated_restore(self):
        container = os.environ["JOBFINDER_RECOVERY_TEST_DB_CONTAINER"]
        prefix = "jobfinder_test_recovery_" + uuid4().hex[:12]

        def docker(*args, data=None):
            return subprocess.run(
                ["docker", *args], input=data, capture_output=True, check=True, timeout=60
            ).stdout

        inspection = json.loads(docker("inspect", container))[0]
        self.assertEqual(
            inspection["Config"]["Labels"]["com.docker.compose.project"], "jobfinder-test"
        )
        record = self.folder / "record"
        record.mkdir(mode=0o700)
        check_container = prefix + "-check"
        docker("exec", container, "createdb", "-p", "55439", "-U", "jobfinder", prefix)
        try:
            docker(
                "exec",
                "-i",
                container,
                "psql",
                "-p",
                "55439",
                "-U",
                "jobfinder",
                "-d",
                prefix,
                "-v",
                "ON_ERROR_STOP=1",
                data=(b"CREATE TABLE sample(id int PRIMARY KEY); INSERT INTO sample VALUES (42);"),
            )
            encrypt_command(
                [
                    "docker",
                    "exec",
                    container,
                    "pg_dump",
                    "-p",
                    "55439",
                    "-U",
                    "jobfinder",
                    "-d",
                    prefix,
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                ],
                self.folder / PAYLOADS[0],
                self.home,
                self.recipient,
            )
            data = io.BytesIO()
            with tarfile.open(fileobj=data, mode="w") as archive:
                entry = tarfile.TarInfo("synthetic.txt")
                content = b"Synthetic restored content"
                entry.size, entry.mode = len(content), 0o600
                archive.addfile(entry, io.BytesIO(content))
            for name in VOLUMES:
                encrypt_bytes(
                    data.getvalue(), self.folder / f"{name}.tar.gpg", self.home, self.recipient
                )
            encrypt_bytes(
                json.dumps(
                    {
                        "format": 1,
                        "payloads": {
                            name: ciphertext_record(self.folder / name) for name in PAYLOADS
                        },
                    }
                ).encode(),
                self.folder / "manifest.json.gpg",
                self.home,
                self.recipient,
            )
            journal = restore.restore(self.folder, self.home, record)
            self.assertEqual(journal["state"], "restored_isolated")
            self.assertEqual(journal["container_cleanup_failed"], [])
            self.assertNotIn(
                journal["container"], docker("ps", "-a", "--format", "{{.Names}}").decode()
            )
            for logical in VOLUMES:
                result = docker(
                    "run",
                    "--rm",
                    "--pull",
                    "never",
                    "--network",
                    "none",
                    "--read-only",
                    "--cap-drop",
                    "ALL",
                    "--user",
                    "10001:10001",
                    "--mount",
                    f"type=volume,src={journal['volumes'][logical]},dst=/data,readonly",
                    backup.HELPER,
                    "python",
                    "-c",
                    "from pathlib import Path; p=Path('/data/synthetic.txt'); "
                    "assert p.read_bytes()==b'Synthetic restored content'; "
                    "assert p.stat().st_mode & 0o777 == 0o600",
                )
                self.assertEqual(result, b"")
            image = restore.configuration()["services"]["db"]["image"]
            # Single-user postgres can report SQL errors with exit 0; inspect its result explicitly.
            result = docker(
                "run",
                "--rm",
                "--name",
                check_container,
                "--pull",
                "never",
                "--network",
                "none",
                "--user",
                "postgres",
                "--entrypoint",
                "postgres",
                "--mount",
                f"type=volume,src={journal['volumes']['postgres']},dst=/var/lib/postgresql/data",
                "-i",
                image,
                "--single",
                "-D",
                "/var/lib/postgresql/data",
                "jobfinder",
                data=b"SELECT id FROM sample;\n",
            )
            self.assertIn(b"42", result)
        finally:
            subprocess.run(["docker", "rm", "-f", check_container], capture_output=True, timeout=30)
            journal_path = record / "operation.json"
            if journal_path.exists():
                journal = json.loads(journal_path.read_text())
                subprocess.run(
                    ["docker", "rm", "-f", journal["container"]], capture_output=True, timeout=30
                )
                for volume in journal["created_volumes"]:
                    docker("volume", "rm", volume)
            docker("exec", container, "dropdb", "-p", "55439", "-U", "jobfinder", prefix)

    def test_layout_drift_is_rejected_before_stopping_services(self):
        states = [
            {"Service": name, "State": "running", "ID": name} for name in (*backup.WRITERS, "db")
        ]
        config = {
            "name": "synthetic",
            "services": {
                name: {"volumes": [{"type": "volume", "source": "data", "target": "/data"}]}
                for name in (*backup.WRITERS, "db")
            },
            "volumes": {"data": {"name": "expected"}},
        }
        calls = []

        def run(command, **kwargs):
            calls.append(command)
            if "ps" in command:
                return json.dumps(states)
            return json.dumps(
                [
                    {
                        "Config": {
                            "Labels": {
                                "com.docker.compose.project": "synthetic",
                                "com.docker.compose.service": command[-1],
                            }
                        },
                        "Mounts": [{"Type": "volume", "Name": "wrong", "Destination": "/data"}],
                        "Image": "synthetic-image",
                    }
                ]
            )

        with patch.object(backup, "run", side_effect=run):
            with self.assertRaisesRegex(ValueError, "layout differs"):
                backup.capture(["compose"], config, self.folder, self.home, self.recipient)
        self.assertFalse(any("stop" in command for command in calls))

    def test_failed_source_never_counts_as_successful_encryption(self):
        with self.assertRaisesRegex(RuntimeError, "source exit 7"):
            encrypt_command(
                [sys.executable, "-c", "print('partial'); raise SystemExit(7)"],
                self.folder / "partial.gpg",
                self.home,
                self.recipient,
            )

    def test_stream_timeout_is_bounded(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            encrypt_command(
                [sys.executable, "-c", "import time; time.sleep(20)"],
                self.folder / "timeout.gpg",
                self.home,
                self.recipient,
                timeout=1,
            )

    def test_source_failure_recovers_only_previously_running_services(self):
        calls = []
        initial = [
            {"Service": name, "State": state}
            for name, state in [
                ("db", "running"),
                ("api", "running"),
                ("worker", "running"),
                ("ai-worker", "exited"),
                ("ntfy", "running"),
            ]
        ]

        def run(command, **kwargs):
            calls.append(command)
            if "ps" in command:
                return json.dumps(
                    initial
                    if sum("ps" in call for call in calls) == 1
                    else [
                        {
                            "Service": row["Service"],
                            "State": "running" if row["Service"] == "db" else "exited",
                        }
                        for row in initial
                    ]
                )
            return ""

        config = {
            "name": "synthetic",
            "volumes": {name: {"name": "synthetic_" + name} for name in VOLUMES},
        }
        with (
            patch.object(backup, "run", side_effect=run),
            patch.object(backup, "validate_layout", return_value={}),
            patch.object(backup, "encrypt_bytes"),
            patch.object(
                backup, "encrypt_command", side_effect=RuntimeError("Synthetic source failure")
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "Synthetic source failure"):
                backup.capture(["compose"], config, self.folder, self.home, self.recipient)
        self.assertEqual([call[-1] for call in calls if "start" in call], ["ntfy", "api", "worker"])
        self.assertEqual(
            json.loads((self.folder / "operation.json").read_text())["state"], "services_resumed"
        )

    def test_partial_stop_failure_still_attempts_every_restart(self):
        calls = []

        def run(command, **kwargs):
            calls.append(command)
            if "ps" in command:
                return json.dumps(
                    [{"Service": name, "State": "running"} for name in ["db", "api", "worker"]]
                )
            if "stop" in command or ("start" in command and command[-1] == "api"):
                raise RuntimeError("Synthetic Docker failure")
            return ""

        config = {"name": "synthetic", "volumes": {name: {"name": name} for name in VOLUMES}}
        with (
            patch.object(backup, "run", side_effect=run),
            patch.object(backup, "validate_layout", return_value={}),
            patch.object(backup, "encrypt_bytes"),
        ):
            with self.assertRaisesRegex(RuntimeError, "restart failed: api"):
                backup.capture(["compose"], config, self.folder, self.home, self.recipient)
        self.assertIn(["compose", "start", "--wait", "--wait-timeout", "60", "worker"], calls)
        self.assertEqual(
            json.loads((self.folder / "operation.json").read_text())["restart_failed"], ["api"]
        )


if __name__ == "__main__":
    unittest.main()
