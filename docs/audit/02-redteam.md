# Angle TWO: Red-Team Audit of Parallax (rival-entrant posture)

Auditor stance: attacking the submission, not reviewing it fairly. Every claim below is either
(a) a command I ran with literal output, (b) a file:line citation, or (c) explicitly labelled
**HYPOTHESIS**.

Scratch clone: `/tmp/redteam-parallax/scratch.c5XNSE/parallax`, cloned fresh from
`https://github.com/NexuChat/parallax.git` at commit `69900d0` ("docs: a diagram that leads with
its measurements, and text that matches the code"). All commands below ran from that clone, in a
Python venv at `/tmp/redteam-parallax/venv` and Node via the repo's own `npm ci`. Nothing was run
inside `/home/dev/hackathon/parallax` or any owner worktree.

---

## Ranked findings (cost to the submission, highest first)

### 1. THE HEADLINE NUMBER DOES NOT REPRODUCE. Literal, documented reproduction against the exact stated host gives 2/15, not 15/15.

The README's own reproduction recipe is:

```bash
python demo/serve.py &
python scripts/run_demo_suite.py --no-vision --host http://127.0.0.1:8080
```

and separately claims the published figure is graded against `https://demo.mlki.app`
(`web/graded-summary.json:2`, `"host": "https://demo.mlki.app"`). I ran the identical script
against that literal host, twice:

```
$ python scripts/run_demo_suite.py --no-vision --host https://demo.mlki.app
site       found  missed  false+  details
admin          0       3       0  missed:inversion@/reports, missed:drift@/exports, missed:dead@/legacy
control        0       0       0  ok
docs           0       3       0  missed:untranslated@/guide, missed:low_contrast@/, missed:divergence@/faq
shop           0       4       0  missed:offscreen_control@/checkout, missed:horizontal_overflow@/cart, missed:small_tap_target@/cart, missed:clipped@/product/<id>
workspace      2       3       0  missed:escalation@/audit, missed:rtl_not_mirrored@/threads, missed:theme_layout_shift@/threads
total          2      13       0  FAIL (exit 1)
```

Re-run with `--only admin` alone reproduced the identical 0/3 miss set deterministically (not a
flake). `curl` confirms the target routes are live and behaving as the fixtures describe
(`admin/reports` → 302, `admin/exports` → 302, `admin/legacy` → 404), so the demo fleet is up and
correctly seeded — Parallax itself simply fails to detect 13 of 15 planted defects when pointed at
the live host by the book. **0 false positives held**, but **found dropped from the claimed 15 to
2**, and the exit code is 1 (FAIL), not the claimed passing gate.

This is not an edge case or a misconfiguration on my part — it is the exact command from the
README, against the exact host named in the submission's own artifact, run twice with identical
results. Whatever produced `web/graded-summary.json`'s 15/15/0, it was not "run this script against
this host," despite that being the explicit, sole documented reproduction path.

### 2. The "21 generated specs, 0 setup failures" claim also fails literal reproduction — and the checked-in spec count doesn't even match the claim.

`web/generated-spec-verification.json:2-3` (checked into the repo I cloned) asserts
`"expected": 21, "total": 21, "failed": 21, "passed": 0, "setup_failures": []`, and the README
(lines 260-265) says "the checked release gate currently executes 21 public spec files."

Actual count in the same commit's `console/runs/`: **23** spec files
(`npx playwright test --list` → `Total: 23 tests in 23 files`), because `console/runs/latest/` is a
byte-for-byte duplicate of `console/runs/workspace/` (both produced by
`scripts/run_demo_suite.py:395-396`, `_publish_run(stage / latest_site, stage / "latest")`) —
5 of the 23 files are exact re-publications of 5 files already counted under `workspace/`. Running
the documented gate exactly as written:

```
$ python scripts/verify_demo_generated.py --base-url https://demo.mlki.app --report /tmp/redteam-parallax/verify-report.json
{
  "expected": 21, "total": 0, "failed": 0, "passed": 0,
  "setup_failures": [{"title": "environment", "message": "release manifest expects 21 specs, found 23"}],
  "verdict": "FAIL"
}
```

Zero tests even execute — the gate self-aborts on a manifest mismatch. Forcing `--expected 23` to
get past that gate and actually exercise Playwright against the live public host:

```
$ python scripts/verify_demo_generated.py --base-url https://demo.mlki.app --expected 23 --report /tmp/redteam-parallax/verify-report-23.json
{
  "expected": 23, "total": 23, "failed": 23, "passed": 0, "skipped": 0,
  "assertion_failures": 7,
  "setup_failures": [ ... 8 entries, mostly "Test timeout of 30000ms exceeded" on page.goto() ... ],
  "unclassified_failures": [ ... 6 more timeout entries ... ],
  "verdict": "FAIL"
}
```

Only 7 of 23 failed for the intended reason (an assertion mismatch); 14 failed on plain 30-second
navigation timeouts hitting `demo.mlki.app` over the network (e.g.
`navigating to "https://demo.mlki.app/admin/exports?lang=ar&theme=light", waiting until "load"` —
timeout). Note: 8 of those timeout messages were mis-bucketed into `setup_failures` by
`scripts/verify-generated-specs.mjs:76`'s classifier, which flags anything containing the
substring `config` as a setup failure — and Chromium's own launch argument
`--disable-field-trial-config` contains that substring, so the classifier's regex is falsely
triggered by browser boilerplate it logs on timeout. That's a second, independent bug, but it
doesn't rescue the headline: whichever way the 14 timeouts are bucketed, the run is **not**
"21 expected defect failures, 0 passes, 0 skips, 0 setup failures" — it is 23 files, majority
network timeouts, verdict FAIL.

Taken together with finding #1, the most parsimonious explanation is that the specs and the
detection logic are tuned to low-latency localhost conditions and do not hold up against the actual
publicly reachable `demo.mlki.app` the submission cites as its grading target — whether or not that
is also where the checked-in `graded-summary.json` and `generated-spec-verification.json` were
literally produced.

### 3. The "15/15/0" grading harness is a tautology: self-authored fixtures, self-declared answer key, exact-string matching.

`demo/sites/base.py:92-104` defines `Planted(defect, axis, route, note)` — the "ground truth" is a
hand-written dataclass the same author wrote inside the same site fixture the same detector is
graded against (`demo/sites/shop.py:64` etc., `demo/README.md`). `scripts/run_demo_suite.py:83-88`
matches a finding to a plant by exact string equality on `defect`, `axis`, and a route-shape regex
— there is no independent oracle, no held-out defect set, and no third-party site in the grading
loop at all. The commit `0c6e749` ("evidence: grade against the public demo fleet, not localhost")
only changes which host serves the *same* fixture code with the *same* planted answer key; it does
not add independence.

A secondary structural risk in the same grader: `grade_findings` (lines 91-103) computes
`matches = [item for item in unmatched if _matches(plant, item, site_name)]` and then removes
**every** matching item from the `unmatched` pool while incrementing `found` only once per plant. A
detector that fired the *same* correct defect 3 times for one planted bug would consume all 3
findings as "matched" and report 0 false positives for the duplicates — the grader cannot see
over-triggering on a location it also happens to be right about, only over-triggering elsewhere.
Given the demonstrated real-host failures above, whether this dedup masked anything in the actual
graded run is a **HYPOTHESIS** I could not confirm or refute without the original run's raw findings
list, which is not part of the repo.

A perfect self-graded score on fixtures the author wrote, using an answer key the author also
wrote, is the least surprising possible artifact — and per findings #1-#2, it is also one that does
not survive being run against the author's own named grading host.

### 4. Of the "four Google models," at least two cannot run at all during the exact process that produced the flagship number, and Gemma 3 is decoration.

Commit `4fd5a54` ("feat: four Google models...") lists: Gemini 3.5 Flash for scenario proposal,
`text-embedding-005`, Cloud Translation v2, and Gemma 3 for triage.

- **Gemini 3.5 Flash / vision specialist** (`src/parallax/specialists/layout_i18n.py:20`,
  `src/parallax/__main__.py:71-82`): gated by `_specialists(no_vision)`, which returns it only
  `if not no_vision and os.environ.get("GEMINI_API_KEY")`. The README's own reproduction command
  and `scripts/run_demo_suite.py`'s `main()` (which produced `graded-summary.json`) both pass
  `--no-vision`. This model **structurally cannot run** during the graded sweep that produced
  15/15/0.
- **Gemini 3.5 Flash / scenario proposer** (`src/parallax/proposer.py:84`, flag
  `--propose-scenarios` defined only in `src/parallax/__main__.py:41`): `scripts/run_demo_suite.py`'s
  `parse_args` (lines 630-636) exposes only `--host`, `--only`, `--no-vision`, `--max-surfaces` — there
  is **no CLI path to enable the proposer** in the grading script at all, and the flag defaults off
  everywhere else too. This model never fires in the run that produced the headline claim.
- **Gemma 3 triage** (`src/parallax/triage.py:28,62,80`): requires `PARALLAX_GEMMA_URL`, which is
  not set anywhere in `scripts/run_demo_suite.py` or the README's reproduction commands; absent it,
  `TriageReport.summary` reports `"triage disabled: no PARALLAX_GEMMA_URL configured"`. By the
  commit's own message, Gemma 3 "cannot invent a finding, change a severity, or reach a page" — it
  only relabels findings that already exist for a human reader. It is the closest thing to pure
  decoration among the four: it is off by default, off during grading, and even fully working it
  changes zero pass/fail outcomes. **Verdict: Gemma 3 is the one that's decoration** — delete it and
  nothing breaks except cosmetic grouping labels a human never sees during the graded run anyway.
- Only `text-embedding-005` and Cloud Translation v2 (`src/parallax/semantics.py:16,168`) are wired
  to run unconditionally (`configure_semantics` is called regardless of `--no-vision`,
  `src/parallax/__main__.py:287-288`) — but they require live GCP ADC credentials
  (`src/parallax/semantics.py:104-120`, `GoogleCloudTransport._headers`), which are not guaranteed
  present in whatever environment ran the grading script; on failure they degrade silently to the
  pre-existing hash comparison (by design, and openly reported as "degraded" — this specific
  fallback behavior is honestly documented and not itself a false claim).

Net: of "four Google models," a defensible count of what could have possibly executed during the
actual command that produced 15/15/0 is one or two (semantics/translation, conditional on ADC), not
four.

### 5. Prior art exists for "revocation lag" as a measured, named metric — the innovation claim is not novel-in-kind, only differently packaged.

Web searches actually run (see queries below) surfaced a directly on-point prior tool:

- **TimeTrap** (per a DEV Community post surfaced by search) is described as a tool built
  specifically "to detect delayed access revocation" — the author describes objects (subscriptions,
  caches, sessions, tokens) with events, and a rule like "cached access must end within five minutes
  of subscription revocation," reporting violation intervals as a time gap between revocation and
  actual access termination. This is the same measurement primitive Parallax reports (revocation
  event → last successful use → gap in ms), built earlier and independently. **I did not verify
  TimeTrap's source or run it — I only have the search-result description; treat the tool's exact
  scope as HYPOTHESIS, but its existence as a "measures the time gap for delayed access revocation"
  tool is a direct search hit, not a fabrication.**
- Academic prior art: an agentic-control-plane paper (arXiv:2606.20520, surfaced by search) reports
  measured revocation propagation delay (mean 2.6s, max 5.2s) as a first-class metric under a named
  polling/cache-TTL model — the same "declared revoked" vs. "access actually stopped" gap Parallax
  frames as new.
- RFC 7009 §3 (cited independently by the README itself) already frames "token keeps working until
  it expires" as a known, standardized gap requiring non-standard backend interaction — the
  *problem* is textbook OAuth/session literature, not new.
- Playwright's own documented multi-context pattern (playwright.dev auth/isolation docs, and a
  PlaywrightSolutions blog post found via search, repo
  `playwrightsolutions/playwright-practicesoftwaretesting.com`) already describes exactly the recipe
  Parallax's `_relational_spec` codegen uses: two `BrowserContext`s with independent storage state,
  logout one, assert the other's continued access — down to the "second session stays authenticated
  after the first is revoked" framing.
