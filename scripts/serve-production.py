"""Build and serve the production app through Cloudflare Tunnel."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from http.client import HTTPConnection, HTTPException
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypeVar

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
PYTHON = BACKEND / ".venv/bin/python"
HOST = "127.0.0.1"
BACKEND_PORT = 27431
FRONTEND_PORT = 27432
TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
STOP_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
T = TypeVar("T")


def check_prerequisites(existing_tunnel: bool = False):
    commands = ("npm", "caddy") if existing_tunnel else ("npm", "caddy", "cloudflared")
    for command in commands:
        if not shutil.which(command):
            raise RuntimeError(f"{command} is required on PATH.")
    if not os.access(PYTHON, os.X_OK):
        raise RuntimeError("Set up backend/.venv first (see backend/README.md).")
    if not os.access(FRONTEND / "node_modules/.bin/vite", os.X_OK):
        raise RuntimeError("Run npm ci in frontend first.")

    for port in (BACKEND_PORT, FRONTEND_PORT):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                listener.bind((HOST, port))
                listener.listen()
            except OSError as error:
                raise RuntimeError(
                    f"Cannot use production port {port}: {error}"
                ) from error


def http_status(port: int) -> int:
    connection = HTTPConnection(HOST, port, timeout=1)
    try:
        connection.request("GET", "/")
        return connection.getresponse().status
    except (OSError, HTTPException):
        return 0
    finally:
        connection.close()


def wait_for(process: subprocess.Popen, probe: Callable[[], T], error: str) -> T:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and process.poll() is None:
        result = probe()
        if result:
            return result
        time.sleep(0.2)
    raise RuntimeError(error)


def stop_processes(processes: list[subprocess.Popen]):
    for process in processes:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    deadline = time.monotonic() + 15
    for process in processes:
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()


def serve(
    run_dir: Path,
    hostname: str | None,
    token_file: Path | None,
    existing_tunnel: bool = False,
):
    processes: list[subprocess.Popen] = []
    tunnel_log = run_dir / "cloudflared.log"

    def start(args, *, cwd=ROOT, env=None, **options):
        process = subprocess.Popen(
            args, cwd=cwd, env=env, start_new_session=True, **options
        )
        processes.append(process)
        return process

    def run(args, *, cwd, env=None):
        process = start(args, cwd=cwd, env=env)
        returncode = process.wait()
        if returncode:
            raise subprocess.CalledProcessError(returncode, args)
        processes.remove(process)

    def find_tunnel_url():
        match = TUNNEL_URL.search(tunnel_log.read_text(errors="replace"))
        return match[0] if match else ""

    try:
        print("Checking database migration status...", flush=True)
        run([PYTHON, "-m", "alembic", "current", "--check-heads"], cwd=BACKEND)

        site = run_dir / "site"
        caddy = start(
            [
                "caddy",
                "run",
                "--config",
                ROOT / "scripts/Caddyfile",
                "--adapter",
                "caddyfile",
            ],
            env={**os.environ, "FIELD_SHIFT_DIST": str(site)},
        )
        wait_for(caddy, lambda: http_status(FRONTEND_PORT), "Caddy did not start.")

        # Keep this run independent of any existing cloudflared configuration.
        tunnel_config = run_dir / "cloudflared.yml"
        tunnel_config.write_text("{}\n")
        tunnel_pidfile = run_dir / "cloudflared.pid"
        tunnel_command = [
            "cloudflared",
            "tunnel",
            "--config",
            tunnel_config,
            "--no-autoupdate",
            "--metrics",
            f"{HOST}:0",
        ]
        tunnel_env = os.environ.copy()
        # Explicit launch options must not inherit credentials for a different tunnel.
        tunnel_env.pop("TUNNEL_TOKEN", None)
        tunnel_env.pop("TUNNEL_TOKEN_FILE", None)
        if token_file is None:
            tunnel_command.extend(["--url", f"http://{HOST}:{FRONTEND_PORT}"])
        else:
            tunnel_command.extend(
                ["--pidfile", tunnel_pidfile, "run", "--token-file", token_file]
            )

        tunnel = None
        if not existing_tunnel:
            with tunnel_log.open("w") as log:
                tunnel = start(
                    tunnel_command, env=tunnel_env, stdout=log, stderr=subprocess.STDOUT
                )
        if existing_tunnel:
            public_url = f"https://{hostname}"
            print(
                f"Using the existing tunnel service; its route must target http://{HOST}:{FRONTEND_PORT}.",
                flush=True,
            )
        elif hostname is None:
            public_url = wait_for(
                tunnel, find_tunnel_url, "Cloudflare did not issue a Quick Tunnel URL."
            )
        else:
            wait_for(
                tunnel,
                tunnel_pidfile.is_file,
                "The named Cloudflare Tunnel did not connect.",
            )
            public_url = f"https://{hostname}"

        build = run_dir / "build"
        run(
            ["npm", "run", "build", "--", "--outDir", build, "--emptyOutDir"],
            cwd=FRONTEND,
            env={**os.environ, "VITE_API_BASE_URL": f"{public_url}/api/v1"},
        )
        backend = start(
            [
                PYTHON,
                "-m",
                "uvicorn",
                "main:app",
                "--host",
                HOST,
                "--port",
                str(BACKEND_PORT),
                "--workers",
                "1",
                "--timeout-graceful-shutdown",
                "10",
            ],
            cwd=BACKEND,
            env={**os.environ, "COOKIE_SECURE": "true", "CORS_ORIGINS": public_url},
        )
        wait_for(
            backend,
            lambda: http_status(BACKEND_PORT) == 200,
            "The backend did not start.",
        )

        build.rename(site)
        if http_status(FRONTEND_PORT) != 200:
            raise RuntimeError("Caddy could not serve the frontend build.")

        services = {"Caddy": caddy, "Backend": backend}
        if tunnel is not None:
            services["Cloudflare Tunnel"] = tunnel

        def check_services():
            for name, process in services.items():
                if process.poll() is not None:
                    raise RuntimeError(
                        f"{name} stopped with exit code {process.returncode}."
                    )

        check_services()
        print(
            f"\nField Shift NASA is serving locally for {public_url}\nPress Ctrl+C to stop.",
            flush=True,
        )
        while True:
            time.sleep(1)
            check_services()
    except (OSError, RuntimeError, subprocess.CalledProcessError):
        if tunnel_log.exists():
            print(tunnel_log.read_text(errors="replace"), end="", file=sys.stderr)
        raise
    finally:
        for signum in STOP_SIGNALS:
            signal.signal(signum, signal.SIG_IGN)
        stop_processes(processes)


def stop(signum, _frame):
    raise SystemExit(128 + signum)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hostname", help="Public DNS hostname for a named tunnel")
    tunnel_mode = parser.add_mutually_exclusive_group()
    tunnel_mode.add_argument(
        "--token-file", type=Path, help="File containing the named tunnel token"
    )
    tunnel_mode.add_argument(
        "--existing-tunnel",
        action="store_true",
        help="Use an already running tunnel service",
    )
    args = parser.parse_args()
    if (args.hostname is not None) != (
        args.token_file is not None or args.existing_tunnel
    ):
        parser.error(
            "--hostname requires either --token-file or --existing-tunnel, and vice versa"
        )
    if args.hostname is not None:
        args.hostname = args.hostname.lower()
        labels = args.hostname.split(".")
        if (
            len(args.hostname) > 253
            or len(labels) < 2
            or not all(DNS_LABEL.fullmatch(label) for label in labels)
        ):
            parser.error("--hostname must be a DNS hostname such as nasa.example.com")
    if args.token_file is not None:
        args.token_file = args.token_file.expanduser().resolve()
        if not args.token_file.is_file() or not os.access(args.token_file, os.R_OK):
            parser.error("--token-file must point to a readable file")

    for signum in STOP_SIGNALS:
        signal.signal(signum, stop)
    try:
        check_prerequisites(args.existing_tunnel)
        with TemporaryDirectory(prefix="field-shift-production.") as directory:
            serve(Path(directory), args.hostname, args.token_file, args.existing_tunnel)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
