# The demo video is produced, not performed

`web/demo.mp4` (3:21, 1920×1080, narrated) is generated end to end by two
commands, and that is deliberate: a hackathon that requires an *unedited, live*
demo is better served by a recording nobody could have edited than by a screen
capture taken on trust.

```bash
python scripts/record_demo.py  --out /tmp/demo.webm     # one continuous browser session
python scripts/narrate_demo.py --video /tmp/demo.mp4    # Google Cloud TTS narration
```

## What the recording actually is

One Playwright video of one browser session, no cuts. The stage
(`demo/stage.html`) frames real sessions side by side — each pane is a genuine
browser context against the deployed hosts — and a caption bar driven by the
same script that paces the beats. Nothing framed is a mock-up.

The beats, in order:

1. **The thesis** — the landing page and the seven-witness derivation.
2. **The value** — the architecture diagram: URL in, failing tests and a pull
   request out.
3. **The wall** — the published sweep of `the-internet.herokuapp.com` replayed
   frame by frame, then one witness opened full-screen in the inspector.
4. **The protocol** — *the beat that matters.* The choreography engine plays the
   seven-step game against the deployed arena with its own two sessions; nobody
   scripts a click. The ledger beside the boards is the engine's own per-step
   verification — `samir must see it — never appeared` is read from the
   `StepResult`, not typed into a caption. The verdict shown is the finding.
5. **The call** — three live WebRTC peers; the mute that mutes nothing; the
   observer who chose silence and is correctly not reported.
6. **The graded number** — 17/17/0 read live from `graded-summary.json`.
7. **Google Cloud** — the service at its own `.run.app` URL beside its data.
8. **A sweep, right now** — `/run.html` on Cloud Run sweeps an external site
   during the recording; the closing caption reads the real finding count off
   the page, because the beat *waits for the sweep* rather than timing it.
9. **The pull request** — navigated to on GitHub, not screenshotted: a real PR
   opened by a sweep, one commit per finding.

## How the narration stays in sync

Two beats wait for real work (the live sweep, the played protocol) and take as
long as they take. So the recorder stamps every headline line with the second it
appeared on screen (`demo.narration.json`), and `narrate_demo.py` synthesises
each line with **Cloud Text-to-Speech** (`en-US-Chirp3-HD-Charon`), pads it to
its own timestamp, and mixes the track under the untouched picture. The video
stream is stream-copied — narration cannot alter a frame of what was recorded.
The tool reports any line that would overrun its slot; the published render has
zero.

## If a judge asks what is missing

- The two multi-session finding kinds are reported and graded but do not become
  generated specs; the emitter declines what it cannot express honestly.
- The locale axis reports itself not applicable on monolingual applications —
  that is the correct answer, not a gap.
- The real-time call fixture is swept alone because a loaded machine negotiates
  WebRTC more slowly, and silence would read as a room that worked.
