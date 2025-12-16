import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


if getattr(sys, "frozen", False):
    PYTHON = ROOT / "_internal" / "python.exe"
else:
    PYTHON = sys.executable

LABELME_CMD = [
    str(PYTHON),
    "-m",
    "labelme",
]

MIDDLEWARE_CMD = [
    str(PYTHON),
    str(ROOT / "middleware" / "app.py"),
]


def main():
    print("[SUCCESS] Both processes started")
    print("[INFO] Close either window to exit all")

    labelme_proc = subprocess.Popen(
        LABELME_CMD,
        cwd=ROOT,
    )

    middleware_proc = subprocess.Popen(
        MIDDLEWARE_CMD,
        cwd=ROOT,
    )

    try:
        labelme_proc.wait()
    finally:
        middleware_proc.terminate()


if __name__ == "__main__":
    main()
