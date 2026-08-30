# Parallax — execution plan to raise the score from 3.7/6

Written 2026-08-30, roughly 22 hours before submissions close (2026-09-01 00:00 UTC).
Every number below is either measured in this repository or quoted from one of the
five audit reports beside this file.

---

## Where we actually stand

An independent judge simulation, restricted to what a real judge sees — the README,
`docs/architecture.png`, the live page, and no video — scored the submission:

| Criterion | Weight | Score | Why not higher |
|---|---|---|---|
| Innovation & Operational Utility | 40% | 4 / 5 | Validation is self-refereed: five demo applications we wrote, seeded with defects we planted. No evidence the tool finds anything on software we did not author. |
| Architectural Discipline & Tech Stack | 30% | 4 / 5 | No external verification signal. "316 tests" and "21/21 specs" are text a judge cannot confirm without cloning. Three different URLs appear as "the live thing". |
| Demo & Production Readiness | 30% | 2 / 5 | No video. The live page is a scoreboard to read, not a tool a judge can drive. |
| Bonus | — | 0.3 / 1.0 | The write-up and social post do not exist. Gemma is real but invisible to a judge. |

**Total as it stands: 3.7 / 6.**

The gap between that and my own earlier estimate of 4.9 was self-assessment. The
judge simulation is the number to plan against.

---

## Is 6/6 reachable? Arithmetically yes. The blocker is Demo, not bonus.

This section replaces an earlier version that was wrong, and the correction matters
enough to state plainly. That version claimed the last 0.4 of bonus was unreachable
because it would need Veo or Lyria, neither of which has an honest job inside an
evidence tool. The premise was false: **three additional Google models are already
integrated and called at runtime**, which is the rule's maximum.

The rule, quoted from the terms: *"Earn 0.2 bonus points for each additional Google
AI model successfully integrated (such as Gemma, Veo, or Lyria), up to a maximum of
0.6 total bonus points."*

| Additional model | Where it runs | Job |
|---|---|---|
| Gemma 3 (`gemma3:4b`) | `src/parallax/triage.py` | Names the shared cause behind repeated findings |
| `text-embedding-005` | `src/parallax/semantics.py` | Replaced an FNV-1a hash for content divergence |
| Cloud Translation | `src/parallax/semantics.py` | Replaced a regex that caught only missing translations |

Three models is the 0.6 cap. Add the write-up and the social post at 0.2 each and
the bonus is the full **1.0**. Veo and Lyria were never needed.

That changes the ceiling:

| | Base | Bonus | Total |
|---|---|---|---|
| Today | 3.4 | 0.3 | **3.7** |
| After P1 + P2 | 4.7 | **1.0** | **5.7** |
| If Demo reaches 5/5 | 5.0 | **1.0** | **6.0** |

**6/6 is arithmetically open.** The only thing standing in front of it is Demo &
Production Readiness reaching 5, which asks for a live, unedited demo of a
production-ready system — a judgement call against five hundred other entries that
no plan can promise. **Target 5.7, with 6.0 genuinely in reach if the video lands.**

Three things currently stop us collecting the bonus we have already earned, and all
three are cheap:

1. **Gemma is gated behind an environment variable.** Without `PARALLAX_GEMMA_URL`
   the run reports grouping as disabled, so a judge sees a model that did not run.
   Its output must appear in published evidence.
2. **Cloud Translation may be argued away as "an API, not a model."** The
   compliance audit makes exactly that objection. `text-embedding-005` is an
   unarguable Vertex model; name both precisely in the submission and let the judge
   count what they will.
3. **The write-up and the post do not exist.** `docs/BUILD-LOG.md` is written and
   needs publishing. That is 0.4 sitting on one hour of work.

---

## The plan

### P0 — the submission itself (blocking; nothing else matters if this is wrong)

**P0.1 — Fill the Devpost form.** The compliance audit found a draft still titled
"Untitled" as of 2026-08-30 02:24 UTC, and marked eleven requirements CANNOT VERIFY
purely because the form's contents are unknown. Category **Taskmaster**. Submitter
type **Individuals** — the owner is an individual, not a company, so the Startup
Excellence fields stay empty. Start date **2026-08-29** (first commit
`2026-08-29 01:34:33`, inside the window that opened 2026-08-03). Google SDK: Google
GenAI SDK. Google Cloud services: Cloud Run, Cloud Build, Artifact Registry, Secret
Manager, Vertex AI. Models: Gemini 3.5 Flash, text-embedding-005, Cloud Translation,
Gemma 3.
*Moves: eligibility from CANNOT VERIFY to MET. Cost: 30 minutes.*

