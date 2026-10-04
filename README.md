# YouTube video agent

Makes a narrated history or science explainer video from one topic, using free stock footage,
and uploads it to YouTube as **private** so you can check it before it goes public.

```
topic -> script (Claude) -> footage (Pexels/Pixabay) -> narration -> edit (FFmpeg) -> thumbnail -> private upload
```

## What you need

| Thing | Cost | Where |
| --- | --- | --- |
| Python 3.10+ and FFmpeg | Free | python.org, ffmpeg.org |
| Claude API key | About $0.10 to $0.50 per script | console.anthropic.com |
| Pexels API key (Pixabay optional) | Free | pexels.com/api |
| Voice | Free (your recordings) or about $5+/month (ElevenLabs) | elevenlabs.io |
| YouTube upload access | Free | console.cloud.google.com |

## Setup (once)

1. Install: `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and paste in your keys. Never share `.env` with anyone.
3. YouTube access: in Google Cloud Console create a project, enable **YouTube Data API v3**,
   create an **OAuth client ID** of type **Desktop app**, and download it as `client_secret.json`
   into this folder. The first upload opens a browser window to log in to your channel.

## Make a video

```bash
# Test without any keys (title cards instead of footage, robot voice)
python make_video.py --script scripts/roman_roads_sample.json --offline

# Real video from a topic
python make_video.py --topic "How the Romans built roads that still exist"

# Next idea from ideas.md, then upload as private
python make_video.py --next-idea --upload
```

Everything for a video lands in `output/<title>/`: `video.mp4`, `thumbnail.jpg`, `description.txt`
(with sources and footage credits), `script.json`, and `licenses.json` (the license of every clip,
keep it in case of a copyright claim).

## Before you publish each video (15 to 30 minutes)

- Read the "Check these claims" list the script step prints, and fix anything wrong in `script.json`,
  then rerun with `--script output/<title>/script.json`.
- Watch the whole video. Replace any clip that doesn't match what's being said.
- In YouTube Studio, check the title, thumbnail and description, then set the video to Public.

## Run it automatically (3 times a week)

On Linux or Mac, `crontab -e` and add (runs Mon, Wed, Fri at 06:00):

```
0 6 * * 1,3,5 cd /path/to/youtube-agent && python make_video.py --next-idea --upload >> agent.log 2>&1
```

On Windows, use Task Scheduler with the same command.

## Rules this agent follows, and you should too

- Footage only from Pexels and Pixabay, whose licenses allow commercial use and editing.
  Never add clips licensed CC NC or ND, or "no copyright" re-uploads of films, TV or sports.
- Every video has an original script and narration. That is what makes it monetizable under
  YouTube's reused content policy.
- Music only from the YouTube Audio Library (set `MUSIC_FILE` in `.env`).
- If a video ever shows realistic AI-generated scenes of real people or events, the script marks
  `contains_synthetic_media` and the upload sets YouTube's disclosure flag.
