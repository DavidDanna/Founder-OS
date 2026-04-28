import sys
import types
import unittest

if "psycopg" not in sys.modules:
    fake_psycopg = types.ModuleType("psycopg")
    fake_psycopg.Connection = object
    rows_module = types.ModuleType("psycopg.rows")
    rows_module.dict_row = object()
    fake_psycopg.rows = rows_module
    fake_psycopg.connect = lambda *args, **kwargs: None
    sys.modules["psycopg"] = fake_psycopg
    sys.modules["psycopg.rows"] = rows_module

from packet_coordinator import CoordinatorError, derive_target_repo, parse_validation_commands_env


class PacketCoordinatorTests(unittest.TestCase):
    def test_parse_validation_commands_env_valid(self):
        commands = parse_validation_commands_env('["pytest -q", "npm run lint"]')
        self.assertEqual(commands, ["pytest -q", "npm run lint"])

    def test_parse_validation_commands_env_rejects_blank(self):
        with self.assertRaises(CoordinatorError):
            parse_validation_commands_env('["pytest -q", " "]')

    def test_parse_validation_commands_env_accepts_multiline(self):
        commands = parse_validation_commands_env("npm install\nnpm run lint\nnpm run build")
        self.assertEqual(commands, ["npm install", "npm run lint", "npm run build"])

    def test_derive_target_repo_from_github_url(self):
        self.assertEqual(
            derive_target_repo("https://github.com/acme/founder-os.git", "fallback"),
            "founder-os",
        )

    def test_derive_target_repo_falls_back(self):
        self.assertEqual(derive_target_repo(None, "workspace-repo"), "workspace-repo")


if __name__ == "__main__":
    unittest.main()