**P0.2 — Record and upload the video.** Rules §8 makes this a Stage One pass/fail
item: a submission missing a required component fails viability before scoring
begins. The organisers warned on 2026-08-29 that YouTube processing "can take
anywhere from a few minutes to several hours". Upload early; the submission form can
be edited until the deadline, the video link cannot be added after it.
*Moves: Demo 2 → 3 minimum. Cost: 2 hours.*

**P0.3 — Freeze the repository at the deadline.** The rules lock everything when
submissions close, and the compliance audit flagged this as a live risk because the
repo has been committed to continuously. After 2026-08-31 17:00 PT: no commits, no
deploys, no artifact edits, until winners are announced.
*Moves: removes an eligibility challenge. Cost: none, but it is a hard stop.*

---

### P1 — the four cheap points (about four hours, all verifiable)

**P1.1 — Let the judge drive a sweep.** `POST /runs` already exists and works; the
page simply does not expose it. Add a field to the live page that accepts any URL,
posts it, and streams the resulting feed into the console that is already there. The
judge stops reading our numbers and produces their own.
> The judge's own words: a 4 "would require the live page to let a judge trigger or
> step through a real sweep (not just view a pre-computed scoreboard)".

*Moves: Demo 2 → 4. Cost: 1 hour. Highest return in the plan.*

**P1.2 — Sweep an application we did not write.** This is the objection that caps
Innovation, named in both the judge simulation and the red team: every application
we grade is one we authored and seeded. Run one sweep against a real third-party
site, publish the feed and the emitted specs alongside the graded fleet, and say
plainly what it found and what it did not.
> "even one paragraph of 'ran against X open-source app, found Y' would convert this
> from a compelling internally-graded claim into an externally-validated one."

*Moves: Innovation 4 → 5. Cost: 2 hours.*

**P1.3 — CI with a visible badge.** No `.github/workflows` exists. A judge cannot
confirm 316 tests or 21/21 specs without cloning. A workflow that runs the suite on
push, plus a badge at the top of the README, turns two asserted numbers into one
clickable fact.
*Moves: Architecture 4 → 5. Cost: 30 minutes.*

**P1.4 — One URL, and one sentence on category fit.** The README currently offers
`perallax.mlki.app`, `demo.mlki.app`, and a Cloud Run hostname without saying which
is the demo. Both are live, which makes it worse, not better: the judge has to guess.
Name one canonical URL everywhere — README, diagram, Devpost — and describe the other
two by their role. Then add the sentence the judge said was missing: why this is a
Taskmaster entry.
> The judge's deliberation sentence flagged that the project "never explains why it
> belongs in a 'Taskmaster' agentic category".

*Moves: Architecture, and removes an Innovation risk. Cost: 20 minutes.*

---

### P2 — the certain bonus (one hour, +0.4)

**P2.1 — Publish the build write-up.** `docs/BUILD-LOG.md` is already written. It
must be public, on a platform like dev.to, and must state that it was created for
this hackathon — the rules require that wording explicitly. **+0.2**

**P2.2 — Post it with the hashtag.** `#AllThingsAgenticHackathon` on X or LinkedIn.
**+0.2**

Bonus moves 0.3 → 0.7. The remaining 0.3 is not honestly reachable.

---

### P1.5 — the six findings the first draft of this plan missed

An adversarial review of this plan (`06-plan-review.md`) found fourteen errors in it.
Six were omissions of findings from the audit reports, and they are folded in here
rather than left in the reports where nobody would act on them.

**E7 — Yemen eligibility. Resolved, not open.** The compliance audit rated this
"CANNOT VERIFY, leaning MET" and ranked it highest because a wrong answer is a total
loss rather than a deduction. It resolves cleanly on the evidence. The rules name
their excluded territories explicitly — Belarus, Crimea, Cuba, Iran, Italy, North
Korea, Quebec, Russia, Sudan, Syria — and Yemen is not among them. That list is the
comprehensive US-embargo set; Yemen carries targeted designations against named
persons and entities, not a country-wide embargo, so the clause barring "residents of
US embargoed countries" does not reach an ordinary resident. Registration was also
accepted with Yemen as the country of residence, with a "You're in!" confirmation on
2026-08-11. Record the reasoning; take no further action.

**E8 — Two live deployments serving different content.** `README.md:75` links
`perallax.mlki.app` as "the live console" while the Cloud Run service is the thing
that was actually redeployed and verified. Both return 200 and they are not the same
backend. The first draft of this plan said "name one canonical URL", which does not
reach the defect: the fix is to make the canonical URL the Cloud Run service that
carries the current code, and describe the others by their role or drop them.

