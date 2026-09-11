"""setup_backend.py — PrivARcy backend environment setup & doctor.

What this does, in order:
  1. Creates the expected backend folder structure.
  2. Reports the Python/venv situation.
  3. Normalizes requirements.txt to UTF-8 (see NOTE below) and installs it
     with `pip install -r requirements.txt`.
  4. Gives dlib / face_recognition / torch / transformers special-cased handling, since
     these three are the packages most likely to fail on Windows and the
     ones this script is most often run to diagnose.
  5. Re-imports every required package and prints a pass/fail report.
  6. Exits with a non-zero status if anything required is still missing,
     so this script is safe to use in CI / automated setup too.

NOTE on requirements.txt encoding:
  PowerShell's `>` / `Out-File` (the usual way this file gets regenerated,
  e.g. `pip freeze > requirements.txt`) writes UTF-16LE with a BOM by
  default. Depending on the pip version, `pip install -r requirements.txt`
  against a UTF-16 file can silently fail to parse any package (every line
  looks "unknown"/invalid), which matches the symptom this script is meant
  to catch. To avoid that trap, this script always reads requirements.txt
  with an encoding-detecting loader and re-writes a UTF-8 copy before
  handing it to pip.

Usage:
  python setup_backend.py                 # create folders, install, verify
  python setup_backend.py --check-only     # skip install, just verify
  python setup_backend.py --skip-folders   # don't touch folder structure
"""

import argparse
import importlib
import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
REQUIREMENTS_PATH = BACKEND_DIR / "requirements.txt"
REQUIREMENTS_UTF8_PATH = BACKEND_DIR / "requirements.utf8.txt"

FOLDERS = [
    "src", "app", "app/routers", "tests", "models", "data", "logs", "temp",
    "data/uploads", "data/output", "data/face_registry",
    "src/detectors", "src/ocr", "src/classifiers",
    "src/face", "src/tracker", "src/decision",
    "src/redaction", "src/video", "src/pipeline",
    "src/workers", "src/config", "src/utils",
    "src/integration", "src/review", "src/results", "src/live", "src/dataset",
    "data/review_frames", "data/dataset",
]

# import-name -> (pip spec to install if missing, human label)
# Order matters: dlib must land before face_recognition, since
# face_recognition depends on it at import time.
REQUIRED_PACKAGES = [
    ("numpy", "numpy", "NumPy"),
    ("cv2", "opencv-python", "OpenCV"),
    ("torch", "torch", "PyTorch"),
    ("ultralytics", "ultralytics", "Ultralytics (YOLO)"),
    ("transformers", "transformers", "Transformers"),
    ("dlib", None, "dlib"),                       # installed via requirements.txt (custom wheel URL)
    ("face_recognition", "face-recognition", "face_recognition"),
    ("fastapi", "fastapi", "FastAPI"),
    ("uvicorn", "uvicorn[standard]", "Uvicorn"),
]

# These are the ones most likely to be broken on a fresh Windows
# venv, so they get extra diagnosis if they're still missing afterward.
CRITICAL_PACKAGES = {"dlib", "face_recognition", "torch", "transformers"}

DLIB_HELP = """
  dlib failed to import. Common causes on Windows:
    - Python version mismatch: the dlib wheel pinned in requirements.txt
      targets a specific CPython ABI (e.g. cp311 = Python 3.11). Check that
      this venv's Python version matches what the wheel was built for.
    - No prebuilt wheel available for this Python/OS/arch combo, so pip
      tried to compile from source and needs CMake + a C++ compiler
      (Visual Studio Build Tools on Windows) that aren't installed.
  Fix options:
    - Recreate the venv with the Python version the wheel targets, or
    - Install Visual Studio Build Tools (C++ workload) + CMake and re-run
      this script so pip can build dlib from source, or
    - Install a dlib wheel that matches this interpreter from
      https://github.com/z-mahmud22/Dlib_Windows_Python3.x
"""

