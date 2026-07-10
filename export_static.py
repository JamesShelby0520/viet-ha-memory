from pathlib import Path
import json
import os
import shutil

import app


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "app" / "static"
TARGET = ROOT / "docs"
DATA_DIR = TARGET / "data"
INCLUDE_MEDIA = os.environ.get("VIET_HA_EXPORT_INCLUDE_MEDIA", "false").lower() == "true"


def relative_url(value):
    return value[1:] if value.startswith("/") else value


def ignore_private_media(directory, names):
    if INCLUDE_MEDIA:
        return set()
    if Path(directory).resolve() == SOURCE.resolve():
        return {"photos"} & set(names)
    return set()


def main():
    if TARGET.exists():
        shutil.rmtree(TARGET)
    shutil.copytree(SOURCE, TARGET, ignore=ignore_private_media)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if INCLUDE_MEDIA:
        photos = app.build_photo_manifest(app.DEFAULT_PHOTO_DIR, url_mode="static")
        for photo in photos:
            photo["src"] = relative_url(photo["src"])
            photo["thumb"] = relative_url(photo["thumb"])
            photo["original"] = relative_url(photo["original"])
    else:
        photos = []

    audio_tracks = [
        {"src": relative_url(track["src"])}
        for track in app.build_audio_manifest(app.DEFAULT_AUDIO_DIR, url_mode="static")
    ]

    (DATA_DIR / "photos.json").write_text(
        json.dumps({
            "count": len(photos),
            "photos": photos,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (DATA_DIR / "audio.json").write_text(
        json.dumps({
            "count": len(audio_tracks),
            "tracks": audio_tracks,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (TARGET / ".nojekyll").write_text("", encoding="utf-8")

    media_note = "with photos and audio" if INCLUDE_MEDIA else "without private photos, with audio"
    print(f"Exported {len(photos)} photos and {len(audio_tracks)} audio tracks to {TARGET} ({media_note})")


if __name__ == "__main__":
    main()
