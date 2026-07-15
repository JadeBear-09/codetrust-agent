#!/usr/bin/env python3
"""One-command local launcher for CodeTrust."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import venv
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Set up and run CodeTrust locally.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-open", action="store_true", help="Do not open a browser")
    parser.add_argument(
        "--setup-only",
        action="store_true",
        help="Install dependencies, then exit",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Install developer dependencies, then run tests and lint",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = _prepare_environment(development=args.check)

    if args.check:
        print("\nChecking CodeTrust...", flush=True)
        _run([*command, "pytest"])
        _run([*command, "ruff", "check", "."])
        print("\nReady: tests and lint passed.", flush=True)
        return 0

    if args.setup_only:
        print("\nReady. Start dashboard with: python3 start.py", flush=True)
        return 0

    url = f"http://{args.host}:{args.port}"
    if _codetrust_running(url):
        print(f"\nCodeTrust already running at {url}", flush=True)
        if not args.no_open:
            webbrowser.open(url)
        return 0
    if not args.no_open:
        threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()

    print(f"\nCodeTrust ready at {url}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    try:
        return _run(
            [
                *command,
                "codetrust.cli",
                "serve",
                "--host",
                args.host,
                "--port",
                str(args.port),
            ]
        ).returncode
    except KeyboardInterrupt:
        print("\nCodeTrust stopped.", flush=True)
        return 0


def _prepare_environment(*, development: bool) -> list[str]:
    uv = shutil.which("uv")
    if uv:
        print("Setting up CodeTrust with uv...", flush=True)
        sync = [uv, "sync"]
        if development:
            sync.extend(["--extra", "dev"])
        _run(sync)
        return [uv, "run", "python", "-m"]

    print("uv not found; using standard Python virtual environment...", flush=True)
    if not VENV.exists():
        venv.EnvBuilder(with_pip=True).create(VENV)
    python = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    pip_probe = subprocess.run(
        [str(python), "-m", "pip", "--version"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if pip_probe.returncode:
        _run([str(python), "-m", "ensurepip", "--upgrade"])
    package = ".[dev]" if development else "."
    _run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--quiet",
            "-e",
            package,
        ]
    )
    return [str(python), "-m"]


def _open_when_ready(url: str) -> None:
    for _ in range(60):
        if _codetrust_running(url):
            webbrowser.open(url)
            return
        time.sleep(0.25)


def _codetrust_running(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=0.5) as response:
            payload = json.load(response)
        return response.status == 200 and payload.get("service") == "codetrust"
    except (OSError, ValueError):
        return False


def _run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, cwd=ROOT, check=check)
    except subprocess.CalledProcessError as exc:
        print(f"Command failed with exit code {exc.returncode}.", file=sys.stderr)
        raise SystemExit(exc.returncode) from exc


if __name__ == "__main__":
    raise SystemExit(main())