FACE_RECOGNITION_HELP = """
  face_recognition failed to import. It depends on dlib being importable
  first — fix dlib (see above) and re-run this script; face_recognition
  itself rarely fails independently of that.
"""

TORCH_HELP = """
  torch failed to import. TrOCR (text extraction) depends on it. Common causes:
    - No matching wheel for this Python/OS/CUDA combination — install the
      CPU build explicitly: `pip install torch --index-url
      https://download.pytorch.org/whl/cpu`, or the CUDA build matching
      your driver from https://pytorch.org/get-started/locally/.
"""

TRANSFORMERS_HELP = """
  transformers failed to import. It depends on torch being importable
  first — fix torch (see above) and re-run this script.
"""

HELP_BY_PACKAGE = {
    "dlib": DLIB_HELP,
    "face_recognition": FACE_RECOGNITION_HELP,
    "torch": TORCH_HELP,
    "transformers": TRANSFORMERS_HELP,
}


def header(text):
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)


def create_folders():
    print("\nCreating folder structure...")
    ok = True
    for folder in FOLDERS:
        target = BACKEND_DIR / folder
        try:
            target.mkdir(parents=True, exist_ok=True)
            print(f"  \u2713 Created: {folder}")
        except OSError as e:
            ok = False
            print(f"  \u2717 Failed to create {folder}: {e}")
    return ok


def report_python_env():
    print(f"\nPython version: {sys.version}")
    in_venv = hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    )
    print(f"Virtual environment active: {in_venv}")
    print(f"Python executable: {sys.executable}")
    if not in_venv:
        print(
            "  \u26a0 Not running inside a virtual environment — packages will "
            "install into the system/global Python instead of venv\\Lib. "
            "Activate the venv first: venv\\Scripts\\activate"
        )
    return in_venv


def check_pip_available():
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError as e:
        print(f"  \u2717 Could not launch pip: {e}")
        return False
    if result.returncode != 0:
        print(f"  \u2717 pip is not available: {result.stderr.strip()}")
        return False
    print(f"  \u2713 {result.stdout.strip()}")
    return True


def normalize_requirements_encoding():
    """Read requirements.txt with whatever encoding it's actually in and
    re-save a UTF-8 copy, so pip never chokes on a UTF-16 file produced by
    PowerShell's `>` redirection. Returns the path pip should use, or None
    if requirements.txt doesn't exist / couldn't be read."""
    if not REQUIREMENTS_PATH.exists():
        print(f"  \u2717 {REQUIREMENTS_PATH.name} not found in {BACKEND_DIR}")
        return None

    raw = REQUIREMENTS_PATH.read_bytes()
    text = None
    detected = None
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "latin-1"):
        try:
            text = raw.decode(encoding)
            detected = encoding
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if text is None:
        print(f"  \u2717 Could not decode {REQUIREMENTS_PATH.name} with any known encoding")
        return None

    if detected != "utf-8-sig":
        print(
            f"  \u26a0 {REQUIREMENTS_PATH.name} was encoded as {detected}, not UTF-8 "
            f"(this is what PowerShell's `>` / Out-File produces by default, and "
            f"can make pip silently fail to parse every requirement). "
            f"Writing a UTF-8 copy to {REQUIREMENTS_UTF8_PATH.name}..."
        )
    else:
        print(f"  \u2713 {REQUIREMENTS_PATH.name} is already UTF-8")

    try:
        REQUIREMENTS_UTF8_PATH.write_text(text, encoding="utf-8")
    except OSError as e:
        print(f"  \u2717 Could not write normalized requirements file: {e}")
        return None
    return REQUIREMENTS_UTF8_PATH


def pip_install_requirements(req_path):
    print(f"\nInstalling from {req_path.name} (this can take a while for torch/dlib)...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req_path)],
            cwd=str(BACKEND_DIR),
        )
    except FileNotFoundError as e:
        print(f"  \u2717 Failed to launch pip: {e}")
        return False
    except Exception as e:
        print(f"  \u2717 Unexpected error running pip: {e}")
        return False

    if result.returncode != 0:
        print(f"  \u2717 pip install exited with code {result.returncode} — see output above.")
        return False
    print("  \u2713 pip install -r requirements.txt completed")
    return True