**E9 — `/healthz` 404s at the public URL.** Same root cause as E8. Diagnosed earlier:
the 404 carries `referrer-policy: no-referrer` and a 1568-byte HTML body, which is
Google's frontend answering, not the container — the path is reserved at the platform
edge. The handler at `service/app.py:57` is correct and returns 200 locally. Say so
in one line rather than leaving a documented endpoint that appears broken.

**E10 — No answer to prior art.** Commissioned research came back "partially taken":
TimeTrap shares the tagline but is a symbolic analyser with no HTTP dependency;
Playwright's multi-context recipe is public and free. A judge who searches will find
these. One paragraph in the README, naming them and stating the distinction —
measured against a live application in milliseconds, versus modelled at design time —
converts a liability into a credibility signal. This defends the 40% criterion and
costs ten minutes.

**E11 — Quickstart fails on stock Debian and Ubuntu.** `python -m pip install .` hits
PEP 668's `externally-managed-environment`. One line adding a virtualenv step fixes
the exact class of gap the organisers warned costs points.

**E12 — A known false-positive path that P1.1 invites.** The legacy blocked-witness
escalation fallback at `differ.py:186-199` can fire on an application other than the
demo fleet — and P1.1 exists precisely to send judges at their own applications.
Either gate the fallback behind the applicability evidence the newer oracle uses, or
state the limit where a judge running an ad-hoc sweep will see it.

---

### P3 — hardening (if time remains after P0–P2)

**P3.1 — Network sensitivity.** The red team ran the documented command against
`https://demo.mlki.app` and got 2 of 15, not 15 of 15, while five audit workers were
hitting the same Cloudflare tunnel concurrently. I re-ran it three times — twice from
this tree, once from a clean public clone with a fresh virtualenv — and got
`15 / 0 / 0 PASS` every time. The number reproduces; the finding is real anyway,
because a judge on a slow link could see what the red team saw. The failure mode fits
the diagnosis exactly: **0 false positives, 13 missed** — surfaces failing to settle
within the deadline, not a broken detector. Raise the settle timeout for remote hosts,
or document `--settle-ms` for network targets.

**P3.2 — The plan document contradicts the project.**
`/home/dev/hackathon/all-things-agentic.yaml` still describes a different project
entirely — a "Zero-Token Orchestration Fleet" targeting the Fortified Enterprise
Fleet track. It sits outside the repository, so a judge will not see it, but it
should not be cited or reused anywhere in the submission text.

**P3.3 — The "21 specs" wording.** Five of the twenty-one are `console/runs/latest/`
republished from `console/runs/workspace/`, so twenty-one files represent sixteen
distinct specs. The gate is honest and the specs all fail correctly; only the phrasing
overstates. Say sixteen distinct specs across twenty-one published files.

---

## Sequence, against the clock

| When | Item | Why in this order |
|---|---|---|
| Now → +1h | P1.1 interactive sweep | Biggest single gain, and the video should film it |
| +1h → +3h | P1.2 third-party sweep | Produces the evidence the video needs |
| +3h → +3.5h | P1.3 CI badge | Must be green before the video shows the README |
| +3.5h → +4h | P1.4 URL and category sentence | Everything downstream quotes the canonical URL |
| +4h → +6h | **P0.2 record and upload video** | Uploads early per the organisers' warning |
| +6h → +7h | P2.1 and P2.2 write-up and post | Certain +0.4, no dependencies |
| +7h → +7.5h | **P0.1 submit the form** | Editable until the deadline; submit early, refine after |
| Remaining | P3 hardening | Only if P0–P2 are all closed |
| Deadline | **P0.3 freeze** | No commits after 2026-08-31 17:00 PT |

---

## Expected result

| Criterion | Now | After plan | What moves it |
|---|---|---|---|
| Innovation 40% | 4 | **5** | Third-party sweep removes the self-refereed objection |
| Architecture 30% | 4 | **5** | CI badge and one canonical URL |
| Demo 30% | 2 | **4** | Video plus a page the judge can drive |
| Weighted base | 3.4 | **4.7** | |
| Bonus | 0.3 | **0.7** | Write-up and social post |
| **Total** | **3.7 / 6** | **≈ 5.4 / 6** | |

A fifth point in Demo would put it at 5.7. That depends on how the video lands
against five hundred others, which is not something this plan can promise.

---

## What this plan will not do

It will not claim 6/6. Reaching it would mean adding two more Google models with no
honest use, which trades a 40%-weighted criterion for 0.4 of bonus — a losing trade,
and one that contradicts the standard this project has held to throughout: every
number on the page reproduces, and nothing is claimed that cannot be demonstrated.
