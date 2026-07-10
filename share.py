from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time

from app import VietHaHandler
from http.server import ThreadingHTTPServer


ROOT = Path(__file__).resolve().parent
URL_PATTERN = re.compile(r"https://[a-zA-Z0-9.-]+")


def say(message=""):
    print(message, flush=True)


def find_free_port(start_port=4173):
    for port in range(start_port, start_port + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No free port found.")


def start_server(port):
    server = ThreadingHTTPServer(("127.0.0.1", port), VietHaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def start_tunnel(port):
    ssh = Path("C:/Windows/System32/OpenSSH/ssh.exe")
    if not ssh.exists():
        raise RuntimeError("Cannot find Windows OpenSSH. Please install OpenSSH Client first.")

    cmd = [
        str(ssh),
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "ServerAliveInterval=60",
        "-R",
        f"80:127.0.0.1:{port}",
        "nokey@localhost.run",
    ]

    return subprocess.Popen(
        cmd,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )


def main():
    port = find_free_port()
    server = start_server(port)

    say()
    say("Viet Ha photo website is running.")
    say(f"Local address: http://localhost:{port}")
    say()
    say("Creating a temporary public link...")
    say("Keep this window open. Closing it will stop sharing.")
    say()

    tunnel = start_tunnel(port)
    public_url = None
    started_at = time.time()

    try:
        while True:
            line = tunnel.stdout.readline()
            if line:
                say(line.rstrip())
                match = URL_PATTERN.search(line)
                if match and ".lhr.life" in match.group(0):
                    public_url = match.group(0)
                    say()
                    say("=" * 68)
                    say("Public share address:")
                    say(public_url)
                    say("=" * 68)
                    say()
            elif tunnel.poll() is not None:
                raise RuntimeError("Tunnel process exited. Please run share.bat again.")
            elif not public_url and time.time() - started_at > 30:
                say("Still waiting for public link...")
                started_at = time.time()
            time.sleep(0.05)
    except KeyboardInterrupt:
        say()
        say("Stopping share server...")
    finally:
        tunnel.terminate()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        say()
        say(f"Error: {exc}")
        say()
        input("Press Enter to close...")
        sys.exit(1)
