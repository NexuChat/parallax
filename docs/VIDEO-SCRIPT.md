# Demo video script — ~4 minutes

Target length 3:50. Every number below is in the repository, so nothing has to be
recreated for the camera. Record at 1920×1080; the console and the demo fleet are
both readable at that size without zooming.

The hackathon requires the video to *demonstrate the backend is running on Google
Cloud*. Beat 5 is that requirement and is not optional.

---

## Beat 1 — the friction, 0:00–0:35

On camera: the Parallax console at `https://perallax.mlki.app`, idle.

> Every regression tool I have used compares a page against yesterday's copy of
> the same page. That catches what changed. It never catches what only one kind
> of user sees.
>
> The bugs that reached my users were never a diff against yesterday. A control
> that only falls off the screen on a phone. A page an anonymous visitor could
> reach that only members should. A message the sender saw sent and the receiver
> never received. Every one of those is invisible to a tool that looks at one
> browser at a time.

## Beat 2 — the idea, 0:35–1:05

On camera: `docs/architecture.png`, then the seven-context table in the README.

> Parallax runs seven browser contexts against the same page at the same time.
> Each one differs from the baseline by exactly one property — privilege,
> locale, theme, viewport. Nothing is compared against a stored screenshot. The
> finding *is* the disagreement between witnesses.
>
> That means there is no golden file to record, so it works on the first sweep of
> a site it has never seen.

## Beat 3 — the proof on a site I did not build, 1:05–2:05

**This is the beat that matters. Do not rush it.**

On camera: the console, `the-internet` run selected.

> This is a sweep of the-internet.herokuapp.com — a public site built by someone
> else, for practising browser automation. No plants, no configuration, no
> stored baseline. First run: twenty-six findings across thirteen surfaces.
>
> The highest severity one:

Read the finding from the console:

> `/challenging_dom`: an actionable control sits outside the viewport; seen by
> `owner-en-light-mobile`, not seen by `owner-en-light-desktop`,
> `owner-en-light-tablet`.

Now switch to a terminal and prove it live — this takes fifteen seconds:

```bash
# at 360px, then at 768px
```

Show the output: **20 actionable controls off-screen at 360, zero at 768.**

> Twenty edit and delete links fall outside a phone viewport. Zero fall outside
> on a tablet. No tool comparing that page against its own history would report
> this, because the page never changed. It is only visible when two witnesses
> look at the same commit and disagree.

## Beat 4 — the graded number, 2:05–2:45

On camera: the green CI badge, then `web/graded-summary.json`.

> Findings are worth nothing without a false-positive count. Five demo
> applications declare their own deliberate defects in code, including a clean
> control with nothing planted. Fifteen of fifteen found, zero missed, zero
> false positives — and the control stays at zero.
>
> That runs in CI on every push, so the badge means the graded sweep passed, not
> just the unit tests. It reproduces on a machine I do not own.

Optional, if the pace allows — the honest note lands well with judges:

> It did not always. It disagreed with my laptop because the demo asked for
> fonts that are not installed everywhere, and different text metrics move an
> overflow measurement across its threshold. The fleet now serves its own fonts.

## Beat 5 — running on Google Cloud, 2:45–3:20

**Required by the rules. Show, do not narrate.**

On camera, in this order:

1. Cloud Run console — the `parallax` service, region `us-central1`, green.
2. The `.run.app` URL in the address bar, serving the console.
3. Vertex AI logs, or a sweep's JSON summary showing
   `"model": {"name": "gemini-3.7-flash", "route": "vertex", "calls_succeeded": 25}`.

> The sweep service runs on Cloud Run. Gemini 3.7 Flash is reached through
> Vertex AI with the Google GenAI SDK — and the run reports how many calls it
> attempted and how many succeeded, so a run that silently lost the model says
> so instead of looking like a run that found nothing.

## Beat 6 — the other models, 3:20–3:40

On camera: the `triage` event in the `the-internet` feed.

> Three more Google models each do one job. Cloud Translation translates the
> baseline so the comparison is same-language, and `gemini-embedding-001` decides
> whether the meanings match — the model it replaced could not, scoring correct
> and wrong translations in bands that overlapped. Gemma 3 groups the findings by
> cause, and it runs self-hosted, so defect summaries about someone's application
> never leave the machine.

## Beat 7 — close, 3:40–3:50

> Parallax turns disagreement between simultaneous witnesses into failing
> Playwright specs you can run in your own suite. Repository and console are in
> the description.

---

## Recording checklist

- [ ] `PORT=8099 PYTHONPATH=src:demo:. python demo/serve.py` running for beat 4
- [ ] Console tab open at `perallax.mlki.app` on the `the-internet` run
- [ ] Cloud Run console tab already authenticated — do not film a login
- [ ] Terminal font large enough to read at 1080p
- [ ] No credentials, tokens, or `gcloud` output containing a token on screen
- [ ] Under 4 minutes
