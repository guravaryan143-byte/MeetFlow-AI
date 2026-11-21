"""Startup-safety tests. Stdlib only (no FastAPI needed)."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def run(code: str, **env):
    full = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "JWT_SECRET_KEY", "ENVIRONMENT")}
    full.update(env)
    return subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=full, capture_output=True, text=True)


class ConfigGuardTests(unittest.TestCase):
    def test_production_rejects_default_jwt_secret(self):
        r = run("import app.core.config", ENVIRONMENT="production")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("JWT_SECRET_KEY", r.stderr)

    def test_production_accepts_strong_secret(self):
        r = run("import app.core.config", ENVIRONMENT="production", JWT_SECRET_KEY="x" * 40)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_postgres_url_is_supported_by_database_adapter(self):
        r = run("import app.db.database", DATABASE_URL="postgresql+psycopg2://u:p@h:5432/db")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_adapters_flag_simulated(self):
        from app.integrations.adapters import ADAPTER_REGISTRY
        for name, adapter in ADAPTER_REGISTRY.items():
            res = adapter.execute("EXTERNAL_TASK_CREATE", {"title": "t"}, "key-1", {})
            self.assertTrue(res["simulated"], name)


if __name__ == "__main__":
    unittest.main()
