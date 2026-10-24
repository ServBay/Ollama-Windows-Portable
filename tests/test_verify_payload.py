import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / ".github/scripts/verify_payload.py"
BASE_FILES = ("ollama.exe", "libwinpthread-1.dll")
NATIVE_FILES = BASE_FILES + (
    "lib/ollama/llama-server.exe",
    "lib/ollama/llama-quantize.exe",
) + tuple(
    f"lib/ollama/cuda_v{version}/{dll}"
    for version in (12, 13)
    for dll in (
        "ggml-cuda.dll",
        f"cublas64_{version}.dll",
        f"cublasLt64_{version}.dll",
    )
) + ("lib/ollama/cuda_v12/cudart64_12.dll",)

spec = importlib.util.spec_from_file_location("verify_payload", SCRIPT)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class PayloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def assertPathIn(self, expected, message):
        self.assertIn(str(expected).replace("\\", "/"), str(message).replace("\\", "/"))

    def make_payload(self, files=NATIVE_FILES, empty=None):
        payload = self.root / "payload"
        payload.mkdir(exist_ok=True)
        for name in files:
            target = payload / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"" if name == empty else b"payload bytes")
        return payload

    def make_archive(self, files=NATIVE_FILES, empty=None, backslashes=False):
        archive = self.root / "payload.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as output:
            for name in files:
                entry = name.replace("/", "\\") if backslashes else name
                output.writestr(entry, b"" if name == empty else b"payload bytes")
        return archive

    def test_complete_native_directory_passes(self):
        validator.validate_payload(self.make_payload(), "native")

    def test_complete_native_archive_passes(self):
        validator.validate_archive(self.make_archive(), "native")

    def test_windows_archive_separators_pass(self):
        validator.validate_archive(self.make_archive(backslashes=True), "native")

    def test_legacy_directory_and_archive_pass_without_cuda(self):
        validator.validate_payload(self.make_payload(BASE_FILES), "legacy")
        validator.validate_archive(self.make_archive(BASE_FILES), "legacy")

    def test_cpu_only_directory_and_archive_fail(self):
        cpu_files = NATIVE_FILES[:4]
        for source, check in (
            (self.make_payload(cpu_files), validator.validate_payload),
            (self.make_archive(cpu_files), validator.validate_archive),
        ):
            with self.subTest(source=source):
                with self.assertRaises(validator.PayloadError) as error:
                    check(source, "native")
                message = str(error.exception)
                for rendered in (message, message.replace("/", "\\")):
                    self.assertPathIn("cuda_v12/ggml-cuda.dll", rendered)

    def test_each_missing_directory_file_fails_with_its_path(self):
        payload = self.make_payload()
        for name in NATIVE_FILES:
            target = payload / name
            content = target.read_bytes()
            target.unlink()
            with self.subTest(name=name):
                with self.assertRaises(validator.PayloadError) as error:
                    validator.validate_payload(payload, "native")
                self.assertPathIn(name, error.exception)
            target.write_bytes(content)

    def test_each_missing_archive_file_fails_with_its_path(self):
        for name in NATIVE_FILES:
            with self.subTest(name=name):
                archive = self.make_archive(tuple(item for item in NATIVE_FILES if item != name))
                with self.assertRaises(validator.PayloadError) as error:
                    validator.validate_archive(archive, "native")
                self.assertPathIn(name, error.exception)

    def test_each_empty_directory_file_fails_with_its_path(self):
        for name in NATIVE_FILES:
            with self.subTest(name=name):
                payload = self.make_payload(empty=name)
                with self.assertRaises(validator.PayloadError) as error:
                    validator.validate_payload(payload, "native")
                self.assertPathIn(name, error.exception)

    def test_each_empty_archive_file_fails_with_its_path(self):
        for name in NATIVE_FILES:
            with self.subTest(name=name):
                archive = self.make_archive(empty=name)
                with self.assertRaises(validator.PayloadError) as error:
                    validator.validate_archive(archive, "native")
                self.assertPathIn(name, error.exception)

    def test_corrupted_archive_data_fails_with_entry_path(self):
        archive = self.make_archive()
        data = archive.read_bytes()
        self.assertIn(b"payload bytes", data)
        archive.write_bytes(data.replace(b"payload bytes", b"damaged bytes", 1))
        with self.assertRaises(validator.PayloadError) as error:
            validator.validate_archive(archive, "native")
        self.assertPathIn("ollama.exe", error.exception)

    def test_invalid_zip_fails_with_archive_path(self):
        archive = self.root / "invalid.zip"
        archive.write_bytes(b"not a ZIP")
        with self.assertRaises(validator.PayloadError) as error:
            validator.validate_archive(archive, "native")
        self.assertPathIn(archive, error.exception)

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, arguments)],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_accepts_payload_and_archive(self):
        for option, source in (
            ("--payload", self.make_payload()),
            ("--archive", self.make_archive()),
        ):
            with self.subTest(option=option):
                result = self.run_cli(option, source, "--layout", "native")
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_cli_failure_returns_nonzero_and_identifies_missing_path(self):
        result = self.run_cli("--payload", self.make_payload(BASE_FILES), "--layout", "native")
        self.assertNotEqual(result.returncode, 0)
        self.assertPathIn("lib/ollama/llama-server.exe", result.stderr)

    def test_cli_requires_one_source_and_explicit_layout(self):
        payload = self.make_payload()
        archive = self.make_archive()
        for arguments in (
            (),
            ("--layout", "native"),
            ("--payload", payload),
            ("--payload", payload, "--archive", archive, "--layout", "native"),
            ("--payload", payload, "--layout", "unknown"),
        ):
            with self.subTest(arguments=arguments):
                self.assertNotEqual(self.run_cli(*arguments).returncode, 0)


if __name__ == "__main__":
    unittest.main()
