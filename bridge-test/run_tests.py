"""Run regression checks with the current interpreter."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parent
cache_dir = tempfile.TemporaryDirectory(prefix="aitu-test-db-")
os.environ["BRIDGE_DB_PATH"] = str(Path(cache_dir.name)/"test.sqlite3")
for script in ["test_student_cache.py","test_startup.py","test_login_flow.py","test_materials.py","test_ui.py","test_multiuser.py","test_attendance.py","test_session_continuity.py","smoke_test.py"]:
    print("\nRunning "+script,flush=True)
    subprocess.run([sys.executable,str(ROOT/script)],check=True,env=dict(os.environ,BRIDGE_HEADLESS="1"))
cache_dir.cleanup()
print("\nAll available checks passed; inspect explicit SKIP notices.")
