# Angle 6 — Adversarial Review of the Plan (`00-PLAN.md`)

Scope: find fault only. Nothing below is a rewritten plan, a replacement schedule, or an improved
task list — only errors, gaps, and their verdicts.

**Provenance note.** This worktree (`/home/dev/.auctor/parallax-a274e548f605/worktrees/2306e40f-41d3-408d-ace8-5650408ef0c5/plan-review-attempt-2`,
HEAD `69900d0456193affa363f7c3c153813191a0e3bc`) does not itself contain `docs/audit/00-PLAN.md`
or the five reports — `docs/audit/` is untracked scratch output of the audit pipeline in the linked
main checkout, not committed to any branch this worktree can see. The six source files were read
from `/home/dev/hackathon/parallax/docs/audit/`, the only checkout holding all six at review time,
and are quoted verbatim from there. Every *repository* claim (source code, deployed hosts,
`.github/`) was independently re-checked in this worktree itself, at the same commit the plan and
all five reports were written against, not taken on the plan's or any report's word — see the
verification block under Q1 below.

**Total distinct errors found: 15** (enumerated inline as **E1**–**E15**).

---

## Repository verification used throughout this review

Three specific claims were checked directly in this working tree before trusting anything the plan
says about them:

**Does `POST /runs` genuinely accept an arbitrary URL?** `service/app.py:136-147` (`start_run`):

```python
url = body["url"]
max_surfaces = body.get("max_surfaces", 12)
if not isinstance(url, str) or not url.startswith(("http://", "https://")):
    raise ValueError("url must be an http(s) URL")
```

That is the entire validation. No host allowlist, no same-origin check — any string beginning
`http://` or `https://` is accepted and passed straight into
`[sys.executable, "-m", "parallax", url, ...]` (`app.py:160`) as a subprocess argument. **Confirmed:
`POST /runs` genuinely accepts an arbitrary URL**, exactly as the plan claims.

**Is `.github/workflows` really absent?**

```
$ ls .github/
ls: cannot access '.github/': No such file or directory
$ git ls-files | grep -i '^\.github'
(no output)
```

**Confirmed: no `.github` directory exists at all** — not just no `workflows/` subfolder.

**Are both `mlki.app` hostnames live?**

```
$ curl -sS -o /dev/null -w "%{http_code} %{time_total}s\n" --max-time 15 https://demo.mlki.app/
200 0.153683s
$ curl -sS -o /dev/null -w "%{http_code} %{time_total}s\n" --max-time 15 https://perallax.mlki.app/
200 0.120303s
```

**Confirmed: both `demo.mlki.app` and `perallax.mlki.app` return HTTP 200.** They are also confirmed
to be materially different backends (Cloudflare-fronted `perallax.mlki.app` vs. Google-Frontend
Cloud Run for the canonical service) per 05-owner-intent.md's own byte-diff — see E8 below.

---

## Q1 — Do the three claimed score gains survive contact with 04-judge.md's own stated requirements?

### P1.1 — interactive sweep, claimed "Demo 2 → 4"

Plan, line 78-85: *"**P1.1 — Let the judge drive a sweep.** `POST /runs` already exists and works;
the page simply does not expose it. Add a field to the live page that accepts any URL, posts it, and
streams the resulting feed into the console that is already there. The judge stops reading our
numbers and produces their own. ... *Moves: Demo 2 → 4. Cost: 1 hour. Highest return in the plan.*"*

Where the plan is right: the repository check above confirms `POST /runs` genuinely accepts an
arbitrary URL and is genuinely unexposed on the page (`grep -rn "runs" web/*.js web/*.html` finds
only static reads of `/console/runs/latest/feed.jsonl`, never a `POST`) — the mechanism P1.1 proposes
to build is real and does not yet exist on the page.

04-judge.md's actual sentence, line 37: *"the minimum bar is simply a video — even an unpolished
screen recording of one sweep running end-to-end and producing a failing spec would satisfy the
explicit judging instruction to watch it... **A 4** would **additionally** require the live page to
let a judge trigger or step through a real sweep (not just view a pre-computed scoreboard) so
'production readiness' is demonstrated interactively rather than asserted."*

