import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if "psycopg" not in sys.modules:
    fake_psycopg = types.ModuleType("psycopg")
    fake_psycopg.Connection = object
    rows_module = types.ModuleType("psycopg.rows")
    rows_module.dict_row = object()
    fake_psycopg.rows = rows_module
    fake_psycopg.connect = lambda *args, **kwargs: None
    sys.modules["psycopg"] = fake_psycopg
    sys.modules["psycopg.rows"] = rows_module

from execution_worker import (
    PacketValidationError,
    parse_execution_result,
    parse_validation_commands,
    resolve_repo_path,
    should_retry,
)


class ExecutionWorkerUnitTests(unittest.TestCase):
    def test_parse_validation_commands_accepts_list(self):
        commands = parse_validation_commands(["npm test", "npm run lint"])
        self.assertEqual(commands, ["npm test", "npm run lint"])

    def test_parse_validation_commands_accepts_json_string(self):
        raw = json.dumps(["pytest -q"])
        commands = parse_validation_commands(raw)
        self.assertEqual(commands, ["pytest -q"])

    def test_parse_validation_commands_rejects_invalid_shape(self):
        with self.assertRaises(PacketValidationError):
            parse_validation_commands({"bad": "shape"})

    def test_parse_validation_commands_rejects_empty_values(self):
        with self.assertRaises(PacketValidationError):
            parse_validation_commands(["pytest", "   "])

    def test_should_retry_true_before_max(self):
        packet = {"attempts": 0, "max_attempts": 3}
        self.assertTrue(should_retry(packet))

    def test_should_retry_false_at_max(self):
        packet = {"attempts": 2, "max_attempts": 3}
        self.assertFalse(should_retry(packet))

    def test_should_retry_guards_invalid_max_attempts(self):
        packet = {"attempts": 0, "max_attempts": 0}
        self.assertFalse(should_retry(packet))

    def test_resolve_repo_path_requires_existing_nested_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo = root / "my-repo"
            repo.mkdir()

            resolved = resolve_repo_path(str(root), "my-repo")
            self.assertEqual(resolved, str(repo.resolve()))

    def test_resolve_repo_path_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with self.assertRaises(PacketValidationError):
                resolve_repo_path(str(root), "../escape")

    def test_resolve_repo_path_supports_repo_map(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "root"
            mapped = Path(tmpdir) / "mapped"
            root.mkdir()
            mapped.mkdir()
            resolved = resolve_repo_path(str(root), "AFDP", {"AFDP": str(mapped)})
            self.assertEqual(resolved, str(mapped.resolve()))

    def test_parse_execution_result_returns_empty_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = parse_execution_result(tmpdir, ".founder_os/execution_result.json")
            self.assertEqual(result, {})

    def test_parse_execution_result_reads_json_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result_file = Path(tmpdir) / ".founder_os" / "execution_result.json"
            result_file.parent.mkdir(parents=True, exist_ok=True)
            result_file.write_text('{"branch":"founder-os/a","commit_sha":"abc123","pr_url":"https://github.com/acme/x/pull/1","pr_number":1}')
            result = parse_execution_result(tmpdir, ".founder_os/execution_result.json")
            self.assertEqual(result["pr_number"], 1)


if __name__ == "__main__":
    unittest.main()
