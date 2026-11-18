import shutil
import tempfile
import zipfile
from pathlib import Path

import httpx


def _download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as response:
        response.raise_for_status()
        with partial.open("wb") as out:
            for chunk in response.iter_bytes(1 << 20):
                out.write(chunk)
    partial.rename(target)


def ensure_file(path: Path, url: str) -> Path:
    if not path.exists():
        print(f"Скачиваю {url}")
        _download(url, path)
    return path


def ensure_zip_dir(path: Path, url: str) -> Path:
    if path.exists():
        return path
    print(f"Скачиваю {url}")
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "model.zip"
        _download(url, archive)
        unpacked = Path(tmp) / "unpacked"
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(unpacked)
        inner = unpacked / path.name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(inner if inner.exists() else unpacked), str(path))
    return path
