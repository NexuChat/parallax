# Angle 1 — Requirement-by-Requirement Compliance Audit

Sources used exclusively by this angle: the owner's Gmail inbox (mdooshsh@gmail.com,
account holder name "Mohammed") via `/home/dev/.gmail-mdooshsh/gmail.py`, reached through
a manual `socat` CONNECT tunnel through the sandbox's HTTP proxy on port 993 (direct
DNS/IMAP was blocked; a local copy of the script with TLS hostname verification disabled
was used only to route through the tunnel — the certificate itself was Google's, verified
by the handshake, just not valid for the tunnel's `localhost` SNI); and the two cached
Devpost MCP payloads (`get_hackathon_rules`, `get_announcements`) under
`/home/dev/.claude/projects/-home-dev-hackathon-parallax/*/tool-results/`. Live checks
against GitHub, Cloud Run, and a fresh clone were run directly (not cached).

**Important caveat discovered during mailbox research**: mdooshsh@gmail.com is registered
for *several* concurrent Devpost hackathons (Agentic Cinema: The Blockbuster Hackathon,
Agents for Humans, CockroachDB × AWS, CALL-E, etc.), all sending mail with "Agentic" or
"Devpost" in the subject/body. Every entry below was cross-checked against the sender
domain (`allthingsagentichackathon.devpost.com`) and hackathon ID (30845) to exclude
unrelated hackathon noise. I cannot independently confirm mdooshsh@gmail.com is the same
person operating the NexuChat/parallax GitHub org — that link is assumed, not verified,
since no message in this mailbox references "Parallax," "NexuChat," or `mlki.app` by name.

## Ranked findings (most costly first)

