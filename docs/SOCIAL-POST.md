# Social post — ready to publish

The bonus requires the hashtag `#AllThingsAgenticHackathon` and a public post on
X, LinkedIn, Instagram or Facebook. Attach `docs/architecture.png`, or a
screenshot of the console showing the `the-internet` run.

Paste the resulting post URL into the Devpost field
*"OPTIONAL for Bonus Points: Link to a social media post"*.

---

## X (fits in one post)

> Every regression tool compares a page to yesterday's copy of itself.
>
> That never catches the bug only *one kind of user* sees.
>
> Parallax runs 7 browser contexts at once — privilege, locale, theme, viewport
> — and the finding is the disagreement between them. No stored baseline, so it
> works on the first sweep of a site it has never seen.
>
> Pointed it at a public site I didn't build: 26 findings, first run. Top one —
> 20 controls fall outside a 360px viewport, zero at 768px. Verifiable by hand
> in 30 seconds.
>
> Graded on 7 apps that declare their own planted defects: 17/17 found, 0
> missed, 0 false positives — enforced in CI on every push.
>
> Gemini 3.7 Flash · gemini-embedding-001 · Gemma 4 — all on Vertex AI, deployed on Cloud Run.
>
> #AllThingsAgenticHackathon
>
> github.com/NexuChat/parallax

---

## LinkedIn (longer form)

> **The bugs that reached my users were never a diff against yesterday.**
>
> A button that only falls off screen on a phone. A page an anonymous visitor
> could reach that only members should. A message the sender saw sent and the
> receiver never got.
>
> None of those are visible to a tool that looks at one browser at a time — and
> every visual regression tool I've used compares a page against a stored copy
> of the same page. That answers "did this change since yesterday". It cannot
> answer "do two users see the same thing right now".
>
> So I built **Parallax**. It runs seven browser contexts against the same commit
> simultaneously, each differing from the baseline by exactly one property, and
> turns witness disagreement into failing Playwright specs. There is no golden
> file, so it works on the first sweep of a site it has never seen.
>
> Two things I can show rather than assert:
>
> • I pointed it at a public site I did not build. First run, no configuration:
> 26 findings. The highest severity one says an actionable control sits outside
> the viewport for the mobile witness and not for the desktop or tablet ones.
> Load that page at 360px and twenty edit/delete links fall past the right edge;
> at 768px, zero do. Thirty seconds to verify by hand.
>
> • Seven demo applications declare their own deliberate defects in code,
> including two clean controls with nothing planted. 17 of 17 found, 0 missed, 0
> false positives — and that runs in CI on every push, so the badge means the
> graded sweep passed, not just the unit tests.
>
> The most useful thing I learned came from CI disagreeing with my laptop. It
> was right: the demo asked for fonts that aren't installed everywhere, different
> fallbacks changed text metrics, and that moved an overflow measurement across
> its threshold. A number that depends on the operator's font set isn't
> reproducible, and reproducibility was the whole reason it was worth quoting.
>
> Built on Gemini 3.7 Flash via Vertex AI and the Google GenAI SDK, deployed on
> Cloud Run, with Gemma 4 grouping the findings by cause.
>
> #AllThingsAgenticHackathon
>
> Run it on your own URL: perallax.mlki.app/run.html
> Demo (3:21, one uncut browser session): perallax.mlki.app/demo.mp4
> Code: github.com/NexuChat/parallax
