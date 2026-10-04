"""Finds and downloads free, monetization-safe stock footage, logging the license of every clip.

Sources, tried in this order:
  Pexels and Pixabay (need free API keys; both licenses allow commercial use and editing)
  NASA media library and Wikimedia Commons (no key; public domain, CC0 and CC BY files only)
"""

import hashlib
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import requests
from urllib.parse import quote

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


HEADERS = {"User-Agent": "youtube-agent/1.0 (https://github.com/javedbiu/youtube-agent)"}


def _nasa(query: str, used: set[str]) -> Clip | None:
    """NASA media library. No key needed; NASA media is generally public domain."""
    r = requests.get("https://images-api.nasa.gov/search",
                     params={"q": query, "media_type": "video"}, headers=HEADERS, timeout=30)
    r.raise_for_status()
    for item in r.json()["collection"]["items"][:10]:
        meta = item["data"][0]
        page = f"https://images.nasa.gov/details/{quote(meta['nasa_id'])}"
        if page in used:
            continue
        assets = requests.get(item["href"], headers=HEADERS, timeout=30).json()
        mp4s = [u for u in assets if u.endswith(".mp4")]
        pick = next((u for u in mp4s if "~medium" in u), None) or next((u for u in mp4s if "~orig" in u), None)
        if not pick:
            continue
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", meta["nasa_id"])[:60]
        path = _download(pick.replace("http://", "https://"), CACHE / f"nasa_{safe_id}.mp4")
        creator = meta.get("center") or "NASA"
        return Clip(str(path), "NASA", page, f"NASA {creator}".strip(), "Public domain (NASA media)", query)
    return None


# Only licenses that allow both commercial use and edits, without share-alike obligations.
_SAFE_LICENSE = re.compile(r"^(cc0|public domain|pd\b|pd-|cc by \d)", re.I)


def _wikimedia(query: str, used: set[str]) -> Clip | None:
    """Wikimedia Commons videos. No key needed; keeps only public domain, CC0 and CC BY files."""
    r = requests.get("https://commons.wikimedia.org/w/api.php", headers=HEADERS, timeout=30, params={
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": f"{query} filetype:video", "gsrlimit": 20,
        "prop": "imageinfo", "iiprop": "url|size|extmetadata",
    })
    r.raise_for_status()
    pages = sorted(r.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    for p in pages:
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        page = info.get("descriptionurl", "")
        if not _SAFE_LICENSE.match(lic) or not page or page in used:
            continue
        if info.get("width", 0) < 640 or info.get("duration", 3) < 3:
            continue
        artist = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip() or "Unknown"
        ext = Path(info["url"]).suffix or ".webm"
        path = _download(info["url"], CACHE / f"wikimedia_{p['pageid']}{ext}")
        return Clip(str(path), "Wikimedia Commons", page, artist, lic, query)
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
        for finder in (_pexels, _pixabay, _nasa, _wikimedia):
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