def check_packages():
    print("\nChecking installed packages...")
    results = {}
    for import_name, pip_spec, label in REQUIRED_PACKAGES:
        try:
            module = importlib.import_module(import_name)
            version = getattr(module, "__version__", "unknown")
            print(f"  \u2713 {label} ({import_name}): {version}")
            results[import_name] = (True, version)
        except ImportError as e:
            print(f"  \u2717 {label} ({import_name}): NOT INSTALLED ({e})")
            results[import_name] = (False, str(e))
        except Exception as e:
            # Some packages (torch in particular) can raise non-ImportError
            # exceptions on a broken install (e.g. missing DLLs on Windows).
            print(f"  \u2717 {label} ({import_name}): FAILED TO LOAD ({e})")
            results[import_name] = (False, str(e))
    return results


def try_install_missing(results):
    """Best-effort direct install for anything still missing after the
    requirements.txt pass, using each package's individual pip spec."""
    missing = [
        (name, spec, label)
        for name, spec, label in REQUIRED_PACKAGES
        if not results.get(name, (False,))[0] and spec is not None
    ]
    if not missing:
        return results

    print("\nAttempting direct install for still-missing packages...")
    for import_name, pip_spec, label in missing:
        print(f"\n>>> pip install {pip_spec}")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", pip_spec],
                cwd=str(BACKEND_DIR),
            )
        except Exception as e:
            print(f"  \u2717 Failed to launch pip for {label}: {e}")
            continue
        if result.returncode != 0:
            print(f"  \u2717 pip install {pip_spec} exited with code {result.returncode}")

    return check_packages()


def print_summary(results):
    header("Summary")
    failed = [name for name, (ok, _) in results.items() if not ok]
    for import_name, (ok, info) in results.items():
        status = "OK" if ok else "MISSING/BROKEN"
        print(f"  {import_name:20s} {status}")

    if not failed:
        print("\nAll required packages are installed and importable.")
        return True

    print(f"\n{len(failed)} package(s) still missing or broken: {', '.join(failed)}")
    for name in failed:
        if name in HELP_BY_PACKAGE:
            print(HELP_BY_PACKAGE[name])
    return False


def main():
    parser = argparse.ArgumentParser(description="PrivARcy backend setup")
    parser.add_argument(
        "--check-only", action="store_true",
        help="Only verify packages; don't run pip install",
    )
    parser.add_argument(
        "--skip-folders", action="store_true",
        help="Don't create/verify the backend folder structure",
    )
    args = parser.parse_args()

    header("PrivARcy Backend Setup")

    folders_ok = True
    if not args.skip_folders:
        folders_ok = create_folders()

    report_python_env()

    header("Dependency Check")
    pip_ok = check_pip_available()

    if not args.check_only:
        if not pip_ok:
            print(
                "\n\u2717 Skipping install step because pip is unavailable. "
                "Fix pip and re-run, or use --check-only to just see current status."
            )
        else:
            req_path = normalize_requirements_encoding()
            if req_path is not None:
                pip_install_requirements(req_path)
            else:
                print(
                    "  \u2717 Skipping `pip install -r requirements.txt` — "
                    "requirements.txt could not be read/normalized."
                )

    results = check_packages()
    if not args.check_only:
        # Give the special-cased packages (dlib/face_recognition/torch/transformers) one
        # more direct shot in case the bulk `-r requirements.txt` install
        # partially failed but pip itself is fine.
        results = try_install_missing(results)

    all_ok = print_summary(results)

    header("Setup complete" if all_ok and folders_ok else "Setup finished with issues")
    print("\nTo activate the venv, run:")
    print("  venv\\Scripts\\activate")

    if not all_ok or not folders_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
