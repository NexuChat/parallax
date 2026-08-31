#!/usr/bin/env python3
"""Speak the demo's captions with Google Cloud Text-to-Speech, in time with it.

The recording carries its own narration manifest: every headline line, stamped
with the second it appeared on screen. That matters because two of the beats
wait for real work — a sweep on Cloud Run, a protocol played by the engine — and
neither takes a predictable amount of time. Aligning speech to a guess would
drift; aligning it to the timestamps the recorder actually observed does not.

    python scripts/narrate_demo.py --video web/demo.mp4

Each line is synthesised separately, padded to its own start time, and the whole
track is mixed under the untouched video. The picture is never altered: this
adds a voice to a recording, it does not edit what the recording shows.
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://texttospeech.googleapis.com/v1/text:synthesize"
VOICE = "en-US-Chirp3-HD-Puck"
PROJECT = "rasikh-fleet-2026"
RATE = 24_000


def access_token() -> str:
    """A token from the local gcloud, so no key is written to disk or argv."""
    result = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        check=False, capture_output=True, text=True,
    )
    token = result.stdout.strip()
    if result.returncode != 0 or not token:
        raise SystemExit(f"could not get an access token: {result.stderr.strip() or 'gcloud failed'}")
    return token


def synthesise(text: str, token: str, *, rate: float) -> bytes:
    payload = json.dumps({
        "input": {"text": text},
        "voice": {"languageCode": "en-US", "name": VOICE},
        "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": RATE, "speakingRate": rate},
    }).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT, data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "x-goog-user-project": PROJECT,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise SystemExit(f"text-to-speech refused the line: {error.read()[:300]!r}") from error
    return base64.b64decode(body["audioContent"])


def duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def build(video: Path, manifest: Path, out: Path, *, rate: float) -> dict[str, object]:
    lines = json.loads(manifest.read_text(encoding="utf-8"))
    if not lines:
        raise SystemExit(f"{manifest} carries no narration")
    token = access_token()
    work = out.parent / ".narration"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    clips: list[tuple[float, Path, float]] = []
    for index, line in enumerate(lines):
        clip = work / f"{index:03d}.wav"
        clip.write_bytes(synthesise(str(line["say"]), token, rate=rate))
        clips.append((float(line["at"]), clip, duration(clip)))

    video_seconds = duration(video)
    # Generative voices vary a little between renders, so a line that fits on
    # paper can still spill into the next by a few hundred milliseconds — two
    # narrators talking over each other. Starts are timestamps from the
    # recording, but they are floors, not walls: a colliding line is pushed
    # later by exactly the overflow plus a breath, and the drift is absorbed by
    # the next natural gap.
    placed: list[tuple[float, Path, float]] = []
    cursor = 0.0
    for at, clip, length in clips:
        start = max(at, cursor + 0.15) if placed else at
        placed.append((start, clip, length))
        cursor = start + length
    clips = placed
    overruns = [
        {"at": at, "ends": round(at + length, 1), "say": str(lines[i]["say"])[:60]}
        for i, (at, _, length) in enumerate(clips)
        if i + 1 < len(clips) and at + length > clips[i + 1][0]
    ]

    # One delayed stream per line, mixed together: no re-encode of the picture,
    # and a line that runs long simply overlaps the next rather than shifting it.
    inputs: list[str] = ["-i", str(video)]
    for _, clip, _ in clips:
        inputs += ["-i", str(clip)]
    delays = "".join(
        f"[{index + 1}:a]adelay={int(at * 1000)}|{int(at * 1000)}[d{index}];"
        for index, (at, _, _) in enumerate(clips)
    )
    mix = "".join(f"[d{index}]" for index in range(len(clips)))
    graph = f"{delays}{mix}amix=inputs={len(clips)}:normalize=0:dropout_transition=0[a]"

    subprocess.run(
        ["ffmpeg", "-v", "error", *inputs, "-filter_complex", graph,
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", str(out), "-y"],
        check=True,
    )
    shutil.rmtree(work, ignore_errors=True)
    return {
        "video": str(out),
        "seconds": round(video_seconds, 1),
        "lines": len(clips),
        "spoken_seconds": round(sum(length for _, _, length in clips), 1),
        "voice": VOICE,
        "overruns": overruns,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--video", type=Path, default=ROOT / "web" / "demo.mp4")
    parser.add_argument("--manifest", type=Path, help="defaults to the video's .narration.json")
    parser.add_argument("--out", type=Path, help="defaults to overwriting the video in place")
    parser.add_argument("--rate", type=float, default=1.08, help="speaking rate")
    parser.add_argument("--voice", default=None, help="Chirp3-HD voice name override")
    args = parser.parse_args()

    global VOICE
    if args.voice: VOICE = args.voice
    manifest = args.manifest or args.video.with_suffix(".narration.json")
    out = args.out or args.video.with_name(f"{args.video.stem}-narrated{args.video.suffix}")
    print(json.dumps(build(args.video, manifest, out, rate=args.rate), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