**E1 — the plan's own quote drops the word "additionally."** Plan line 82-83 renders this as: *"The
judge's own words: a 4 'would require the live page to let a judge trigger or step through a real
sweep (not just view a pre-computed scoreboard)'."* The judge simulation states a 4 requires the
video (which alone reaches 3, per the same sentence) *plus* the interactive page — two conditions.
The plan's excerpt, and the P1.1 task line crediting "Demo 2 → 4" to itself alone, reads as if the
interactive sweep by itself is sufficient. It is not, by the judge's own sentence.

**E2 — the plan then contradicts itself on where "2" moves to.** P0.2, line 66: *"Moves: Demo 2 → 3
minimum. Cost: 2 hours."* Both P1.1 and P0.2 claim to move the same starting score of 2 to different
endpoints (4 and 3) on different task lines, hours apart, with neither line acknowledging the other
supplies half the requirement. The "Expected result" table (line 176) does credit both together —
*"Demo 30% | 2 | 4 | Video plus a page the judge can drive"* — but the per-task lines do not.

### P1.2 — third-party sweep, claimed "Innovation 4 → 5"

Plan, line 92-95, quotes 04-judge.md line 19 accurately: *"'even one paragraph of "ran against X
open-source app, found Y" would convert this from a compelling internally-graded claim into an
externally-validated one.'"* — a correctly-attributed verbatim quote.

**E3 — the gain is booked as certain even though the project's own test of exactly this scenario
found nothing.** 02-redteam.md, lines 213-232 (finding 6): pointed Parallax at a real,
unauthored public target (`https://public-firing-range.appspot.com`) at two different
`--max-surfaces` settings, and got *"'surfaces': 1, 'testimonies': 7, 'findings': 0'"* both times,
*"with all four axes reported 'applicable': false"* and *"0 generated specs."* The judge's bar is
"found Y," not "honestly reported finding nothing." Plan line 91 does say the sweep should *"say
plainly what it found and what it did not,"* the right instinct if the result is empty — but the
plan's own "Expected result" table still books the full Innovation 4→5 gain (line 174) as if a
finding were assured, without acknowledging that the one time this exact experiment was run in these
reports, it produced zero signal against a real target.

### P1.3 — CI badge, claimed "Architecture 4 → 5"

Plan, line 97-101: *"**P1.3 — CI with a visible badge.** No `.github/workflows` exists. A judge
cannot confirm 316 tests or 21/21 specs without cloning. A workflow that runs the suite on push, plus
a badge at the top of the README, turns two asserted numbers into one clickable fact. *Moves:
Architecture 4 → 5. Cost: 30 minutes.*"*

Where the plan is right: the repository check above confirms `.github/workflows` (indeed all of
`.github/`) genuinely does not exist.

04-judge.md, line 29: *"What a 5 requires: a single, consistent, working URL used everywhere
(README, diagram caption, Devpost link) **plus** one external verification signal (CI badge, or a
link to a build log a judge can click without cloning)."*