- Tools I searched and found **no** direct hit for a comparable timed-revocation metric: Burp
  Autorize (confirmed via search: point-in-time enforcement checking only, explicitly not a latency
  measurement — the search results say so directly), AuthMatrix, OWASP ZAP access-control testing,
  StackHawk, Escape.tech, OpenID Foundation conformance suite (confirmed via search: standards
  conformance, not a revocation-lag stopwatch).

Net assessment: the *combination* (deliberately parallel live sessions + a Playwright-generated,
CI-runnable, numeric millisecond assertion) may be a genuinely useful packaging, but the underlying
measurement — "how long does access survive after revocation" — is prior art at both the tool level
(TimeTrap) and the standards-literature level (RFC 7009, Microsoft's own documented propagation
latency, which the README itself cites). The 40%-weighted "Innovation" claim of novelty rests on
packaging, not on an unmeasured phenomenon.

Queries actually run: `"revocation lag" session authorization measurement tool milliseconds`;
`Burp Autorize session revocation latency measurement authorization testing`; `StackHawk
Escape.tech AuthMatrix OpenID Foundation conformance suite session revocation propagation delay
test`; `Playwright multiple browser contexts test session revocation "still logged in" recipe
github`.

### 6. Self-dealing: pointed at a real, non-authored public target, Parallax finds nothing — not garbage, not a crash, just silence.

