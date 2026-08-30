# Every company knows when it revoked access. None knows when access stopped.

*I built this for the [All Things Agentic Hackathon](https://allthingsagentichackathon.devpost.com/), and I wrote this post for the purposes of entering that hackathon. Code: [github.com/NexuChat/parallax](https://github.com/NexuChat/parallax)*

---

## The chore I was actually trying to kill

I maintain a web application with two roles, two languages, one of them right-to-left, a dark theme, and three viewport sizes. Every release, I would open it as the owner, click through, sign out, sign in as a member, click through again, switch to Arabic, reload, shrink the window, reload — and try to remember what a page had looked like ten minutes earlier.

The worst defects never survived that process, because they are not visible in any single session. A member opening a page they should have been denied sees nothing wrong. Nothing on the page says "you should not be here." The information is not in their session at all. It is in the *difference* between their session and the owner's.

So I stopped testing sessions and started comparing them.

## Seven witnesses, one axis apart

Parallax opens seven isolated browser contexts at the same instant against the same application. One is a baseline — owner, English, light, desktop. The other six each change **exactly one axis** from it: privilege, locale, theme, viewport.

The full product of those axes is thirty-six combinations. Seven one-axis derivations is not just cheaper; it is the only version that can attribute a cause. When the Arabic witness disagrees with the baseline and locale is the only thing that changed, locale is the reason. With thirty-six combinations you get a bigger table and less knowledge.

Each axis carries a contract about what must change and what must not:

| Axis | Contract | A finding is |
|---|---|---|
| Privilege | access **must** differ | sameness — an escalation |
| Locale | access constant, layout **mirrors** | access drift, or geometry that did not mirror |
| Theme | access constant, layout **does not move** | any positional shift |
| Viewport | access constant, reflow allowed | access drift |

That is the whole engine. Adding an axis means declaring a contract, not writing a detector.

## The axis that made me build a second engine

Then there is a claim no single-session test can express at all:

> A sends a message. B must see it within three seconds.

Run those roles sequentially and by the time B's turn arrives, A's session is closed. The claim is not hard to test sequentially — it is **structurally untestable**. Simultaneity stops being an optimisation and becomes a capability.

That gave me `PROPAGATION_FAILURE`: the sender acted, the receiver never saw it. Two live sessions, one polling the other, a deadline in milliseconds.

And once that machine existed, I noticed it was pointing at something much bigger, and it only needed its predicate inverted.

## Revocation lag

An admin removes someone from a workspace. Ask any engineer whether access ended and they will say yes — the row was deleted, the API returns 403, a new login fails.

Now ask about the tab that person **already had open**.

That tab has its data loaded. Its WebSocket is open. Its membership was resolved once and cached. It keeps working for a window that nobody measures, because nobody has a tool that measures it.

This is not theoretical. [OWASP ASVS V3](https://github.com/OWASP/ASVS) *requires* that all active sessions be revoked when an account is disabled — naming "an employee leaving the company" explicitly. The OWASP testing guide describes checking it **by hand**. There is no automated verifier. Microsoft's own continuous-access documentation admits propagation latency of up to fifteen minutes and hands the last mile back to the application. Supabase documents, as intended behaviour, that "client access policies are cached for the duration of the connection."

A standard mandates the control. A guide describes testing it manually. Zero tools do it.

Meanwhile: a fired IT contractor downloaded 1.2 million patient records **two days after termination** because his credentials were still valid. Guilty plea in February 2026, five million dollar settlement.

So Parallax measures it. The owner revokes the member in one live session while the member's already-open session is held open in another, and it reports:

```
REVOCATION · HIGH
Revocation authority ceased after 2,572ms
failed plane: effects; unmeasured: distribution, enforcement
```

## Four planes, because they fail independently

"Was access revoked?" is four questions:

1. **Decision** — was the revocation recorded?
2. **Distribution** — did it reach the backend?
3. **Enforcement** — is a *new* request refused?
4. **Effects** — did the session that was *already open* stop?

The first three pass in almost every application. The fourth is where the window lives, and it is the only one that requires a live browser: an API-layer tool has no already-open page to test.

## The mistake that taught me what I was measuring

My first version asserted on the DOM: is the thread list still visible in the revoked user's page? It reported that authority never ceased, even after fifteen seconds.

It was right, and my assertion was wrong. **A rendered page keeps its markup forever.** Revocation does not reach into someone's DOM and delete it. Authority is not what a page still *shows* — it is what an open session can still *fetch*.

Switching the assertion to a live request from the open page produced 2,572 milliseconds, matching what I measured by hand with `curl`. The tool and the human agreed, which is the only evidence I trust.

## Where the models earn their place, and where they do not

Anything measurable is measured. Overflow is `scrollWidth > clientWidth`. Contrast is the WCAG formula over computed styles. RTL mirroring is `x' = W − x − w` compared against recorded geometry. These are repeatable, which is what makes a live unedited demo survive contact with an audience.

**Gemini 3.5 Flash** gets the one question geometry cannot express. The seven witness frames are composed into a single mosaic, and the model is asked which tile disagrees with its peers. Sending one image instead of seven screenshots is not a cost trick: the outlier becomes *spatial*, and comparison is native to a single frame rather than something a model must reconstruct.

**Gemma 3** gets a different job. An early sweep of five applications produced ninety-four findings that were not defects — a number I published rather than hid. That was a detector-calibration failure, not a grouping problem; fixing page-wide duplication, contextual URLs, and unintended fixture defects brought the declared fleet to zero false positives in the later calibrated sweep. On an uncalibrated real application there can still be many legitimate findings, and Gemma can partition those by cause. It reads only summaries the deterministic layers already produced, and it cannot add to its input — an id it never received is discarded.

And a model I did **not** use: neither Veo nor Lyria appears anywhere in the engine, because generating video or audio inside a tool whose entire pitch is evidence integrity would be decoration at best and fabricated evidence at worst.

## The bug that would have cost me the whole argument

Parallax's headline is "the output is a test, not a report" — every finding becomes a failing Playwright spec you merge into CI.

Two days before the deadline I did something I should have done much earlier: I cloned my own repository from GitHub as a stranger, installed it, ran the documented first sweep, then installed Playwright and **actually ran the generated spec.**

```
Error: Error reading storage state from runs/site/storage-owner.json:
ENOENT: no such file or directory
```

The emitter had been *guessing* the credential path from the finding's URL. For a root-level route that produced the literal word "site." Every spec from a credential-free sweep — the most common case, a reviewer pointing the tool at any site — died before its first assertion.

I fixed it, re-ran, and the spec executed. Then it **passed**. Which was worse.

The finding was a tap target below 44 pixels. The assertion measured `page.locator("body")` — always larger than 44 pixels, always green. The probe knew exactly which element was too small; the type carrying that observation threw the selector away, and the emitter fell back to `body`.

A regression spec that passes while the defect is present is not a weak test. It is a lie that goes green in CI forever.

That audit found two more versions of the same lie. Propagation findings were emitted as `test.skip`, and revocation used the fifteen-second *observation window* as its acceptable lag. A session that retained authority for 2.5 seconds could therefore produce a high-severity finding and a green regression test.

The relational declaration now survives the sweep as a replay plan. Its generated spec opens the owner and member contexts together, repeats the safe form action, and polls the receiver's live effect. Revocation has two separate clocks: `max_lag_ms` is the contract, while `deadline_ms` is only the outer observation window. The generated assertion uses the former. Cross-locale and cross-theme findings similarly retain the exact geometry selector and compare two browser contexts; a dead surface asserts reachability instead of skipping.

At that final calibration, the fleet emitted 16 per-site specs and zero skips; the public tree listed 21 because `latest/` intentionally mirrored the five Workspace artifacts. `npm run verify:demo-generated` created private, mount-scoped sessions for every declared demo role, executed the JSON-reported gate, and deleted those states afterward. I executed all 21 files against the planted applications: all 21 failed their defect assertions, with zero passes and zero setup, syntax, or storage-path failures. Propagation reached its deadline, revocation exceeded its 100ms contract, RTL and theme geometry missed their invariants, and the dead route remained unreachable. The sanitized result was retained in `web/generated-spec-verification.json`; those failures were from the planted conditions, not fixture paths or guessed selectors.

## What I would tell myself at the start

**Run your own artifact.** Not the code — the *thing you hand people*. I had 226 passing tests and a deployed service, and the deliverable I lead with had never once been executed.

**A number that does not reproduce is worse than no number.** My front page claimed "8 of 14 defects found." Regenerating from HEAD gave 7 of 14 — twelve commits had silently killed the propagation finding, because moving scenarios from code to declarations left no site actually declaring one. Publish the number your current commit produces, and publish the false-positive count beside it.

**Silence is the expensive failure.** The vision lens wrapped every model call in `except Exception: continue`. When the API credits ran out, a run against a dead key was byte-identical to a run that found nothing. Every model call is now counted and reported: route, attempted, succeeded, last error.

**Let the application decide what it claims.** Parallax used to force `dir="rtl"` onto whatever page loaded and then report it for not mirroring — manufacturing the condition it reported. It now checks whether the application claims to support an axis at all, and says so when it does not:

```
"axis_summary": "1 axes exercised, 3 not applicable"
"reason": "no localized alternate, language switcher, changed lang attribute, or non-Latin text observed"
```

Saying what you did *not* test is worth more than one more finding.

---

**Stack:** Gemini 3.5 Flash on Vertex AI · Google GenAI SDK · Gemma 3 self-hosted · Cloud Run, Cloud Build, Artifact Registry, Secret Manager · Playwright + CDP · Python 3.12, no framework

**Try it:** [github.com/NexuChat/parallax](https://github.com/NexuChat/parallax)
