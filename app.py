from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, unquote, urlparse
from pathlib import Path
import argparse
import errno
import json
import os
import random
import socket
import sys
import time

try:
    from PIL import Image, ImageOps
except ImportError:
    Image = None


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "app" / "static"
DEFAULT_PHOTO_DIR = STATIC_DIR / "photos"
DEFAULT_AUDIO_DIR = STATIC_DIR / "audio"
DATA_DIR = STATIC_DIR / "data"
CAPTIONS_FILE = DATA_DIR / "captions.json"

PHOTO_DIR = Path(os.environ.get("VIET_HA_PHOTO_DIR", DEFAULT_PHOTO_DIR)).expanduser()
AUDIO_DIR = Path(os.environ.get("VIET_HA_AUDIO_DIR", DEFAULT_AUDIO_DIR)).expanduser()

SUPPORTED_IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".avif"}
SUPPORTED_AUDIO = {".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac", ".webm"}

IMAGE_INFO_CACHE = {}
CAPTION_CACHE = {"mtime": None, "data": {}}


def write_log(message):
    if sys.stdout:
        sys.stdout.write(f"{message}\n")
        sys.stdout.flush()


def find_free_port(host, start_port):
    for port in range(start_port, start_port + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise OSError(f"No free port found from {start_port} to {start_port + 99}.")


def resolve_dir(path):
    return Path(path).expanduser().resolve()


def is_under(path, root):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def iter_media_files(root, extensions):
    root = resolve_dir(root)
    if not root.exists() or not root.is_dir():
        return []
    return sorted(
        [
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in extensions
        ],
        key=lambda path: (path.stat().st_mtime, path.name.lower()),
        reverse=True,
    )


def image_files(photo_dir=None):
    return iter_media_files(photo_dir or PHOTO_DIR, SUPPORTED_IMAGES)


def audio_files(audio_dir=None):
    return iter_media_files(audio_dir or AUDIO_DIR, SUPPORTED_AUDIO)


def rel_url(path):
    return "/" + path.relative_to(STATIC_DIR).as_posix()


def load_captions():
    if not CAPTIONS_FILE.exists():
        CAPTION_CACHE["mtime"] = None
        CAPTION_CACHE["data"] = {}
        return {}

    mtime = CAPTIONS_FILE.stat().st_mtime
    if CAPTION_CACHE["mtime"] == mtime:
        return CAPTION_CACHE["data"]

    try:
        data = json.loads(CAPTIONS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}

    CAPTION_CACHE["mtime"] = mtime
    CAPTION_CACHE["data"] = data if isinstance(data, dict) else {}
    return CAPTION_CACHE["data"]


def image_dimensions(path):
    stat = path.stat()
    cache_key = (str(path), stat.st_mtime, stat.st_size)
    if cache_key in IMAGE_INFO_CACHE:
        return IMAGE_INFO_CACHE[cache_key]

    width, height = 0, 0
    if Image is not None:
        try:
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image)
                width, height = image.size
        except OSError:
            width, height = 0, 0

    IMAGE_INFO_CACHE[cache_key] = (width, height)
    return width, height


def caption_for(path, captions):
    value = captions.get(path.name) or captions.get(path.stem) or {}
    if not isinstance(value, dict):
        value = {}
    return {
        "zh": str(value.get("zh", "")),
        "vi": str(value.get("vi", "")),
    }


def photo_url(path, root, mode):
    if mode == "static":
        return rel_url(path) if is_under(path, STATIC_DIR) else ""
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    return "/local-photos/" + quote(relative)


def build_photo_manifest(photo_dir=None, url_mode="server"):
    root = resolve_dir(photo_dir or PHOTO_DIR)
    captions = load_captions()
    photos = []

    for source in image_files(root):
        url = photo_url(source, root, url_mode)
        if not url:
            continue

        width, height = image_dimensions(source)
        stat = source.stat()
        relative = source.resolve().relative_to(root).as_posix()
        photos.append({
            "id": source.stem,
            "name": source.name,
            "relativePath": relative,
            "src": url,
            "thumb": url,
            "original": url,
            "width": width,
            "height": height,
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "desc": caption_for(source, captions),
        })

    total = len(photos)
    for index, item in enumerate(photos, 1):
        item["rank"] = index
        item["label"] = {
            "zh": f"第 {index} / {total} 张",
            "vi": f"Ảnh {index} / {total}",
        }

    return photos