OWASP Juice Shop's public demo (`https://juice-shop.herokuapp.com`) and the official
`https://demo.owasp-juice.shop` both returned HTTP 503 at test time (both appear to be
decommissioned free-tier/public demo instances — confirmed by direct `curl`, not assumed).
`zero.webappsecurity.com` failed to connect at all. I used Google's own explicitly-for-testing
public security testbed, `https://public-firing-range.appspot.com` (HTTP 200), which is
long-published specifically for scanner/tool testing and is not the author's own site.

```bash
PYTHONPATH=src python -m parallax https://public-firing-range.appspot.com \
  --out /tmp/redteam-parallax/runs/firingrange --no-vision --max-surfaces 8
# and again with --max-surfaces 64
```

Both runs: `"surfaces": 1, "testimonies": 7, "findings": 0"`, with all four axes reported
`"applicable": false` (no roles supplied → privilege n/a; no locale switcher observed → locale n/a;
no theme toggle observed → theme n/a; no viewport meta observed → viewport n/a) and **0 generated
specs**. Raising `--max-surfaces` from 8 to 64 did not increase discovery past the single homepage —
the crawler found no same-origin links to follow on a real, unfamiliar site structure.

This is not damning by itself — the "not applicable" reporting is honest by the tool's own stated
design (`README.md:158-172`), and it correctly declined to invent findings rather than hallucinating
defects. But it means the entire 15/15/0 track record is against fixtures the tool's own detectors
were tuned against, and the one real-world test I could run in scope produced zero signal and a
crawl that never left the homepage — no evidence of generalization past the bundled fixtures exists
in this audit or, as far as I can tell, in the repo.

