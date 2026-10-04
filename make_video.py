"""Make one video end to end.

Examples:
  python make_video.py --topic "How the Romans built roads that still exist"
  python make_video.py --script scripts/roman_roads.json --offline      # no API keys needed
  python make_video.py --next-idea --upload                            # next idea from ideas.md, upload as private
"""

import argparse
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from agent import editor, footage, voice
from agent.script_writer import load_script, save_script, write_script

IDEAS = Path("ideas.md")
DONE = Path("output/done.txt")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60]


def next_idea() -> str:
    done = set(DONE.read_text().splitlines()) if DONE.exists() else set()
    for line in IDEAS.read_text().splitlines():
        m = re.match(r"^\s*\d+\.\s+(.*)", line)
        if m and m.group(1).strip() not in done:
            return m.group(1).strip()
    raise SystemExit("All ideas in ideas.md are used. Add more.")


def main() -> None:
    load_dotenv()
    p = argparse.ArgumentParser()
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--topic")
    src.add_argument("--script", type=Path, help="Use an existing script JSON instead of writing one")
    src.add_argument("--next-idea", action="store_true", help="Take the next unused idea from ideas.md")
    p.add_argument("--offline", action="store_true", help="Title cards instead of downloaded footage")
    p.add_argument("--upload", action="store_true", help="Upload to YouTube as private when done")
    a = p.parse_args()

    topic = a.topic or (next_idea() if a.next_idea else None)
    if a.script:
        script = load_script(a.script)
    else:
        print(f"1/5 Writing script: {topic}")
        script = write_script(topic)
    work = Path("output") / slugify(script.title)
    work.mkdir(parents=True, exist_ok=True)
    save_script(script, work / "script.json")
    if script.uncertain_claims:
        print("  Check these claims before publishing:\n   - " + "\n   - ".join(script.uncertain_claims))

    print(f"2/5 Finding footage for {len(script.scenes)} scenes")
    used: set[str] = set()
    clips = [footage.find_clip(s.footage_query, used, a.offline) for s in script.scenes]
    (work / "licenses.json").write_text(json.dumps(footage.as_records(clips), indent=2))

    print("3/5 Recording narration and editing scenes")
    scene_files, durations = [], []
    for i, (scene, clip) in enumerate(zip(script.scenes, clips), 1):
        audio = voice.narrate(scene.narration, work / "audio" / f"scene_{i:02}.wav")
        out = work / "scenes" / f"scene_{i:02}.mp4"
        out.parent.mkdir(exist_ok=True)
        durations.append(editor.render_scene(Path(clip.path), audio, scene.on_screen_text, out))
        scene_files.append(out)

    print("4/5 Assembling video, captions and thumbnail")
    srt = work / "captions.srt"
    editor.build_srt([s.narration for s in script.scenes], durations, srt)
    video = work / "video.mp4"
    editor.assemble(scene_files, srt, video, os.getenv("MUSIC_FILE"))
    thumb = work / "thumbnail.jpg"
    editor.thumbnail(scene_files[len(scene_files) // 3], script.thumbnail_text, thumb)

    description = "\n\n".join(filter(None, [
        script.description,
        "Sources:\n" + "\n".join(f"- {s}" for s in script.sources) if script.sources else "",
        footage.credits(clips),
    ]))
    (work / "description.txt").write_text(description)
    print(f"  Done: {video} ({sum(durations) / 60:.1f} min)")

    if a.upload:
        from agent.uploader import upload
        print("5/5 Uploading to YouTube as PRIVATE")
        vid = upload(video, script.title, description, script.tags,
                     script.contains_synthetic_media, thumb)
        print(f"  Uploaded: https://studio.youtube.com/video/{vid}/edit  (review, then set to Public)")
    if topic:
        DONE.parent.mkdir(exist_ok=True)
        with DONE.open("a") as f:
            f.write(topic + "\n")


if __name__ == "__main__":
    main()
