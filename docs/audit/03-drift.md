# Angle 3 — Drift Audit: What Parallax Said vs. What Shipped

Scope: cross-check `all-things-agentic.yaml`, `docs/AUDIT-IDEA.log`, `docs/AUDIT-ARCHITECTURE.log`,
Codex session transcripts (`/home/dev/.codex/sessions/2026/08/{29,30}/*.jsonl`), Auctor runtime logs
(`/home/dev/.auctor/parallax-a274e548f605/logs/`), and git history against the tree at HEAD `69900d0`.
All extraction scripts and scratch text live under `/tmp/audit3/` (not in any repo).

Headline: this project self-audited unusually hard and unusually late. Both `docs/AUDIT-IDEA.log`
(16:30 UTC, 29 Aug) and `docs/AUDIT-ARCHITECTURE.log` (16:21 UTC, 29 Aug) read a broken, non-executing
tool. Commits in the following ~27 hours fixed the large majority of what they flagged, verified against
the current tree line-by-line below. The residual drift is smaller and more specific than the audit
logs alone would suggest — but it exists, and one item (item 1) is a total top-of-funnel pivot the
plan file never caught up with.

---

## 1. The plan (`all-things-agentic.yaml`) describes a different project than the one that shipped

**Promise**, `all-things-agentic.yaml:220-346` (written 28 Aug, before any code — file mtime confirms):
`project.name: "Zero-Token Orchestration Fleet"` — "Deterministic local routing with no model in the
decision path... ADK agents deployed on Cloud Run... Cloud Billing and Vertex usage metadata expose
per-call token counts." `scope.must_have` lists three concrete acceptance criteria: a zero-token router,
"ADK agents deployed on Cloud Run," and "a measured cost comparison" from Vertex usage metadata. The
demo script (`demo.steps`, lines 313-331) is a baseline-vs-zero-token cost run followed by killing a
Cloud Run revision mid-job. Note also that the file is internally inconsistent even at that stage:
`selected_idea.name` (line 210) says **"Institutional Onboarding for Agents"** while `project.name`
two lines later says **"Zero-Token Orchestration Fleet"** — two different ideas, never reconciled.