### 7. `316 tests` includes a test that cannot pass outside the author's exact local layout — the suite is not hermetic.

README (lines 227-240) says: "python -m pip install pytest / python -m pytest -q ... it collects
316 tests." I followed that exact instruction (`pip install pytest` inside a venv located outside
the repo, then `python -m pytest -q` from the repo root):

```
FAILED tests/test_packaging.py::test_demo_verifier_builds_private_mount_scoped_states_and_cleans_them
1 failed, 315 passed in 19.66s
```

Root cause, `tests/test_packaging.py:72`:

```python
[str(ROOT / ".venv" / "bin" / "python"), str(wrapper), "--help"],
```

The test hardcodes `<repo>/.venv/bin/python` instead of `sys.executable`. Any contributor or judge
who follows the documented install steps with a virtualenv anywhere else (a global env, `venv`
instead of `.venv`, a `conda` env, CI's own venv path) gets a spurious, unrelated failure. 316 tests
*collect*; they do not all *pass* under the literal documented instructions in an environment that
isn't the author's own laptop layout.

### 8. Source-level issues (lower stakes, but real, with citations)

- **Undeclared side-channel attribute on a dataclass documented as immutable.**
  `src/parallax/types.py:201-202`: `Testimony` docstring reads *"One witness's account of one
  surface. Evidence, immutable once written."* Yet `src/parallax/conductor.py:551` does
  `testimony.offered_surfaces = offers  # type: ignore[attr-defined]` — setting an attribute that
  is not a declared dataclass field, on an object documented as immutable. The same pattern repeats
  at `src/parallax/conductor.py:774`, with an explicit code comment acknowledging that
  `dataclasses.replace()` "copies declared dataclass fields only," so the undeclared field has to be
  re-attached by hand after every `replace()` call — a documented, self-acknowledged workaround for
  data that lives outside the type's real schema, not a hidden accident, but exactly the
  "undeclared attribute used as a side channel" pattern.
- **Leaked browser context on partial construction, in generated Playwright specs.**
  `src/parallax/emitter.py:329-337` (relational spec) and `:386-401` (mirror spec) both do:
  ```js
  const senderContext = await browser.newContext(...);
  const receiverContext = await browser.newContext(...);   // if this throws...
  try { ... } finally { await Promise.all([senderContext.close(), receiverContext.close()]); }
  ```
  If the second `newContext()` call throws (e.g., a missing/invalid storage-state env var checked
  at expression-evaluation time inside that same call), the `try/finally` hasn't started yet, so
  `senderContext` — already created — is never closed. This is exactly the "opened but never
  closed" pattern requested, and it is baked into every generated relational/mirror spec the tool
  emits, not a one-off.
- **Swallowed exception with no diagnostic trace.** `src/parallax/proposer.py:144-149`:
  `_environment_client` does `except Exception: return None` with no logging of the actual error;
  the caller only ever learns the model route is `"disabled"`, never why the Vertex client
  construction failed (bad project id vs. missing ADC vs. transient network error all look
  identical downstream).
- **In-memory, non-persistent run registry with a disclosed but unresolved single point of
  failure.** `service/app.py:46`: `self.runs: dict[str, dict[str, Any]] = {}` is the sole source of
  truth for `GET /runs/<id>` status, protected by a `threading.Lock` (so it is not a data race —
  access is correctly serialized), but it is **never persisted**. `deploy/README.md` and
  `deploy/cloudrun.sh` candidly document that this is why the Cloud Run service is pinned to
  `--max-instances=1` ("a second instance would answer GET /runs/<id> with 404"). Pinning to one
  instance does not fix crash/restart loss: an OOM under "seven concurrent Chromium contexts plus
  JPEG mosaic composition" (the deploy script's own comment, describing why 512Mi wasn't enough),
  a redeploy, or routine Cloud Run host maintenance during an in-flight sweep loses that sweep's
  status with no checkpoint or resume path — disclosed as an intentional non-goal in
  `deploy/README.md`, but still a real production-readiness gap under the 30%-weighted judging
  criterion.

---

## What I could not attack (fair notice, not softening the verdict)

- The generated spec *assertion bodies* I read (`console/runs/admin/specs/parallax-dead-baseline-*`,
  `console/runs/latest/specs/parallax-revocation-relational-*`) do genuinely assert what their
  names/titles claim (dead-route reachability check; revocation-lag `<= 100ms` check against a
  measured `2,572ms` scenario) — I found no title/assertion mismatch in the specs I inspected.
- The demo fleet's fixture routes behave exactly as declared when probed directly with `curl`
  (protected routes 302 to login, the deliberately dead route 404s) — the fixtures are not
  fraudulent, they're just not run through an independent grader.
- Firing Range's zero-finding result is honest reporting under the tool's own "axis applicability"
  design, not a crash or garbage output.

---

## The one sentence for a judge

**Run the README's own reproduction command against the exact host the submission cites for its
15/15/0 headline claim, and you get 2 of 15 planted defects found on a FAIL exit code — the
flagship number is not reproducible from the project's own instructions, on the project's own named
grading target, as demonstrated live during this audit.**
