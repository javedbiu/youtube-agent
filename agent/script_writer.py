"""Writes a narrated video script for one topic using the Claude API."""

import json
from pathlib import Path

import anthropic
from pydantic import BaseModel, Field

MODEL = "claude-opus-5-5"


class Scene(BaseModel):
    narration: str = Field(description="What the narrator says in this scene, 1 to 3 sentences.")
    footage_query: str = Field(description="2 to 4 word stock-footage search, e.g. 'ancient roman ruins'.")
    on_screen_text: str = Field(description="Short caption shown on screen (max 6 words), or empty.")


class VideoScript(BaseModel):
    title: str = Field(description="YouTube title, under 70 characters, curiosity-driven, not clickbait.")
    thumbnail_text: str = Field(description="2 to 4 bold words for the thumbnail.")
    description: str = Field(description="2 short paragraphs summarising the video.")
    tags: list[str]
    sources: list[str] = Field(description="URLs or book titles used to check the facts.")
    uncertain_claims: list[str] = Field(description="Any claim you are not fully sure of, for human review.")
    contains_synthetic_media: bool = Field(
        description="True only if the video would show realistic AI-generated scenes of real events or people."
    )
    scenes: list[Scene]


SYSTEM = """You write scripts for a faceless YouTube channel that explains history and science.
Every script must add real value: a clear story arc, accurate facts, and an original point of view.
Never pad, never repeat a template, never invent quotes or numbers.
Structure: a 15-second hook with a surprising fact or question, then the explanation as a story,
then a one-line takeaway. Aim for {words} words of narration in total across 15 to 30 scenes.
Write narration to be spoken aloud: short sentences, plain words, no lists."""


def write_script(topic: str, words: int = 1400) -> VideoScript:
    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM.format(words=words),
        messages=[{"role": "user", "content": f"Write the script for this video: {topic}"}],
        output_format=VideoScript,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined this topic: {topic}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Script was cut off; try a lower word count.")
    return response.parsed_output


def load_script(path: Path) -> VideoScript:
    return VideoScript.model_validate(json.loads(Path(path).read_text()))


def save_script(script: VideoScript, path: Path) -> None:
    Path(path).write_text(script.model_dump_json(indent=2))
