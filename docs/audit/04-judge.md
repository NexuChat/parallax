# Angle 4 — Devpost Judge Simulation: Parallax

**Evidence base (judge-visible only):** `README.md` and `docs/architecture.png` from a fresh shallow clone of `https://github.com/NexuChat/parallax` into `/tmp/pxaudit/parallax-judge`, plus a live browse of `https://parallax-739478460363.us-central1.run.app`. No source tree reading beyond a `git ls-files` glance. No video exists to watch.

---

## 1. Scores (committed, single number each)

### Innovation & Operational Utility — **4/5**

The one-line idea is real and not generic: run seven browser contexts (privilege, locale, theme, viewport) *together* and treat disagreement between them as the defect, rather than asserting expected values per-context. The README's clearest, most judge-legible hook is the revocation-lag measurement:

> "Every organisation can say when it revoked a permission. None can say when access actually stopped... the sweep reports how many milliseconds the open session kept working... This cannot be done sequentially."

That is a genuinely distinctive, well-argued utility claim (cites OWASP ASVS V3 and Microsoft's own continuous-access-latency admission), not just "we added AI to testing." It reads as solving a real, named, cited gap.

Held back from 5 by: the headline validation is graded by the project against fixtures the project itself planted (own five-site "demo fleet"), which the README is honest about but which is still self-refereed evidence, not independent or third-party proof of generalization to a real, unknown application.

**What a 5 requires:** evidence, in the README/live page itself, that the tool found something real on an application it did not author and did not pre-declare defects for — even one paragraph of "ran against X open-source app, found Y" would convert this from a compelling internally-graded claim into an externally-validated one.

### Architectural Discipline & Tech Stack — **4/5**

The diagram (`docs/architecture.png`) is the strongest single artifact in this submission and better than most hackathon architecture diagrams a judge will see this cycle. In ~10 seconds it communicates: a drawn Google Cloud project boundary containing Cloud Run, Vertex AI Gemini 3.5 Flash, `text-embedding-005`, and Cloud Translation, with Gemma 3 explicitly drawn *outside* that boundary on self-hosted Ollama; a numbered 1–5 pipeline (Probe → Mirror → Applicability → Mosaic → Triage) labelled "deterministic checks decide measurements; models are reserved for visual, semantic, scenario, and language judgements"; and a "COST DISCIPLINE" callout stating "max 12 changed regions / sweep → 2 paid model calls / run." That is an unusually disciplined, judge-legible statement of where non-determinism is and isn't allowed to enter a testing tool — most submissions do not think to diagram their own cost/latitude boundaries.

The README text matches this discipline in prose: it explains routing precedence for the Gemini key (Vertex ADC → gcloud token → API key), states the exact semantic-check budget ("at most twelve changed regions... at most two paid semantic-model calls regardless of the number of visited surfaces"), and describes graceful degradation ("If embeddings fail, theme and viewport findings fall back to the content-signature mismatch and say that the comparison degraded").

Held back from 5 by: no visible independent verification signal anywhere a judge looks — no CI badge, no linked passing build, no external link confirming the "316 tests" or "21/21 generated specs" claims are anything but text. There is also a live, judge-visible inconsistency: the README's own links disagree with each other on where "the live thing" is — `https://demo.mlki.app` (front-page figures), `https://perallax.mlki.app` (a likely-typo'd domain for the "live console"), and the actual live URL provided for this audit (`parallax-739478460363.us-central1.run.app`, a Cloud Run default hostname) are three different addresses, none of which the README reconciles for a reader trying to find "the one true demo."

**What a 5 requires:** a single, consistent, working URL used everywhere (README, diagram caption, Devpost link) plus one external verification signal (CI badge, or a link to a build log a judge can click without cloning).

### Demo & Production Readiness — **2/5**

Two things pull in opposite directions here. The live page itself is a real, deployed, styled product surface — the first screen reads "One eye sees no depth. Two do." over a dark, purposeful UI with live tabs (Scoreboard / Live wall / Output) and a stats strip (15 defects found / 15 planted / 0 on control). That is a legitimate, non-trivial deployed artifact, not a stub landing page, and it directly echoes the README's numbers, which is good consistency.

But there is **no video**, and the instructions for this simulation are explicit that a real judge is required to watch at least two minutes of one, and that its absence is a first-order signal of effort, not a neutral gap. "Demo & Production Readiness" is a criterion that names "Demo" outright; a written README plus a static/read-only-looking scoreboard page cannot substitute for watching the tool actually catch the 2,572ms revocation lag happen. The Quickstart also requires Python 3.12+, a Playwright Chromium install, and either GCP Vertex credentials or a Gemini API key before a judge could reproduce anything themselves — so the live page is the only thing a time-pressed judge can actually touch, and it is presented as a scoreboard to look at, not a place to drive the tool against a URL of the judge's choosing.

**What a 3 requires:** the minimum bar is simply a video — even an unpolished screen recording of one sweep running end-to-end and producing a failing spec would satisfy the explicit judging instruction to watch it and would let the live page's polish actually count for something. **A 4** would additionally require the live page to let a judge trigger or step through a real sweep (not just view a pre-computed scoreboard) so "production readiness" is demonstrated interactively rather than asserted.

## 2. Bonus — **0.3 / 1.0**

