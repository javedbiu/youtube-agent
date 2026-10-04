"""Turns narration text into audio files.

VOICE_PROVIDER:
  espeak     free robot voice, only for testing the pipeline
  elevenlabs AI voice (ideally a clone of your own voice), needs ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID
  recorded   your own recordings: put scene_01.wav, scene_02.wav ... in the video's audio folder
"""

import os
import subprocess
from pathlib import Path

import requests


def _espeak(text: str, out: Path) -> None:
    subprocess.run(["espeak-ng", "-v", "en-us", "-s", "155", "-w", str(out), text], check=True)


def _elevenlabs(text: str, out: Path) -> None:
    voice = os.environ["ELEVENLABS_VOICE_ID"]
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
        json={"text": text, "model_id": "eleven_multilingual_v2"},
        timeout=120,
    )
    r.raise_for_status()
    mp3 = out.with_suffix(".mp3")
    mp3.write_bytes(r.content)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), str(out)], check=True)


def narrate(text: str, out: Path) -> Path:
    provider = os.getenv("VOICE_PROVIDER", "espeak")
    out.parent.mkdir(parents=True, exist_ok=True)
    if provider == "recorded":
        if not out.exists():
            raise FileNotFoundError(f"Record this line and save it as {out}:\n  {text}")
        return out
    if out.exists():
        return out
    {"espeak": _espeak, "elevenlabs": _elevenlabs}[provider](text, out)
    return out
