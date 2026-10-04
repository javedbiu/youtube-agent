"""Finds and downloads free, monetization-safe stock footage, logging the license of every clip.

Sources: Pexels and Pixabay. Both licenses allow commercial use and editing
(https://www.pexels.com/license/, https://pixabay.com/service/license-summary/).
"""

import hashlib
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

CACHE = Path("cache/footage")


@dataclass
class Clip:
    path: str
    source: str
    page_url: str
    creator: str
    license: str
    query: str


def _download(url: str, dest: Path) -> Path:
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            tmp = dest.with_suffix(".part")
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
            tmp.rename(dest)
    return dest


def _pexels(query: str, used: set[str]) -> Clip | None:
    key = os.getenv("PEXELS_API_KEY")
    if not key:
        return None
    r = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": key},
        params={"query": query, "orientation": "landscape", "per_page": 15},
        timeout=30,
    )
    r.raise_for_status()
    for video in r.json().get("videos", []):
        page = video["url"]
        if page in used:
            continue
        files = [f for f in video["video_files"] if f.get("width") and 1280 <= f["width"] <= 1920]
        if not files:
            continue
        best = max(files, key=lambda f: f["width"])
        name = f"pexels_{video['id']}_{best['width']}.mp4"
        path = _download(best["link"], CACHE / name)
        return Clip(str(path), "Pexels", page, video["user"]["name"], "Pexels License", query)
    return None


def _pixabay(query: str, used: set[str]) -> Clip | None:
    key = os.getenv("PIXABAY_API_KEY")
    if not key:
        return None
    r = requests.get(
        "https://pixabay.com/api/videos/",
        params={"key": key, "q": query, "per_page": 15, "safesearch": "true"},
        timeout=30,
    )
    r.raise_for_status()
    for hit in r.json().get("hits", []):
        page = hit["pageURL"]
        if page in used:
            continue
        video = hit["videos"].get("large") or hit["videos"].get("medium")
        if not video or not video.get("url"):
            continue
        path = _download(video["url"], CACHE / f"pixabay_{hit['id']}.mp4")
        return Clip(str(path), "Pixabay", page, hit["user"], "Pixabay Content License", query)
    return None


def placeholder(query: str, seconds: float = 10) -> Clip:
    """A plain title card, used for offline tests or when no footage is found."""
    name = hashlib.md5(query.encode()).hexdigest()[:10]
    path = CACHE / f"placeholder_{name}.mp4"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        text = query.replace("'", "").replace(":", "")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
             "-i", f"color=c=0x1f2a44:s=1920x1080:d={seconds}:r=30",
             "-vf", f"drawtext=text='{text}':fontcolor=white@0.35:fontsize=64:x=(w-tw)/2:y=(h-th)/2",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
            check=True,
        )
    return Clip(str(path), "placeholder", "", "", "own work", query)


def find_clip(query: str, used: set[str], offline: bool = False) -> Clip:
    if not offline:
        for finder in (_pexels, _pixabay):
            try:
                clip = finder(query, used)
            except requests.RequestException as e:
                print(f"  ! {finder.__name__} failed for '{query}': {e}")
                clip = None
            if clip:
                used.add(clip.page_url)
                return clip
        print(f"  ! no footage found for '{query}', using a title card")
    return placeholder(query)


def credits(clips: list[Clip]) -> str:
    """Credits block for the video description."""
    seen, lines = set(), []
    for c in clips:
        if c.source == "placeholder" or c.page_url in seen:
            continue
        seen.add(c.page_url)
        lines.append(f"- {c.creator} on {c.source} ({c.license}): {c.page_url}")
    return "Footage credits:\n" + "\n".join(lines) if lines else ""


def as_records(clips: list[Clip]) -> list[dict]:
    return [asdict(c) for c in clips]