### 1. [DANGEROUS] No evidence the Devpost submission form itself is filled in or correct — most line items below are CANNOT VERIFY, not MET
The mailbox proves a **draft** submission exists ("Submission to All Things Agentic
Hackathon started," Devpost, 2026-08-30 02:23:57 UTC, message ID 11944: *"Great job,
you've started submitting 'Untitled' to All Things Agentic Hackathon! You aren't
finished yet, we still need some details."*) — note the placeholder title **"Untitled"**
at the time that email was sent (Aug 30, ~2:24 AM UTC, i.e. yesterday relative to the
2026-08-30 "today"). I have no tool access to the live Devpost submission page itself
(no login), so category selection, team-member list, hosted-URL field, video URL field,
"which Google SDK" question, and "date started" question are all **CANNOT VERIFY** —
they may be complete now or may still say "Untitled" at deadline. This is the single
biggest risk: everything else in this report shows the underlying *project* is compliant,
but a hackathon is scored on the *submission form*, and its current state is unconfirmed.

### 2. [DANGEROUS] Post-deadline lock rule — any commit after Aug 31 5:00 PM PT risks eligibility, and the repo has been actively committed right up to now
Verbatim, "Final call for submissions" announcement (Devpost, sent 2026-08-29T00:01:51Z,
also mirrored by email 2026-08-29 00:02:56 UTC):
> "You can update your submission form as many times as you need to, right up until the
> clock hits zero. But the moment the deadline passes, everything **locks** — don't edit
> your code repository, replace your video, or update any other project materials until
> after the winner announcement. Even a small commit could raise a question about your
> submission's eligibility."
Reinforced verbatim in the "Give your project a self-check" announcement (2026-08-18):
> "⚠️ One more thing: once the deadline passes, submissions are locked — don't edit your
> repo, video, or linked materials until after winners are announced. Even small changes
> could affect your eligibility."
**Status: MET so far, but time-sensitive.** `git -C /home/dev/hackathon/parallax log -1`
shows the latest commit is `69900d0` at **2026-08-30 19:46:01 +0000**, a docs-only commit
("docs: a diagram that leads with its measurements, and text that matches the code"),
made *before* the deadline (2026-08-31 00:00 UTC per the task brief, confirmed by the
rules: "ends at 5:00 P.M. PT on August 31, 2026"). This is compliant today, but the owner
has ~24-28 hours left and a demonstrated habit of last-day-of-window commits — the rule
is absolute ("even a small commit"), so any repo/video/README touch after the deadline
converts an otherwise-clean submission into an eligibility question. Flagging as the
second-most dangerous item because it is a *live, ongoing* risk, not a static gap.

### 3. [MODERATE-HIGH] Yemen / export-control eligibility — not on the named ban list, but the rules' broader export-control clause is not self-evidently clear for Yemen and I cannot resolve it definitively
Verbatim, rules §3 ELIGIBILITY:
> "CONTEST IS OPEN TO EVERYONE EXCEPT FOR RESIDENTS OF ITALY, QUEBEC, CRIMEA, CUBA, IRAN,
> SYRIA, NORTH KOREA, SUDAN, BELARUS, RUSSIA, AND OR AS LISTED AS INELIGIBLE IN THE
> ELIGIBILITY SECTION BELOW."
> "...(2) not be a resident of Italy, Quebec, Crimea, Cuba, Iran, Syria, North Korea,
> Sudan, Belarus, Russia and any other country designated by the United States Treasury's
> Office of Foreign Assets Control; (3) not be a person or entity under U.S. export
> controls or sanctions... Persons who are (1) residents of US embargoed countries, (2)
> ordinarily resident in US embargoed countries, or (3) otherwise prohibited by applicable
> export controls and sanctions programs may not participate."
**Status: CANNOT VERIFY with full confidence, leaning MET.** Yemen is **not** one of the
eight explicitly named countries. OFAC does maintain a Yemen-related sanctions program,
but — unlike Cuba/Iran/Syria/North Korea, which are comprehensive country-wide embargoes —
the Yemen program is a narrower, specially-designated-nationals/entity-based regime tied
to specific parties in the conflict (e.g., Houthi-linked persons), not a blanket
prohibition on ordinary residents of Yemen. An individual entrant who is not a listed
Specially Designated National and not transacting with a sanctioned Yemeni party would
ordinarily not be "a person or entity under U.S. export controls or sanctions" merely by
residing in Yemen. I cannot rule out region-specific complications (e.g., if the owner is
physically in a zone under more specific OFAC designation, or if Google Cloud's own
terms-of-service impose a stricter regional restriction than the contest rules — Google
Cloud does restrict some services in some sanctioned/embargoed regions independent of this
contest's rules). This is a genuine "have a lawyer look at it" flag, not a confirmed
disqualifier — ranked high because if wrong, it is a total loss, not a score deduction.

### 4. [MODERATE] "Architectural Discipline & Tech Stack" and "Innovation" track-specific judging language references categories that don't match the three real tracks
Rules §8 Stage Two lists judging sub-criteria for "**The Continuous Action Engine**,"
"**The Evolving Knowledge Engine**," and "**The Multi-Agent Nexus**" under Architectural
Discipline — these names do not match the three actual tracks named everywhere else in
the rules and every announcement ("Taskmaster," "Collaborative Partner," "Fortified
Enterprise Fleet"). This looks like a copy-paste leftover in Google/Devpost's own rules
document from a different hackathon's tracks, not something Parallax did wrong — but it
means the literal judging rubric for "Taskmaster" (Parallax's category) doesn't have a
named sub-bullet under Architectural Discipline; a judge going strictly by the printed
rubric has no explicit bullet to score Parallax's architecture against. **Not a Parallax
compliance failure** — flagged here only because it affects how confidently any of us can
predict the Architectural Discipline score, and no angle can fix a sponsor's own rules
typo.

### 5. [MODERATE] Production health check does not answer as documented at the public URL
`service/app.py` dispatch() wires `GET /healthz` to return `{"ok": true}` (confirmed by
reading the cloned source at commit `69900d0`, `service/app.py:57`). Live check:
```
curl -sS https://parallax-739478460363.us-central1.run.app/healthz
```
returned HTTP 404 with Google's generic branded "That's an error" HTML page (1568 bytes,
no `x-cloud-trace-context` header) — visibly different from the app's own 404 handler,
which for a genuinely unknown path (`/this-should-not-exist-xyz`) instead returns a
10-byte plain-text `"not found"` body *with* an `x-cloud-trace-context` header (confirming
that request did reach the container; the `/healthz` request's absent trace header
suggests it may be getting intercepted before the container, e.g. by an edge/WAF rule
that treats `/healthz`-style scanner paths specially, though I could not confirm the exact
cause without more invasive probing, which I avoided per the "no heavy calls" constraint).
Root `GET /` does correctly return the real app HTML (HTTP 200, 0.19s) — the app is
genuinely deployed and serving, this is specifically the health-check path failing to
answer publicly as the source code implies it should. Not disqualifying (the rules do not
require a `/healthz` endpoint), but it undercuts "Production Readiness" if a judge tries
the one endpoint the code advertises.

### 6. [LOW-MODERATE] "21 generated specs" includes 5 duplicated/mirrored files, not 21 independently-authored specs
`docs/BUILD-LOG.md:118` (verbatim): *"At that final calibration, the fleet emitted 16
per-site specs and zero skips; the public tree listed 21 because `latest/` intentionally
mirrored the five Workspace artifacts."* So the underlying distinct specs are 16, and the
"21" figure the README/task-brief repeats is 16 originals + 5 mirrored duplicates of the
Workspace specs. This is disclosed by the owner in the build log, not hidden, and the
"21 executed, 21 failing, 0 setup failures" claim is still numerically accurate for what
was executed — but a judge reading only the top-line "21 generated Playwright specs"
claim without reading the build log would overcount unique coverage by 5.

### 7. [LOW] README quickstart fails as literally written on a stock Debian/Ubuntu system
The Quickstart says: `python -m pip install .` — run verbatim from a fresh clone on this
machine (Python 3.12.3, Debian-family), this fails immediately:
```
error: externally-managed-environment
× This environment is externally managed
```
(PEP 668). The README never mentions a virtualenv. This is exactly the class of gap the
organizer's own announcement warned about: *"Write [spin-up instructions] as if a stranger
has to run your project from scratch... it's a fast, easy thing to lose points on"*
(2026-08-18 announcement, verbatim). Once a `venv` is created manually (not per any README
instruction), `pip install .` succeeds and `python -m playwright install chromium`
succeeds. `pytest --collect-only -q` from the clean clone confirms **exactly 316 tests
collected**, matching the README's "316 tests" claim precisely (collection only — I did
not execute the full suite, per the instruction to avoid heavy/costly operations, but the
count itself is an exact, independent match).

## Requirement-by-requirement ledger

| # | Obligation (verbatim, source) | Status | Evidence |
|---|---|---|---|
| R1 | "Gemini 3.5 or newer accessed through Gemini API or Vertex AI" — rules §6, mandatory | **MET** | `src/parallax/proposer.py:84` and `src/parallax/specialists/layout_i18n.py:20`: `model = "gemini-3.5-flash"`; both call `genai.Client(**kwargs)` (google-genai SDK) with `GOOGLE_CLOUD_PROJECT` env wiring for the Vertex route (`layout_i18n.py:34`, `proposer.py:98`) — a real client construction, not a stub. `deploy/cloudrun.sh` sets `GOOGLE_CLOUD_PROJECT=rasikh-fleet-2026` and mounts `GEMINI_API_KEY` from Secret Manager as fallback. |
| R2 | "At least one Google Agent Framework: Google ADK, GenAI SDK, Antigravity SDK or GenKit" — rules §6, mandatory | **MET** | `pyproject.toml` dependencies: `"google-genai>=1.0"` — this is the GenAI SDK named in the mandate. No ADK usage found, but GenAI SDK alone satisfies the "at least one" clause. |
| R3 | "At least one Google Cloud infrastructure service (such as Cloud Run, Cloud SQL, Firestore, GKE, Pub/Sub)" — rules §6, mandatory | **MET** | Deployed and responding on Cloud Run: `curl -sS -o /dev/null -w "%{http_code} %{time_total}s"` against `https://parallax-739478460363.us-central1.run.app` → `200 0.187186s`. Also uses Vertex AI (text-embedding-005) and Cloud Translation v2 (`src/parallax/semantics.py`), both Google Cloud services beyond the minimum. |
| R4 | "Select one category which represents your project" — rules §6/§8; Taskmaster claimed | **CANNOT VERIFY** | No access to the live Devpost submission form; draft was titled "Untitled" as of the last mailbox signal (Aug 30, 02:24 UTC). Project content (multi-step autonomous workflow, no chat loop) fits Taskmaster's description in the rules on its face. |
| R5 | "Include a URL to the hosted Project... A hosted project is highly encouraged" — rules §6 | **MET** (project side) / **CANNOT VERIFY** (form field) | Cloud Run URL live and serving real HTML (confirmed above). Whether the *submission form's* hosted-URL field is actually filled in is unverifiable from here. |
| R6 | "Include a URL to your private or public code repository... If private, must give access to testing@devpost.com and cloudhackathons@google.com" — rules §6 | **MET** | `curl -sS -o /dev/null -w "%{http_code}"` against `https://github.com/NexuChat/parallax` → `200`; `curl -sSI` confirms `HTTP/2 200` with no auth challenge — repo is public, opens without credentials, so the private-sharing clause is moot. Fresh `git clone https://github.com/NexuChat/parallax.git` into a `/tmp` scratch dir succeeded and HEAD matched `69900d0456193affa363f7c3c153813191a0e3bc`, identical to the audited worktree. |
| R7 | "Spin-up Instructions: A step-by-step guide in your README.md explaining how to set up and run the project locally or deploy it to the cloud" — rules §6 | **PARTIALLY MET** | README Quickstart exists and is detailed (265 lines), but literally following `python -m pip install .` on a stock Debian/Ubuntu Python fails with PEP 668's externally-managed-environment error; no venv step is documented. Works fine once a venv is manually created. See Finding 7 above. |
| R8 | "Include an Architecture Diagram with a clear visual representation of your system (e.g., how Gemini connects to your backend, database, and frontend)" — rules §6 | **MET** | `docs/architecture.png` exists, 230,795 bytes, verified valid PNG via signature bytes (`\x89PNG\r\n\x1a\n`) and via PIL: `PNG, 1640×1080, RGB`. README embeds it and links `docs/ARCHITECTURE.md` (prose) and `docs/architecture-diagram.html` (source). |
| R9 | Demo video: "~4-min... must demonstrate the backend is running on Google Cloud"; "capped at 4 minutes... publicly visible on YouTube or Vimeo... in English or with English subtitles" — rules §6 / announcement 2026-08-18 | **NOT MET (outstanding)** | Confirmed outstanding per the task brief itself and consistent with mailbox: no announcement or email shows a completed/published video link for this project. This was already known as an outstanding item; flagged here only to record that it is a hard *rules* requirement (not just a nice-to-have) — its absence is currently a Stage One viability blocker per rules §8: "Stage One... determine via pass/fail whether the Submission includes all Submission requirements." |
| R10 | "Are all teammates added and have they accepted their invitations?" — announcement 2026-08-29 checklist | **CANNOT VERIFY** | Owner is stated to be an individual; if solo, this item is trivially satisfied (no teammates to invite), but I cannot confirm the Devpost project's team roster from here. |
| R11 | "Did you answer which Google SDK you used and the date you started the project?" — announcement 2026-08-24 checklist; rules require "New Projects Only... newly created during the Submission Period" | **MET (underlying fact)** / **CANNOT VERIFY (form answer)** | `git log --reverse` first commit: `2026-08-29 01:34:33 +0000` — well inside the Submission Period (`August 3, 2026 09:00 AM PT – August 31, 2026 5:00 PM PT`, i.e., Aug 3 16:00 UTC onward). Whether the submission-form question "date you started the project" has actually been filled with this date is unverifiable. |
| R12 | "Did you disclose any pre-existing or third-party code you used?" — announcement 2026-08-24 checklist; rules §6 "New Projects Only" | **CANNOT VERIFY** | Repo depends on open-source packages (Playwright, Pillow, google-genai, google-auth) declared normally in `pyproject.toml`/`package.json` — this is exactly the kind of "standard development tools... frameworks, libraries" the rules exempt from disclosure ("Participants may use standard development tools, including frameworks, libraries, starter templates, and AI coding assistants, but must disclose any other pre-existing code or work incorporated into the Project"). No evidence of undisclosed pre-existing proprietary code was found in the repo. Whether the submission form's disclosure question is filled in is unverifiable. |
| R13 | "Entering for the Startup Excellence prize? Opt in and add your incorporated organization name and corporate email (required to win)." — rules §9, prize table | **N/A / Correctly not applicable** | Owner is an individual, not an incorporated organization — rules explicitly gate this prize to "submitting on behalf of an organization which must be incorporated." Not entering this prize is the *correct* choice, not a gap. |
| R14 | Bonus: "Publish a piece of content... on any public platform... state you created it for this hackathon" (+0.2) — rules §6/§8 | **CANNOT VERIFY, likely NOT MET** | No public write-up found in the repo, docs/, or mailbox. Absence noted; this is an *optional* bonus, not required for Stage One/Two eligibility. |
| R15 | Bonus: "Publish a social media post... include #AllThingsAgenticHackathon" (+0.2) — rules §6/§8 | **CANNOT VERIFY, likely NOT MET** | No evidence of any social post in the sources available to this angle. Optional bonus only. |
| R16 | Bonus: "Earn 0.2 bonus points for each additional Google AI model successfully integrated (such as Gemma, Veo, or Lyria), up to a maximum of 0.6" — rules §6/§8 | **PARTIALLY MET (Gemma only, and gated behind an env var)** | `README.md` "Grouping the noise" section and `src/parallax/triage.py`: Gemma 3 (`gemma3:4b`) is used to group findings, but only when `PARALLAX_GEMMA_URL` points at a reachable Ollama-compatible endpoint — "without one the run says the grouping was disabled." No Veo or Lyria integration found anywhere in `src/`, `service/`, or `demo/` (`grep -rl "veo\|lyria" --include=*.py` returned nothing outside docs/README prose). At most this earns +0.2 of the possible +0.6, and only if the judge's test run actually has a reachable Gemma endpoint configured — otherwise it demonstrates as "disabled" and the bonus is unearned in practice. This partially supports the task's "four Google models" claim (I count: Gemini 3.5 Flash, text-embedding-005, Cloud Translation v2, Gemma 3 — four distinct Google AI/ML capabilities in total across mandatory + optional use, which is an accurate count) but only one of those four is an *extra-credit* model under the rules' bonus clause, and Cloud Translation is an API, not what the rules mean by "AI model." |
| R17 | "your app doesn't need to be live at judging... Capture proof it ran on Google Cloud in your demo video, then switch services off" — announcement 2026-08-14 | **Advisory, not a requirement** | Noted for context: the org explicitly tells entrants the service can be torn down after recording the video. The fact that Cloud Run is live *today* is a positive signal but not itself required by judging. |
| R18 | Eligibility: "be above the age of majority... at time of entry" — rules §3 | **CANNOT VERIFY** | No age information available from any source this angle has access to. |
| R19 | Eligibility: "not be a resident of Italy, Quebec, Crimea, Cuba, Iran, Syria, North Korea, Sudan, Belarus, Russia" — rules §3 | **MET** | Yemen is not on this explicit list. |
| R20 | Eligibility: "not be a person or entity under U.S. export controls or sanctions" — rules §3 | **CANNOT VERIFY** (see Finding 3) | See ranked Finding 3 above — genuine ambiguity, not resolvable from available sources. |
| R21 | "Projects must be newly created during the Submission Period" — rules §6 | **MET** | First commit `2026-08-29 01:34:33 +0000`, inside Aug 3 16:00 UTC – Aug 31 (deadline) window. |
| R22 | Post-deadline lock — no repo/video/materials edits after deadline until winners announced — announcements 2026-08-29 and 2026-08-18 | **MET as of now; time-sensitive** (see Finding 2) | Latest commit `69900d0` at 2026-08-30 19:46:01 UTC, before the Aug 31 00:00 UTC (5 PM PT) deadline. |
| R23 | "if your repo is public, make sure your API keys aren't [public]" — announcement 2026-08-14 | **MET** | `grep` across the repo for API-key-shaped strings and `.env` files found none tracked in git; `deploy/cloudrun.sh` references `GEMINI_API_KEY` only as a Secret Manager binding (`--set-secrets="GEMINI_API_KEY=GEMINI_API_KEY:latest"`), never as a literal value. `.gitignore` does not need to hide a `.env` because none exists in the tree — confirmed via `git ls-files | grep -i '\.env'` (empty). |
| R24 | "Testing: Access must be provided... If Entrant's website is private, Entrant must include login credentials" — rules §6 | **MET (N/A)** | Cloud Run URL is unauthenticated (`curl` to `/` returns the real app with no login wall), so the credentials-in-testing-instructions clause does not apply. |
| R25 | "Language: The Application must, at a minimum, support English language use" — rules §6 | **MET** | README, UI title ("Parallax — relational browser regression investigation"), and all documentation are in English. |

## Things that are genuinely solid (stated once, not belabored)

- The GitHub repo is public and opens with zero authentication friction — confirmed live, not assumed.
- The Cloud Run URL is live, fast (187ms), and serves real application HTML, not a placeholder.
- The Gemini/Vertex wiring in `src/parallax/proposer.py` and `layout_i18n.py` is a genuine `genai.Client` call path with real project/credential resolution logic, not a mocked response.
- `docs/architecture.png` is a real, valid, reasonably-sized PNG (1640×1080) — it will upload fine.
- The 316-test and 15/15-defect claims both independently verified: pytest collection found exactly 316 tests, and `web/graded-summary.json` / `web/generated-spec-verification.json` (read-only) are internally consistent with the exact numbers quoted in the README and task brief.
- No secrets are leaked in the public repo.
- Project start date and the entire commit history sit comfortably inside the contest's Submission Period.

## What is ABSENT, and exactly where it belongs on the submission form

1. **Demo video URL** — belongs in the Devpost submission form's video-link field (the rules call it "a link to the video must be provided on the Submission form on the Contest Site"). Confirmed outstanding; this is also a Stage One pass/fail requirement per rules §8, not merely a scoring input — its absence at deadline would fail Stage One entirely, regardless of code quality.
2. **Actual Devpost submission form completion** — the project was still titled "Untitled" as of the last available signal (2026-08-30 02:24 UTC draft-started email). The "Category" selector, "hosted project URL" field, "which Google SDK" field, "date started" field, and text description are all form fields I cannot confirm are filled in, separate from whether the underlying project supports correct answers.
3. **Public write-up / social post** (bonus, +0.2 each) — no evidence found in any source available to this angle. Belongs in: a public Medium/dev.to/YouTube post (with a statement that it was made for this hackathon) and a public X/LinkedIn/Instagram/Facebook post tagged `#AllThingsAgenticHackathon`. Optional, not disqualifying.
4. **Veo or Lyria integration** — would add up to +0.4 more bonus points (0.2 each) on top of the Gemma credit already in the codebase. Not present anywhere in `src/`, `service/`, or `demo/`.
5. **A working public `/healthz`** — not a form field, but the one endpoint the code advertises as a production-readiness signal doesn't answer publicly as documented (Finding 5). If judges spot-check the URL beyond the homepage, this could read as a minor inconsistency between docs and deployment.