**E4 — same pattern as E1: the judge requires two things, the plan credits one task with the full
gain.** The URL-consolidation half is P1.4, a separate task scheduled after P1.3, whose own line
(112) doesn't claim a score move at all (*"Moves: Architecture, and removes an Innovation risk"* —
no number). The "Expected result" table again gets it right in aggregate (line 175: *"Architecture
30% | 4 | 5 | CI badge and one canonical URL"*), but the P1.3 per-task line overclaims what a badge
alone buys, per the judge's own quoted sentence.

**E5 — the 30-minute budget assumes the badge goes green, and two reports document reasons it
likely won't, unbudgeted anywhere in the plan.** 02-redteam.md, lines 241-262 (finding 7): running
the README's own documented `python -m pytest -q` from a clean venv gives `1 failed, 315 passed`,
root-caused to `tests/test_packaging.py:72` hardcoding `<repo>/.venv/bin/python` instead of
`sys.executable` — independently confirmed in this review (`sed -n '60,80p' tests/test_packaging.py`
shows the literal `ROOT / ".venv" / "bin" / "python"` path) — a failure any CI runner not laid out
exactly like the author's machine will hit. Separately, 02-redteam.md lines 53-73 (finding 2): the
checked-in spec-count claim (21) doesn't match the actual file count (23), so
`scripts/verify_demo_generated.py` self-aborts with `"release manifest expects 21 specs, found 23"`
before running a single test. Neither of these two concrete, already-diagnosed blockers is scheduled
anywhere in the plan — not in P1.3, not in P3. A CI workflow wired up in 30 minutes against this
repository, as it stands, has a known, already-documented path to a red badge, not the "clickable
fact" (line 100) the task promises.

---

## Q2 — Recompute the weighted totals

04-judge.md, line 49-50: *"Weighted-to-5 base: 0.4×4 (Innovation) + 0.3×4 (Architecture) + 0.3×2
(Demo) = 1.6 + 1.2 + 0.6 = **3.4**"*, *"Plus bonus 0.3 → Total as it stands, no video: **3.7 / 6**."*

Recomputed independently: 0.4×4 = 1.6; 0.3×4 = 1.2; 0.3×2 = 0.6; sum = **3.4**.
**3.4 + 0.3 = 3.7 — correct.**

Plan's projected per-criterion scores (lines 174-176): Innovation 5, Architecture 5, Demo 4. Plan
line 177-178: *"Weighted base | 3.4 | **4.7** |"*, *"Bonus | 0.3 | **0.7** |"*.

Recomputed: 0.4×5 = 2.0; 0.3×5 = 1.5; 0.3×4 = 1.2; sum = **4.7**, matching the plan.
Bonus: P2 arithmetic (lines 118-125) is 0.3 (current) + 0.2 (write-up) + 0.2 (post) = **0.7**,
matching the plan.
**4.7 + 0.7 = 5.4 — correct**, matching line 179's *"≈ 5.4 / 6."* The follow-on claim at line
181 (*"A fifth point in Demo would put it at 5.7"*) also checks out: 0.4×5 + 0.3×5 + 0.3×5 = 5.0,
+ 0.7 = 5.7.

**Both headline sums are arithmetically correct.**

**E6 — the bonus math is internally inconsistent one section above where it's stated correctly.**
Plan line 36-39: *"**The final 0.4 of bonus** requires two more Google AI models integrated
usefully."* Plan line 125: *"Bonus moves 0.3 → 0.7. **The remaining 0.3** is not honestly
reachable."* Both sentences describe the same gap — post-P2 bonus (0.7) to the 1.0 ceiling — and
0.7 + 0.3 = 1.0, so line 125's "0.3" is the figure consistent with the 1.0 cap the plan itself treats
as fixed and with 01-compliance.md's R16 (line 165): *"Earn 0.2 bonus points for each additional
Google AI model successfully integrated (such as Gemma, Veo, or Lyria), up to a maximum of 0.6"* —
combined with the write-up (+0.2, R14) and social post (+0.2, R15) caps, the bonus categories sum to
exactly 0.2+0.2+0.6 = 1.0, matching the plan's own ceiling. Line 36-39's "0.4" is never reconciled
against this: if two more models really added 0.4 more on top of 0.7, the total would be 1.1,
exceeding the cap the plan itself uses two lines later. The final total (5.4) is only internally
consistent if 0.3, not 0.4, is the correct remaining figure — the plan states both numbers without
ever flagging that they can't both be right.

---

## Q3 — Is 6/6 honestly unreachable? Test it, don't repeat it.

Plan, line 28: *"## Is 6/6 reachable? No. 5.5+ is."* and line 36-39: *"The final 0.4 of bonus
requires two more Google AI models integrated **usefully**. Veo and Lyria have no honest use inside
an evidence tool, and adding them as decoration would cost more in the Innovation criterion than the
0.4 is worth."*

01-compliance.md's rules text, R16 (line 165, quoted verbatim from the rules): *"Earn 0.2 bonus
points for each additional Google AI model successfully integrated (such as Gemma, Veo, or Lyria),
up to a maximum of 0.6."* The rule's own named examples are exactly the two the plan calls unusable.

Testing the claim rather than repeating it: the pipeline this tool runs is Probe (deterministic DOM
capture) → Mirror → Applicability → Mosaic (screenshot composition) → Triage, with model use
confined to `src/parallax/specialists/layout_i18n.py` (Gemini vision), `src/parallax/proposer.py`
(Gemini scenario proposer), `src/parallax/semantics.py` (`text-embedding-005`, Cloud Translation),
and `src/parallax/triage.py` (Gemma grouping). Veo (video generation) and Lyria (music generation)
have no input or output role anywhere in that chain — there is no step that consumes or produces
video or audio. The other plausible catalog entries for "an additional Google AI model" fare no
better on inspection: Imagen (image generation) would have to insert a synthetic image into a
pipeline that already diffs real, live-rendered screenshots; Chirp (speech-to-text) has no audio
input anywhere in a browser-DOM tool. Each of these would be added because the rubric line item
exists, not because the regression pipeline has an unmet need — precisely the "decoration" failure
mode the plan itself names for Veo/Lyria (line 189: *"a losing trade"*). **No honest, load-bearing
job for a genuine additional Google AI model exists inside this browser-based regression tool on the
current timeline; the plan's conclusion on this point survives adversarial testing.**

Where the plan is right: 6/6 is correctly unreachable on the stated arithmetic (5/5 on all three
criteria plus a full 1.0 bonus, against a judge simulation that scores two of the three criteria at
4 with named, non-trivial gaps to 5, per Q1 above).

---

## Q4 — Findings the plan does not address

Weighting 01-compliance.md and 05-owner-intent.md over the judge simulation, per instruction.

| # | Finding (report:location) | Plan coverage | Verdict |
|---|---|---|---|
| E7 | 01-compliance.md finding 3 (lines 59-83): Yemen/export-control eligibility is *"CANNOT VERIFY with full confidence... a genuine 'have a lawyer look at it' flag... ranked high because if wrong, it is a total loss, not a score deduction"* | Not mentioned anywhere in `00-PLAN.md` | **Mistake** — binary, catastrophic, and the plan's own line 4-5 claims *"every number below is either measured in this repository or quoted from one of the five audit reports"*, yet this finding is silently absent |
| E8 | 05-owner-intent.md finding 1 (lines 18-32): the owner's explicit redeploy order is half-done — `perallax.mlki.app` (the URL `README.md` actually links) is Cloudflare-fronted and serves *"materially different HTML"* from the real Cloud Run service the owner asked to be proven live | P1.4 (lines 103-112) says only *"Name one canonical URL everywhere"* — never states the candidate URLs point at different deployments with different content, so naming one doesn't fix the mismatch. Independently reconfirmed live in this review: both hosts return HTTP 200 (verification block above), consistent with the report's claim that they are two distinct, both-live backends | **Mistake** — the owner's own named top-priority item, still open, and the plan's fix doesn't reach the underlying defect |
| E9 | 01-compliance.md finding 5 (lines 99-117): the deployed `/healthz` 404s with no `x-cloud-trace-context`, unlike the documented handler | Not mentioned | **Mistake**, same root deployment-mismatch family as E8, cheap to at least flag |
| E10 | 05-owner-intent.md finding 2 (lines 34-44) and 02-redteam.md finding 5 (lines 168-211): commissioned prior-art research came back *"Partially — three separate pieces of your idea are independently taken"* (TimeTrap, RFC 7009, an arXiv paper, Playwright's own documented multi-context recipe), and *"expect a skeptical judge to say exactly that"* — no rebuttal or differentiation exists in any shipped doc | Not mentioned anywhere in `00-PLAN.md` | **Mistake** — cheap (one paragraph), threatens the 40%-weighted Innovation criterion, and is the owner's own stated top ambition (*"استحاله خسارتنا الجاىزه"* — "it's impossible for us to lose") |
| E11 | 01-compliance.md finding 7 (lines 129-144): README quickstart fails with PEP 668's `externally-managed-environment` on a stock Debian/Ubuntu system — exactly the class of gap the organizers explicitly warned costs points | Not mentioned | **Mistake** — one README line, ignored |
| E12 | 03-drift.md ranked item 2 (lines 188-193): the legacy blocked-witness escalation fallback (`differ.py:186-199`, independently reconfirmed present in this review) can still false-positive *"if a judge points Parallax at their own app rather than the demo fleet"* | Not mentioned — and P1.1 is precisely the feature that invites a judge to do exactly that | **Mistake** — the plan's own headline task raises the odds of triggering a known, named, unfixed false-positive path, with zero acknowledgment |
| — | 02-redteam.md finding 4 (lines 132-166): of "four Google models," a defensible count of what executes during the exact command that produced 15/15/0 is one or two, not four | Not mentioned; P0.1's Devpost form instructions (line 57-58) still list all four as "Models" without qualification | **Mistake in spirit, defensible in scope** — re-engineering the grading run to exercise all four models is real work outside a 7.5-hour plan, but this sits in tension with the plan's own closing claim (line 191) that *"nothing is claimed that cannot be demonstrated"* |
| — | 01-compliance.md finding 4 (lines 85-97): the rules' own judging rubric names mismatched track titles | Not mentioned | **Defensible** — the report itself says *"Not a Parallax compliance failure"* and *"no angle can fix a sponsor's own rules typo"* |
| — | 01-compliance.md finding 6 / 02-redteam.md finding 2 (21 vs. 16-23 spec-count wording) | P3.3 (lines 147-150) addresses the wording, deprioritized to "if time remains" | **Defensible** — addressed, though the underlying self-abort mechanism this wording bug causes is not (see E5) |
| — | 02-redteam.md finding 1 (lines 17-51): the headline 15/15/0 doesn't reproduce under concurrent load against the public host (2/15 observed) | P3.1 (lines 131-139) investigates, diagnoses network-settle sensitivity, and reproduces 15/0/0 three times — but is deprioritized to "if time remains" despite roughly 13-14 hours of unscheduled slack existing between the plan's 7.5-hour chain and the ~22-hour runway, and despite being, in the red team's own words, the single most damaging finding in that report | **Defensible in substance** (genuinely investigated and diagnosed) **but risky in priority** — leaving the most damaging red-team finding formally unscheduled when slack time demonstrably exists is a judgment call the plan doesn't explain |
| — | 03-drift.md ranked item 1 (`Testimony` docstring claims immutability; type is an unfrozen dataclass) | Not mentioned | **Defensible** — low probability a judge reads source this deep; the functional mutation bug is already fixed |
| — | 03-drift.md ranked item 3 (replay claim's capability gap) | Not mentioned | **Defensible** — the report itself notes no current public claim asserts replay capability, so judging cost is near zero |
| — | 03-drift.md ranked item 4 / §1 (`all-things-agentic.yaml` plan-vs-shipped pivot and its two stale rule-checks) | P3.2 (lines 141-145) covers "don't cite it," not the report's separate "five-minute sanity pass" suggestion on the yaml's stale checks | **Defensible** — report itself scores this "zero judging cost," file is outside the repo |
| — | 05-owner-intent.md finding 4 (vision-call cost question never documented) | Not mentioned | **Defensible** — cosmetic, no rubric impact |
| — | 05-owner-intent.md finding 3 (rules cross-check requested twice, no dedicated artifact) | Not restated in the plan as a distinct deliverable | **Defensible** — 01-compliance.md's requirement-by-requirement ledger functionally is that artifact, even though the plan never cites it that way |
| — | 05-owner-intent.md List 2 (*"we want all of them"* re: Veo/Lyria) vs. the plan's decision to skip them | Plan's closing section (lines 186-191) directly answers this tension, without quoting the owner | **Addressed** in substance |
| — | 01-compliance.md findings 1-2 (Devpost form "Untitled," post-deadline lock) | P0.1 and P0.3 directly address both | **Addressed** |

---

## Q5 — Sequencing against the clock

Plan, line 154 header: *"## Sequence, against the clock"*, allocating Now→+7.5h across P0-P2, with
*"Remaining | P3 hardening | Only if P0–P2 are all closed"*. The plan states (line 3) it was written
*"roughly 22 hours before submissions close"*, leaving roughly 13-14 hours of slack the sequence
table itself never allocates — P3 runs only "if time remains," and nothing else in the table absorbs
an overrun.

**E13 — dependency inversion: the canonical URL is decided after a feature is built on "the live
page."** P1.1 (line 158, Now→+1h) builds the interactive sweep box on "the live page" before P1.4
(line 161, +3.5h→+4h) decides which of the three candidate URLs *is* "the live page" — and per
05-owner-intent.md (E8 above, independently reconfirmed live in this review), the candidates are not
interchangeable: they front different deployments with different HTML. Building — and presumably
deploying — a feature to one host before deciding which host is canonical risks discovering, at hour
3.5, that the sweep box landed on the wrong one and needs to be redone or redeployed elsewhere. The
plan's own ordering puts "build a feature on the page" before "decide which page."

**E14 — no deployment time is budgeted anywhere in the four P1 tasks (Now→+4h).** Each of
P1.1-P1.4 is costed as build time only (1h, 2h, 30min, 20min). 05-owner-intent.md (lines 92-95)
documents *"12 separate container image builds"* and *"12 Cloud Run revisions"* with *"a visible
cluster of 7 rebuild/redeploy cycles inside a single 80-minute window"* during this project's own
recent deploy debugging. A schedule that treats "built" and "live for the judge/video" as the same
moment, across four tasks feeding directly into a video-recording slot, is optimistic against this
project's own measured deploy friction.

**What must precede the video (P0.2, +4h→+6h), correctly, per the plan's own ordering:** P1.1 (line
158, *"the video should film it"*), P1.2 (line 159, *"Produces the evidence the video needs"*), P1.3
(line 160, *"Must be green before the video shows the README"*), P1.4 (line 161, *"Everything
downstream quotes the canonical URL"*). The stated intent — matching the task constraint that the
video films the interactive sweep and the CI badge must be green before the README is on camera — is
sound in ordering. The defect is not the *order* of these four relative to the video; it is that
P1.3's "green" (E5) and P1.4's "canonical" (E13) are each less certain to hold on schedule than the
plan assumes, and nothing downstream checks either before recording starts.

**What breaks if a single item overruns by one hour:** the Now→+7.5h chain has no slack built into
it — P1 runs directly into P0.2, which runs directly into P2, which runs directly into P0.1. A
one-hour overrun in any of P1.1-P1.4 (the four items carrying E1-E5, E13, E14) delays the video slot
by the same hour, directly eroding the margin the plan itself invokes for recording early (line 63-65:
the organizers' own warning that YouTube processing *"can take anywhere from a few minutes to several
hours"*). A forced re-record is triggered either if the CI badge is not actually green when P0.2
begins recording (the task's own explicit constraint — E5 shows a known, unbudgeted path to a red
badge) or if P1.1's interactive sweep is later found pointed at a non-canonical host once P1.4
resolves it (E13) — either failure means re-shooting footage already captured, not merely delaying an
unstarted task.

---

## Q6 — The single biggest risk: the plan followed perfectly, and still losing

Every item in P0-P2 could execute exactly as written — form filled, video recorded and uploaded,
sweep box live, third-party sweep run, CI badge green, one canonical URL everywhere, write-up and
post published, repository frozen on time — and the submission can still lose outright for a reason
the plan never engages: **E7**, 01-compliance.md's finding 3 (lines 59-83), the unresolved
Yemen/export-control eligibility question, which the report itself ranks by exactly this property:
*"This is a genuine 'have a lawyer look at it' flag, not a confirmed disqualifier — ranked high
because if wrong, it is a total loss, not a score deduction."*

This is qualitatively different from every other gap in this review. Score-affecting risks (E1-E6,
E8-E12) can be partially offset by strong execution elsewhere in the rubric; the scheduling risks
(E13-E14) cost time, not the whole submission. An eligibility disqualification is binary and external
to the rubric — no amount of polish on the video, the README, the CI badge, or the write-up changes
whether the contest's export-control clause applies to the owner. The plan's own introduction (line
4-5) claims *"every number below is either measured in this repository or quoted from one of the
five audit reports beside this file"* — but this specific, highest-consequence finding from one of
those five reports is quoted nowhere in the plan, investigated nowhere, and allocated zero hours
anywhere in the Now→+7.5h sequence or the P3 hardening list. A plan that reaches 5.4/6 on every
criterion it tracks, and is disqualified before scoring begins, has lost from the submission's
perspective.

**E15 — the plan's own stated evidentiary standard ("every number... measured or quoted from one of
the five reports") is itself the claim that E7 falsifies.** The gap is not merely an omission of one
finding; it contradicts the plan's explicit methodological promise about its own sourcing.