def build_audio_manifest(audio_dir=None, url_mode="server"):
    tracks = []
    root = resolve_dir(audio_dir or AUDIO_DIR)
    for source in audio_files(root):
        if url_mode == "static":
            url = rel_url(source) if is_under(source, STATIC_DIR) else ""
        else:
            relative = source.resolve().relative_to(root).as_posix()
            url = "/local-audio/" + quote(relative)
        if url:
            tracks.append({"src": url})
    return tracks


class VietHaHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def end_headers(self):
        path = urlparse(self.path).path
        if path.startswith("/local-photos/") or path.startswith("/local-audio/"):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        elif path.startswith("/photos/") or path.startswith("/audio/"):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format, *args):
        write_log("%s - - [%s] %s" % (self.client_address[0], self.log_date_time_string(), format % args))

    def send_local_file(self, request_path, root, prefix, extensions):
        relative = unquote(request_path.removeprefix(prefix)).replace("\\", "/")
        target = (resolve_dir(root) / relative).resolve()
        base = resolve_dir(root)

        if not is_under(target, base) or not target.is_file() or target.suffix.lower() not in extensions:
            self.send_error(404, "File not found")
            return

        content_type = self.guess_type(str(target))
        size = target.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.end_headers()
        with target.open("rb") as file:
            self.copyfile(file, self.wfile)

    def do_GET(self):
        path = urlparse(self.path).path

        if path.startswith("/local-photos/"):
            self.send_local_file(path, PHOTO_DIR, "/local-photos/", SUPPORTED_IMAGES)
            return

        if path.startswith("/local-audio/"):
            self.send_local_file(path, AUDIO_DIR, "/local-audio/", SUPPORTED_AUDIO)
            return

        if path == "/api/audio":
            tracks = build_audio_manifest()
            selected = random.choice(tracks) if tracks else None
            payload = json.dumps({
                "count": len(tracks),
                "track": selected,
                "tracks": tracks,
            }, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == "/api/photos":
            started = time.time()
            photos = build_photo_manifest()
            payload = json.dumps({
                "count": len(photos),
                "photoDir": str(resolve_dir(PHOTO_DIR)),
                "generatedAt": int(time.time()),
                "elapsedMs": round((time.time() - started) * 1000),
                "photos": photos,
            }, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        super().do_GET()


def main():
    parser = argparse.ArgumentParser(description="Run the Viet Ha memory website.")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "4173")))
    parser.add_argument("--photo-dir", default=os.environ.get("VIET_HA_PHOTO_DIR", str(DEFAULT_PHOTO_DIR)))
    parser.add_argument("--audio-dir", default=os.environ.get("VIET_HA_AUDIO_DIR", str(DEFAULT_AUDIO_DIR)))
    parser.add_argument("--no-auto-port", action="store_true", help="Fail instead of picking another port.")
    args = parser.parse_args()

    global PHOTO_DIR, AUDIO_DIR
    PHOTO_DIR = resolve_dir(args.photo_dir)
    AUDIO_DIR = resolve_dir(args.audio_dir)

    try:
        server = ThreadingHTTPServer((args.host, args.port), VietHaHandler)
    except PermissionError as exc:
        if args.no_auto_port:
            raise
        free_port = find_free_port(args.host, args.port + 1)
        write_log(f"Port {args.port} is not available: {exc}")
        write_log(f"Trying port {free_port} instead.")
        args.port = free_port
        server = ThreadingHTTPServer((args.host, args.port), VietHaHandler)
    except OSError as exc:
        if args.no_auto_port or exc.errno not in (errno.EADDRINUSE, 10048, 10013):
            raise
        free_port = find_free_port(args.host, args.port + 1)
        write_log(f"Port {args.port} is not available: {exc}")
        write_log(f"Trying port {free_port} instead.")
        args.port = free_port
        server = ThreadingHTTPServer((args.host, args.port), VietHaHandler)

    local_url = f"http://localhost:{args.port}"
    lan_url = f"http://{args.host}:{args.port}" if args.host != "0.0.0.0" else f"http://<your-ip>:{args.port}"

    write_log("Viet Ha memory website is running.")
    write_log(f"Photo directory: {PHOTO_DIR}")
    write_log(f"Audio directory: {AUDIO_DIR}")
    write_log(f"Local: {local_url}")
    write_log(f"LAN:   {lan_url}")
    write_log("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        write_log("Stopping server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        (ROOT / "server-crash.log").write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        raise
