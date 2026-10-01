"""Tests run against an isolated temp database — never the real data/jobs.db.

Must be imported by pytest before any test module touches `app.*`, so the env
var lands before `app.config` reads it.
"""

import os
import tempfile
from pathlib import Path

_tmp_dir = tempfile.mkdtemp(prefix="linkedin-laya-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(_tmp_dir) / 'test.db'}")