**What shipped**: none of it. Parallax (`README.md:1-3`) is "a relational browser regression system"
that runs seven Playwright contexts, diffs witness disagreement, and emits failing Playwright specs. No
deterministic zero-token router exists; no ADK is used (`docs/IDEA.md:269`: "لا يعتمد النظام على ...
Google ADK" — "the system does not depend on ... Google ADK"); no cost-ledger comparison, no
kill-a-Cloud-Run-revision demo. Google Cloud is used (Cloud Run, Vertex AI, Gemini 3.5 Flash via
`google-genai`), just for a completely different mechanism.

**Is this drift?** Judge it as **NOT drift**, with one caveat. `docs/IDEA.md:1-8` explicitly
timestamps its own pivot: "كُتبت الأطروحة الأولى في ٢٨ أغسطس ٢٠٢٦، قبل أول سطر من الكود" ("the first
thesis was written 28 Aug 2026, before the first line of code") and says the executive sections were
rewritten 30 Aug to describe the system as built. That is a disclosed pivot, not a silent one, and the
stale yaml is a planning artifact outside the repo, not a submission artifact — judges will never see
it. I could find no transcript evidence of *why* the team pivoted (the earliest captured Codex session
is 29 Aug 00:22, and the yaml predates it by nearly a full day), so I cannot certify the reasoning was
sound — only that the pivot was owned and dated, not hidden.
**Caveat / actual cost**: the yaml's own two hackathon-rule checks are now stale and could bite at
submission time if not re-verified: `requirements.google-agent-framework` (line 52-57) was marked
`warn` because "no agent implemented yet," and needs re-confirming that `google-genai` (used) actually
satisfies the rule's "GenAI SDK" clause, since ADK (the other option) was explicitly dropped.

---

## 2. Baseline check — propagation finding ("already known" per task brief): **verified NOT currently true; it was fixed, not left dead**

The brief states the propagation/relational finding died silently when scenarios moved from hardcoded
closures to data declarations, with no demo site declaring one. I verified this directly against HEAD
and it does **not** hold today:

- `src/parallax/__main__.py:283,354-355` — the CLI's `--relational-scenarios` flag is fully wired to
  the conductor (`relational_scenarios_from_data` → `Conductor(..., relational_scenarios=...)`), not
  dropped on the floor.
- `scripts/run_demo_suite.py:422-436` (`_relational_scenarios`) reads `getattr(site, "relational_scenarios", [])`
  generically from *any* site object — the old `if site.name != "workspace": return []` hard-code
  (quoted verbatim in `docs/AUDIT-IDEA.log:31`) is gone.
- `demo/sites/workspace.py:85` declares a `relational_scenarios` list in the new data format.
- `web/graded-summary.json` (generated `2026-08-30T19:35:10Z`, against the **public** `https://demo.mlki.app`,
  not localhost) reports the workspace propagation plant ("Quiet-thread messages do not reach polling
  clients") with `"verdict": "found"`, and the file's `totals` block is `15 planted / 15 found / 0 missed / 0 false_positives`.

Git history explains the timing: `git log -S"RelationalReplay"` and the commits `f350473`/`e0938b5`
(16:11-16:13, 29 Aug — *before* both audit logs were even finished) and `24793c9`/`36e23c8`
("merge(relproduct): the relational axis is a product feature," 18:28:16, 29 Aug — **after** both audit
logs) show the team reading its own audit and re-wiring the relational axis into the real sweep path
within about two hours of the critique landing.

**Classification: BUILT → REGRESSED (at some earlier point the other four audit angles evidently
inspected) → FIXED, currently working.** Report this as one of the strongest "delivered solidly" data
points in the repo, not as live drift — but flag for the other four angles that whatever they observed
reflects an earlier tree state, not HEAD.

---

## 3. `docs/AUDIT-ARCHITECTURE.log` — every numbered item checked against HEAD

| # | Recommendation (quoted) | Verified current state | Verdict |
|---|---|---|---|
| 1 | "Real findings can become passing or irrelevant Playwright specs" — escalation picked by sorting testimony names, `policy_witness` fires on *any* blocked witness regardless of relevance (`differ.py:91`, `emitter.py:23` at audit time) | `src/parallax/differ.py:110-186` now derives an `_offered_surfaces()` oracle: an escalation requires the lower-privilege witness's own rendered nav to omit a surface the baseline's nav offers (`offer_bypassed`, line 165). **However** the old blocked-witness heuristic still exists as a fallback `elif` (`differ.py:186-199`) when no offer evidence is available, so a legacy false-positive path is not fully retired — see §4 below for a related residual bug this fallback caused as late as 30 Aug. | **PARTIALLY BUILT** — primary oracle fixed, legacy fallback left in place |
| 2 | "One compositor leaks visual state across surfaces" — `_latest`/`_thumbnails`/`_changed_at` persist across surface transitions | `src/parallax/compositor.py:69-76` (`set_action`): "an old frame must never satisfy this surface's paintedness gate for a witness that is now silent" — clears `_latest`, `_thumbnails`, `_changed_at` on every surface change. `tests/test_compositor.py:220` (`set_action("second surface")`) and `tests/test_conductor.py:529` explicitly test the cross-surface case the audit's weakest-test #3 said was untested. | **FIXED**, with a matching regression test added |
| 3 | "The replay claim is false" — mosaic feed omits `Moment.changed/action/surface/settled_ms` and `MosaicFrame.composed_at`; no testimony is serialized | `src/parallax/contracts.py:133-169` (`finding_payload`, `mosaic_payload`) — confirmed still true today: `mosaic_payload` carries only `surface_id`, `seq`, `image`, and tile boxes; `finding_payload` carries witness *names* as strings, never a testimony. No `"moment"` feed-event kind exists (`conductor.py:163,169,177,191,194,202,212,572` — only `status`/`mosaic`/`finding` kinds are ever written). A browser-free specialist replay is still not possible from a completed run. | **IGNORED / still true** — but the specific "replay" *claim* is not made in current public docs (`docs/ARCHITECTURE.md:3` uses "replay" to mean re-witnessing live, not offline replay), so the false claim itself was quietly dropped even though the underlying capability gap remains |
| 4 | "Testimony is mutated after observation" despite docstring "Evidence, immutable once written" | `src/parallax/types.py:200` — `Testimony` is still a **plain `@dataclass`** (not frozen), and the docstring still says "Evidence, immutable once written." The specific *bug* — mirror defects appended directly onto shared, already-published `Testimony` objects — is fixed: `conductor.py:762-793` (`_with_mirror_observations`) now builds copies via `replace(testimony, defects=list(testimony.defects))` before mutating, so the shared-reference corruption the audit reproduced no longer happens. | **PARTIALLY BUILT** — the functional bug is fixed via copy-on-write, but the type itself remains unfrozen and the docstring's immutability claim is still literally false |
| 5 | "`AccessSpecialist` duplicates the differ" — always installed, double-counts privilege findings | `src/parallax/__main__.py:70-76`: `AccessSpecialist` removed from the default lens list; comment states "AccessSpecialist remains an opt-in compatibility lens, never a default CLI lens, so its projection cannot duplicate that work." Commit `2b354c9` ("feat(archfix): landed", 16:29:36 29 Aug) also replaced identity-based dedup (`kind,axis,surface.id`) with `Finding.id`-based `_unpublished_findings`. | **FIXED** |
| "weakest test" #1 (`test_public_spec_example_is_emitted_from_a_real_finding`) | hand-built "real finding" doesn't match the differ's actual policy rules | Not independently re-verified given budget; the underlying escalation semantics changed substantially (item 1), so this specific test's premise is likely stale either way — unverified, flag for another angle | **UNVERIFIED** |
| "weakest test" #3 (final-flush / unpainted-context) | only tests the first surface | See item 2 — a second-surface test now exists | **FIXED** |
| Delete list: "remove `RealtimeSpecialist` from the default specialist list ... it is a default no-op" | `RealtimeSpecialist` is still in the default list (`__main__.py:74`) | `src/parallax/specialists/realtime.py:11-51` shows `RealtimeSpecialist` was substantially rewritten (`fix(realtime): propagation is a claim about a declared pair, not any repaint`, commit `0c8bce1`) to do real propagation judging over `Axis.RELATIONAL` witnesses — it is no longer the no-op the audit described. | **NOT drift** — recommendation superseded by real feature work, not silently ignored |
| Delete list: `AccessSpecialist`, `Compositor.mosaic` alias, invalid hand-built example | Not fully re-checked for the latter two given budget | `AccessSpecialist` demoted (see item 5); `Compositor.mosaic` alias and the hand-built example were not re-verified | **UNVERIFIED** (2 of 3) |

---

## 4. `docs/AUDIT-IDEA.log` — the five-item "revised change list" checked against HEAD

| # | Recommendation (quoted) | Verified current state | Verdict |
|---|---|---|---|
| 1 | "Escalation predicate + `_unique_findings` in the main loop" — must key on offered-vs-reachable, not "someone else was blocked" | See §3 item 1 above — `_offered_surfaces` oracle added, `_unpublished_findings` replaces `_unique_findings`. Legacy blocked-witness fallback still present. | **PARTIALLY BUILT** |
| 2 | "Per-witness discovery" — un-freezes `?lang=en`, revives `drift`, kills phantom RTL findings | `src/parallax/conductor.py:224-231` (`_discover`) still explicitly uses only the baseline context, with a documented rationale: "Use only the baseline context to make the replay set causal and comparable... This makes a short crawl cover distinct pages before spending its remaining slots on siblings." | **CONSCIOUSLY NOT ADOPTED — this is NOT drift.** The team read the recommendation and kept single-context discovery on purpose, with a stated architectural tradeoff (causal attribution over per-witness completeness) rather than silently dropping it. The specific downstream symptoms the audit predicted (frozen `?lang=en`, phantom RTL findings) were not independently re-verified here — worth a spot-check by whichever angle covers demo correctness. |
| 3 | "Make specs executable" — write `.auth/<role>.json` incl. empty anon state, `baseURL` + relative paths, stable selectors, real two-context `expect.poll` for propagation | `src/parallax/emitter.py:74-76` now throws a clear error requiring `PARALLAX_OWNER_STORAGE_STATE`/`PARALLAX_MEMBER_STORAGE_STATE` env vars rather than a hardcoded `.auth/<role>.json` path; `README.md` documents this exactly. `emitter.py:263-317` (`RelationalReplay`) generates a real two-context `expect.poll(...)` block instead of `test.skip`. The site's own hero artifact `web/generated-example.spec.ts` uses a relative URL (`/workspace/audit`) with no embedded storage-state path and asserts the actual finding it is named after. | **FIXED** |
| 4 | "Drop viewport from content divergence; tag findings comparative" (FNV-1a hash false positives) | Superseded by a larger fix: `src/parallax/differ.py:390-470` replaced the FNV-1a hash comparison entirely with `text-embedding-005` semantic similarity (commit `4fd5a54`, 18:58:57 30 Aug — "text-embedding-005 replaces an FNV-1a hash... which cannot tell a reworded sentence from a different page"). Separately, `src/parallax/probe.js:261` now hashes `(document.querySelector('main') || document.body).innerText` instead of the whole `document.body`, closing the specific false-positive class (nav/footer reflow at narrow viewports) identified independently in a later Codex session (`/tmp/audit3/day30.txt:473-475`, ~07:40 30 Aug). | **FIXED, and exceeded** — the fix is more thorough than the recommendation asked for |
| 5 | "Clean `specs/`+`mosaics/` per run, re-grade, publish the delta" | `scripts/run_demo_suite.py:160-161,247,311,330-341` — a defined `_RUN_MANIFEST`, `shutil.rmtree(stage, ...)` before each publish, and an explicit whitelist of artifact suffixes. | **FIXED** |

---

## 5. A second, later self-audit (Codex session, 30 Aug ~07:37-08:xx) found and fixed three more bugs the two logged audits missed

This is not one of the two audit logs — it is a live debugging session inside the largest 30 Aug
transcript (`/home/dev/.codex/sessions/2026/08/30/rollout-2026-08-30T07-37-27-...jsonl`, extracted to
`/tmp/audit3/day30.txt`). It is worth surfacing because it shows the same audit-and-fix pattern
repeating a full day after the two written audits, closer to the deadline:

- **Claim** (`/tmp/audit3/day30.txt:481-485`, ~08:00 30 Aug): "الملخص يعلن أن plant escalation الحقيقي `/audit` ما زال missed" — the real `/audit` escalation plant was still being *missed* while 12 false-positive escalations fired on ordinary pages, because the blocked-witness fallback (`differ.py`, same code path as §3 item 1 / §4 item 1) fired whenever *any* unrelated privilege level was blocked anywhere on a page.
- **Verified against HEAD**: `web/graded-summary.json`'s workspace site now reports the `/audit` escalation plant as `"verdict": "found"` with the site-wide `false_positives: 0`, and `src/parallax/types.py:36` shows `Privilege.rank` ordered `anon=0 < member=1 < owner=2`, which — combined with the `differ.py:186-199` fallback's `rank >` comparison — structurally rules out the specific "member reached, anon blocked" false-positive the session described. This is consistent with, but not conclusively proven identical to, the fix; I could not find the exact commit that changed the fallback's comparison operator in the time available.
- **Claim** (`/tmp/audit3/day30.txt:489-491`): render-defect duplication across a route and its own affordances, and an offscreen check based on `documentElement.scrollWidth` instead of the viewport. **Verified fixed**: `src/parallax/probe.js:120-124` now compares `getBoundingClientRect()` against `view.width` (the actual viewport), not document scroll width.
- **Self-acknowledged gap, not independently re-verified** (`/tmp/audit3/day30.txt:526`): "نشر/تنظيف specs مغطى جزئياً؛ لا اختبار لفشل النسخ الذري أو حماية ملف يدوي باسم يبدأ `parallax-`" — spec publish/cleanup has no test for atomic-copy failure or for protecting a manually-named file that happens to start with `parallax-`. Low-severity, internal-only; **UNVERIFIED**, flagged as-is.

---

## 6. Auctor orchestration failures — checked for permanently lost feature work; found none

12 of 139 logged tasks in `/home/dev/.auctor/parallax-a274e548f605/logs/tasks/` have a genuine
own-status of `failed` (not a reference to a sibling task's failure — the first pass of grep matched 19
files but 7 of those were only mentioning another task's status inside a `git-guard` diagnostic). Of
the 12:

- 8 failed at the **planner** stage (`PLAN_STRATEGY_TOPOLOGY`, `BASE_REVISION_MISSING`,
  `PLANNER_JOB_CONTRACT_MISMATCH`, `PLANNER_LANE_FAILED`) — Auctor's own safety gate refusing to
  dispatch a bad execution graph. This is infrastructure self-protection, not lost Parallax feature
  work; none correspond to a feature absent from HEAD.
- `tasks/b0e4b018-...` (`witness-stage`, 29 Aug 04:16): the child was reworked and **approved**
  (`decision=approve`, 04:28:44) but failed at integration with `execution-base-mismatch` — a
  concurrent commit moved the base out from under it. Witness functionality exists and is exercised
  today (`src/parallax/witness.py`, commit `8a57d04`), so this was very likely superseded by a
  parallel successful lane, not lost.
- `tasks/8c4583b9-...` (`parallax-emitter-types-implementation`, 30 Aug 07:34-07:35) is the clearest
  case: the lane log (`lanes/92f1e724-...__auto__implementation.log`) shows the gemini worker returned
  exit 0 with **zero changed files and zero commits** ("ARTIFACT_ABSENT"), and the qwen fallback then
  failed with exit 127 (binary not found), so the whole task failed. The requested work — "Refine
  `src/parallax/emitter.py` and `src/parallax/types.py` so Playwright regression specs correctly detect
  planted defects" (from the task's own objective, `prompts/0f517054...txt:435-448`) — **did land**,
  just not through this task: `git log -S"RelationalReplay"` shows exactly one commit ever introduced
  that class, `59eb86c` ("Finish Parallax release verification and evidence pipeline," 08:59:53 30 Aug),
  about 85 minutes after this task failed. `src/parallax/types.py:276` (`RelationalReplay`) and
  `src/parallax/emitter.py:263-317` confirm it is present and used today.

**Classification: NOT drift.** Every traced task-level failure was either the planner correctly
rejecting a bad plan, or a failed execution lane whose goal was achieved through a different lane or a
direct commit shortly after. This is worth reporting as a genuine resilience signal for the
architecture-discipline criterion, not a gap.

---

## 7. Near-miss, caught same day: evidence was graded against localhost until 6 hours before the final commit

Commit `0c6e749` (18:25:30, 30 Aug), message quoted verbatim: "The published figures were recorded
against 127.0.0.1, which a reviewer cannot open... Grading now runs against https://demo.mlki.app, so
every number on the page can be checked by visiting the same applications the sweep visited." This is
the team's own admission that, until 6 hours before deadline day's final commit (`69900d0`,
`19:46:01Z`), the headline "15/15 found, 0 missed, 0 false positives" figures were **not
judge-verifiable** — a reviewer without repo access to spin up localhost could not check them, directly
undercutting the organizer's own stated bar ("Judges are not required to run the project; they may
score from video, description and repo alone," `all-things-agentic.yaml:21`). This was fixed the same
day, and `web/graded-summary.json`'s `"host": "https://demo.mlki.app"` confirms the fix is live in the
committed evidence file.

**Classification: PARTIALLY BUILT → FIXED same day.** Not currently live drift, but it is the kind of
gap that would have been severe (an unverifiable headline claim) had the deadline landed a day earlier
in the build. Worth flagging to whichever angle covers demo/production readiness: **confirm the actual
deployed Cloud Run revision the judges will hit is the one this evidence reflects**, since the same
30 Aug session (`/tmp/audit3/day30.txt:417,425`) separately noted "يلزم إعادة تشغيل
`parallax-demo.service`" (the demo service needs a restart) and "النسخة الحالية `parallax-00010-sqt`
قديمة ولا تحتوي `/healthz`" (the current Cloud Run revision is old and lacks `/healthz`) — I did not
verify live deployment state; that is outside this angle's read-only, no-network-egress scope.

---

## Ranked by cost at judging

1. **Testimony docstring says "immutable once written," type is not frozen** (`types.py:200`) —
   architecture-discipline criterion (30% weight) explicitly names "state management." The underlying
   mutation *bug* is fixed (copy-on-write), but the type-level contract is still false to a careful
   reader. Low probability a judge notices, moderate cost if they do (it is exactly the kind of
   discrepancy a "Best Architectural Design" reviewer would flag). **PARTIALLY BUILT.**
2. **Legacy blocked-witness escalation fallback still live** (`differ.py:186-199`) — the primary oracle
   is fixed and the demo fleet grades clean (0 false positives), but the fallback path that caused a
   documented false-positive/false-negative pair as late as the morning of 30 Aug is still in the code,
   guarded only by rank comparisons I could not trace to a specific fixing commit in the time available.
   Real but low-probability risk if a judge points Parallax at their own app rather than the demo fleet.
   **PARTIALLY BUILT, unverified whether fully closed.**
3. **Replay claim's underlying capability gap persists** (`contracts.py:133-169`) — a completed run
   still cannot be replayed through a new specialist without a browser. No current public claim asserts
   this, so judging cost is low, but it is real and unresolved. **IGNORED.**
4. **Plan-vs-shipped pivot never reconciled in the planning artifact** (`all-things-agentic.yaml`) —
   zero judging cost (the file isn't part of the submission and the pivot is disclosed in `docs/IDEA.md`),
   but flagged because it's the largest single "promise vs. shipped" gap in the whole audit and the
   yaml's two hackathon-rule checks (ADK usage, prior-code disclosure) are now stale relative to what
   actually shipped. **NOT drift**, but worth a five-minute sanity pass before submission.
5. **Deployment freshness for the judge-facing Cloud Run revision** — self-flagged by the team mid-day
   30 Aug, not independently verified here (outside this angle's read-only scope). Recommend the
   production-readiness angle confirm this explicitly.

## Delivered solidly (say so and move on)

- The propagation/relational-scenario capability the task brief said had "died silently" is, as of
  HEAD, wired end-to-end from CLI flag to demo declaration to graded evidence
  (`__main__.py:283`, `run_demo_suite.py:422-436`, `demo/sites/workspace.py:85`,
  `web/graded-summary.json`).
- The compositor cross-surface stale-wall bug (AUDIT-ARCHITECTURE #2) is fixed and has a regression
  test for exactly the scenario the audit described (`compositor.py:69-76`, `test_conductor.py:529`).
- `AccessSpecialist` duplicate-finding bug (AUDIT-ARCHITECTURE #5) is fixed by removing it from the
  default lens list (`__main__.py:70-76`).
- The emitter's executability gap (AUDIT-IDEA #3) — hardcoded `.auth/<role>.json` paths, `test.skip`
  instead of real propagation assertions — is fixed, and the site's own front-page proof artifact
  (`web/generated-example.spec.ts`) is a real, relative-URL, runnable spec.
- Content-divergence false positives from a whole-page hash were not just patched but replaced with a
  materially better mechanism (`text-embedding-005` semantic comparison, `differ.py:390-470`).
- Evidence generation was caught and switched from localhost to the public demo fleet
  (`demo.mlki.app`) the same day, before the final commit.
