"""Edits footage + narration into a finished 1080p video with captions, using FFmpeg."""

import os
import re
import subprocess
from pathlib import Path

W, H, FPS = 1920, 1080, 30
FONT = os.getenv("VIDEO_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def run(args: list[str], cwd: Path | None = None) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True, cwd=cwd)


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def render_scene(clip: Path, audio: Path, caption: str, out: Path, pad: float = 0.35) -> float:
    """One scene: footage cut to the narration length, framed to 1080p, with an optional caption."""
    d = duration(audio) + pad
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},"
          f"zoompan=z='min(zoom+0.0004,1.08)':d=1:s={W}x{H}:fps={FPS}")
    if caption.strip():
        txt = out.with_suffix(".txt")
        txt.write_text(caption.strip())
        vf += (f",drawtext=fontfile={FONT}:textfile={txt}:fontsize=58:fontcolor=white:"
               f"box=1:boxcolor=black@0.55:boxborderw=24:x=80:y=90")
    run(["-stream_loop", "-1", "-i", str(clip), "-i", str(audio),
         "-t", f"{d:.2f}", "-map", "0:v", "-map", "1:a",
         "-vf", vf, "-af", f"apad,aresample=48000",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-ac", "2", str(out)])
    return d


def _ts(t: float) -> str:
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02}:{int(m):02}:{int(s):02},{int((s % 1) * 1000):03}"


def build_srt(narrations: list[str], durations: list[float], out: Path, words_per_line: int = 8) -> None:
    """Captions timed by spreading each scene's words evenly across its duration.

    Lines break at sentence ends first, then every few words, so a caption never mixes two sentences.
    """
    lines, start, n = [], 0.0, 1
    for text, d in zip(narrations, durations):
        words = text.split()
        chunks = []
        for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
            sw = sentence.split()
            per = -(-len(sw) // -(-len(sw) // words_per_line)) if sw else 1  # even-sized lines
            chunks += [sw[i:i + per] for i in range(0, len(sw), per)]
        t = start
        for chunk in chunks:
            span = d * len(chunk) / max(len(words), 1)
            lines.append(f"{n}\n{_ts(t)} --> {_ts(t + span)}\n{' '.join(chunk)}\n")
            t += span
            n += 1
        start += d
    out.write_text("\n".join(lines))


def assemble(scene_files: list[Path], srt: Path, out: Path, music: str | None = None) -> None:
    work = out.parent
    concat = work / "scenes.txt"
    concat.write_text("".join(f"file '{Path(p).resolve()}'\n" for p in scene_files))
    joined = work / "joined.mp4"
    run(["-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(joined)])

    style = "FontName=DejaVu Sans,Fontsize=20,Bold=1,Outline=2,Shadow=0,MarginV=40"
    args = ["-i", joined.name]
    if music and Path(music).exists():
        args += ["-stream_loop", "-1", "-i", str(Path(music).resolve()),
                 "-filter_complex",
                 "[1:a]volume=0.10[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
                 "-map", "0:v", "-map", "[a]"]
    args += ["-vf", f"subtitles={srt.name}:force_style='{style}'",
             "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out.name]
    run(args, cwd=work)
    joined.unlink()


def thumbnail(scene: Path, text: str, out: Path) -> None:
    """A 1280x720 frame from a scene (before captions) with big bold text. Swap in a Canva design if you prefer."""
    txt = out.with_suffix(".txt")
    txt.write_text(text.upper())
    at = duration(scene) * 0.5
    run(["-ss", f"{at:.1f}", "-i", str(scene), "-frames:v", "1",
         "-vf", (f"scale=1280:720,eq=brightness=-0.08:saturation=1.3,"
                 f"drawtext=fontfile={FONT}:textfile={txt}:fontsize=110:fontcolor=yellow:"
                 f"borderw=8:bordercolor=black:x=60:y=h-th-70"),
         str(out)])