The "Limits" section is the kind of admission the deliberation-room judge described as raising scores through honesty rather than lowering them through weakness:

> "Parallax observes rendered surfaces and discovered controls; it does not prove application policy, API authorization, or behavior outside the exercised browser flow."

and the "Grouping the noise" section volunteers its own pre-calibration failure rate ("An early pre-calibration sweep of the demo fleet produced 94 false positives") before presenting the current clean number. That is unusual candor for a hackathon README, where the norm is to hide the messy middle. I am not awarding more than 0.3 because the honesty, while real, sits inside a submission whose category fit and demo-readiness gaps (below) are large enough that bonus points can't offset them, and because the URL inconsistency noted above cuts slightly against the "maturity" signal the honesty otherwise buys.

## 3. Total

Weighted-to-5 base: 0.4×4 (Innovation) + 0.3×4 (Architecture) + 0.3×2 (Demo) = 1.6 + 1.2 + 0.6 = **3.4**
Plus bonus 0.3 → **Total as it stands, no video: 3.7 / 6.**

**What a strong video could add:** If a video opened on the live "One eye sees no depth" page, then showed one real sweep firing across the seven contexts and the console rendering the revocation-lag finding (`Revocation authority ceased after 2,572ms...; failed plane: effects`) as it happens — not a slide restating the number — Demo & Production Readiness could reasonably move from 2 to 3, moving the weighted base from 3.4 to 3.7 and the total (with the same 0.3 bonus) to roughly **4.0/6**. A video that additionally opened with an explicit, one-line statement of how this fits "Taskmaster" (see Q1 below) could also nudge Innovation from 4 toward the low end of "makes its category case," but that is a smaller, less certain effect than the Demo gain, and I am not baking either into the committed scores above.

## 4. The deliberation sentence

"Parallax runs seven browser sessions in parallel and turns the *disagreement between them* — like an already-open session that keeps working 2.5 seconds after its owner revokes it — into a failing test instead of a report, but it reads as a security-testing research tool that never explains why it belongs in a 'Taskmaster' agentic category, and it has no video to prove the live page actually does what the README says."

I can write this sentence, but it is doing double duty — half of it is praise for a real technical hook, half of it is a flag that the sentence itself has to work this hard to place the project in its own category. That difficulty is itself part of the finding: a judge skimming five hundred entries will remember the revocation-lag number before they remember what "Taskmaster" has to do with it.

## 5. Three questions this submission cannot answer from the README/diagram/live page alone

Ranked by what they cost at judging (identity/positioning risk first, then trust, then reproducibility):

1. **"Why is this in the Taskmaster category?"** Nothing in the README, the diagram, or the live page's copy ("relational browser regression," "one eye sees no depth") connects the product to task planning/execution/orchestration in the sense a "Taskmaster" category implies. A judge has to supply that bridge themselves, and if they can't, the project competes on identity against entries that state their category fit in the first sentence.
2. **"Which URL is actually the submission — `demo.mlki.app`, `perallax.mlki.app`, or the Cloud Run host I was handed?"** The README references two `mlki.app` subdomains for the "published demo target" and "live console" respectively; neither is the address this audit was given to inspect. A judge clicking the README's own links may never land on the polished page this angle saw, which undercuts the credit the live page otherwise earns.
3. **"Does 15/15, 0 false positives generalize past the bundled fleet?"** The README is explicit that "the figures on the front page come from a graded sweep of five bundled demo applications that declare their own deliberate defects in code" — a judge cannot tell from what's in front of them whether this number would survive contact with an application Parallax's own authors didn't build and didn't pre-declare defects for.

## 6. The competing entry that beats this one

A plausible Taskmaster-category rival: an agent that takes a one-line natural-language goal ("triage and close out this sprint's stale tickets"), visibly plans it into subtasks on camera, executes each step against a real tool (a ticket tracker, a calendar, a doc), and narrates a before/after state change — all inside a two-and-a-half-minute video with no setup shown, ending on a Slack message the agent itself sent as proof of completion.

That entry outranks Parallax in judges' eyes for reasons entirely visible to a judge, not engineering ones:
- **It has a video**, satisfying the explicit judging requirement this submission cannot meet at all right now; a mediocre demo shown is worth more at deliberation than a strong demo merely described.
- **Its one-sentence identity is free** — "it turns a one-line goal into a completed task, on camera" — where Parallax's best sentence (above) needs a clause explaining category fit before it lands.
- **It requires zero bridge-building to "Taskmaster."** A judge does not have to decide for themselves whether task orchestration is what's being shown; it's the whole premise.
- **It is interactive or at least legible without installing Python 3.12, Playwright, and Vertex/Gemini credentials** — the bar Parallax's own Quickstart sets for anyone who wants to reproduce anything beyond looking at the scoreboard page.

## Where the submission genuinely lands something well

- The live page's headline — "One eye sees no depth. Two do." — is the single best piece of judge-facing communication in the whole submission: it explains the core mechanic (compare contexts, not assert values) in five words, without jargon, in the first second on the page.
- The architecture diagram's drawn boundary between "Google Cloud · project" and "self-hosted · outside Google Cloud" for the Gemma component, plus the explicit "COST DISCIPLINE" callout, is a level of self-imposed rigor about where non-determinism is allowed that most submissions this size never bother to state, let alone diagram.
