#!/usr/bin/env python3
"""Start the Foundry API server. Usage: python run.py"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
PORT = os.environ.get("FOUNDRY_PORT", "8000")

env = os.environ.copy()
env["PYTHONPATH"] = f"{BACKEND}{os.pathsep}{env.get('PYTHONPATH', '')}"

venv_uvicorn = ROOT / "venv" / "bin" / "uvicorn"
if venv_uvicorn.is_file() and os.access(venv_uvicorn, os.X_OK):
    cmd = [str(venv_uvicorn)]
else:
    cmd = [sys.executable, "-m", "uvicorn"]

cmd += [
    "foundry.api.app:app",
    "--host", "0.0.0.0",
    "--port", PORT,
    "--reload",
]

print(f"Starting Foundry on http://localhost:{PORT}")
os.chdir(ROOT)
raise SystemExit(subprocess.call(cmd, env=env))
