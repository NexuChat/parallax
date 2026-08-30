# Parallax

Parallax is a browser-based regression investigator for an existing web application. It visits the same discovered surfaces from seven isolated contexts, records what each context can reach and what it renders, then turns broken expectations into findings and Playwright regression specs. The live console is available at [perallax.mlki.app](https://perallax.mlki.app).

![Parallax architecture](docs/architecture.png)

The diagram above is the whole system on one page: what runs on Google Cloud,
how Gemini is reached, where state lives, and what a run leaves behind. Its
source is [`docs/architecture-diagram.html`](docs/architecture-diagram.html), and
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) is the prose version.

## Quickstart

Parallax requires Python 3.12+, Chromium for Playwright, and its runtime packages. From the repository root, install the runtime packages and the browser:

```bash
python -m pip install .
python -m playwright install chromium
```

Installing the package brings in Playwright, Pillow and `google-genai`; the second
command downloads the browser build Playwright drives.

Run a deterministic sweep. `PYTHONPATH=src` runs the package directly from this checkout; `--no-vision` makes the run independent of a Gemini API key.

```bash
PYTHONPATH=src python -m parallax https://app.example.com --out runs/first --no-vision
```

To include authenticated contexts, supply Playwright storage-state files for the roles your application uses:

```bash
PYTHONPATH=src python -m parallax https://app.example.com --out runs/first --storage-state owner=.auth/owner.json --storage-state member=.auth/member.json --no-vision
```

To test a sender-to-receiver claim while both role sessions are open, add `--relational-scenarios` with a data-only JSON file. It supports a fixed form submission action and either a visible receiver selector or a JSON response membership check—no JavaScript from the file is evaluated. For example, save this complete file as `scenarios.json`:

```json
{
  "scenarios": [
    {
      "surface": "/threads",
      "sender": "owner",
      "receiver": "member",
      "action": {
        "type": "submit_form",
        "form": "form.composer",
        "checks": ["input[value='quiet']"],
        "fills": [{"selector": "#message", "value": "Parallax propagation check"}]
      },
      "effect": {
        "type": "json_contains",
        "url": "api/messages?since=0",
        "items": "messages",
        "field": "text",
        "equals": "Parallax propagation check"
      },
      "deadline_ms": 3000
    }
  ]
}
```

Run it with the same role states: `PYTHONPATH=src python -m parallax https://app.example.com --storage-state owner=.auth/owner.json --storage-state member=.auth/member.json --relational-scenarios scenarios.json --no-vision`. Each scenario needs `surface`, `sender`, `receiver`, `action`, `effect`, and a positive `deadline_ms`; roles are `anon`, `member`, or `owner`. A `visible` effect is `{ "type": "visible", "selector": ".notification" }`. The final JSON summary reports both `relational_scenarios.ran` and `relational_scenarios.findings`.

Demo sites can opt in without suite-specific code: declare a `relational_scenarios` list beside `accounts` and `planted`, with entries in this same format. Their `surface` may be the site-local path such as `/threads`; the suite mounts it below the site's name before passing it to the conductor.

Open `console/index.html?feed=../runs/first/feed.jsonl` in the repository's console, or use the [live console](https://perallax.mlki.app). The local console reads the newline-delimited feed and its referenced mosaics; serving the repository with a static web server avoids browser `file:` restrictions.

The command also accepts `--max-surfaces`, `--settle-ms`, and `--headed`. Omit `--no-vision` to enable the Gemini layout and i18n lens. It chooses the first available route: a configured Vertex AI project (`GOOGLE_CLOUD_PROJECT`, with optional `GOOGLE_CLOUD_LOCATION`, defaulting to `global`) using application-default credentials or a fresh `gcloud auth print-access-token` bearer token; then `GEMINI_API_KEY` for AI Studio. The CLI prints the selected route, or explains why the lens is disabled, before the sweep starts.

## What a run produces

Everything for one run is written below `--out`:

- `feed.jsonl` is the append-only event feed consumed by the console.
- `mosaics/` contains JPEG walls for settled visual moments.
- `specs/` contains one generated failing Playwright `.spec.ts` per finding.
- The command prints totals for discovered surfaces, testimonies, findings, severity counts, feed path, and generated specs.

## Reading a finding

A finding identifies a surface, the axis under test, a severity, a short summary, and its supporting testimonies. The evidence line lists each witness context and outcome, for example `owner-en-light-desktop=reached · owner-ar-light-desktop=blocked`. `render` findings come from an observed defect such as overflow or contrast; `drift` means a non-privilege context changed reachability; `escalation` and `inversion` describe unexpected privilege results; `divergence` marks changed content; `propagation` is a missed sender-to-receiver update; and `dead` means no usable testimony reached the surface.

## The seven contexts

Parallax starts with `owner-en-light-desktop` and changes exactly one axis at a time:

| Context | Changed axis |
| --- | --- |
| `owner-en-light-desktop` | baseline |
| `member-en-light-desktop` | privilege |
| `anon-en-light-desktop` | privilege |
| `owner-ar-light-desktop` | locale |
| `owner-en-dark-desktop` | theme |
| `owner-en-light-mobile` | viewport, 360 × 740 |
| `owner-en-light-tablet` | viewport, 768 × 1024 |

There are two expectations. Privilege is the exception: access should narrow as privilege falls, so an anonymous or member witness reaching a surface that the owner also reaches is reported as an escalation. Locale, theme, and viewport are equivalence axes: changing one must not change what the user can reach; theme and viewport are also checked for unexpected content changes. The locale comparison additionally checks that geometry is mirrored for right-to-left rendering, while the theme comparison requires unchanged layout geometry.

## Limits

Parallax observes rendered surfaces and discovered controls; it does not prove application policy, API authorization, or behavior outside the exercised browser flow. It uses the role storage states you supply, so a missing or incorrect role state limits what its privilege witnesses can establish. Evidence is tiered on purpose. Anything a page can be measured for — overflow, contrast ratio, mirrored geometry, tap-target size — is decided by the in-page probe, because a measurement is repeatable and a model's opinion is not; that is what makes a live unedited run reproducible. Gemini 3.5 Flash is given the one question geometry cannot express: shown all seven witness tiles composed into a single frame, which tile disagrees with its peers. Its verdicts are accepted only when they name a real tile, and they are labelled with their source in the feed. Running with `--no-vision` therefore removes cross-tile visual comparison and leaves every measured check intact.

## Revocation lag

Every organisation can say when it revoked a permission. None can say when access
actually stopped. OWASP ASVS V3 requires that all active sessions be revoked when
an account is disabled, the OWASP testing guide describes checking that by hand,
and no automated verifier exists; Microsoft's own continuous-access documentation
admits propagation latency of up to fifteen minutes and leaves the last mile to
the application.

Parallax measures that last mile. An owner revokes a member in one live session
while the member's already-open session is held open in another, and the sweep
reports how many milliseconds the open session kept working. This cannot be done
sequentially: run the roles one after another and the already-open session — the
entire subject of the test — is gone before the second role starts.

The result names which of four planes failed, because they fail independently:
the revoke was **recorded**, it **propagated** to the backend, a **new** request
is refused — and the session already open kept reading anyway. That last plane is
the one nobody measures, and the bundled workspace demo plants exactly that
failure, a per-session membership cache re-read on a delay:

```
REVOCATION · HIGH
Revocation authority ceased after 2,499ms; failed plane: effects
```

Authority is not what a rendered page still shows — markup survives revocation
indefinitely — so the assertion has to be a live request from the open session.
Declare one the same way as any other relational scenario, with `"type":
"revocation"`.

## Axis applicability

An axis is judged only where the application shows evidence of claiming it: a
localized alternate or language switcher for locale, a `prefers-color-scheme`
query or theme toggle for theme, a viewport meta for viewport, supplied role
states for privilege. Anything else is reported as not applicable, with the
reason, and produces no findings.

This is a correctness rule, not a convenience. Forcing `dir="rtl"` onto an
application with no Arabic support and then reporting it for not mirroring is the
tool inventing its own evidence. Every run prints what it did not test:

```
"axis_summary": "1 axes exercised, 3 not applicable"
```

## Grouping the noise

A sweep of the five demo applications publishes ninety-four findings that are not
defects. That number is measured against declared plants and printed on the front
page rather than hidden — but ninety-four lines is not a report anyone reads, and
most of them repeat: the same overflow, seen from six witnesses across four routes.

Grouping them is a judgement about wording, not a measurement, which is the one
place a small model earns its place here. Gemma 3 reads only the summaries the
deterministic layers already produced and returns a partition of their ids:

```
31 findings grouped into 3 causes by gemma3:4b
  [19]  Horizontal overflow
  [ 7]  Text contrast below WCAG AA
  [ 4]  Tap target too small
```

It cannot invent a finding, change a severity, or reach a page. An id it returns
that was not in its input is discarded, and a finding is claimed by one group
only. Point `PARALLAX_GEMMA_URL` at any Ollama-compatible endpoint to enable it;
without one the run says the grouping was disabled rather than silently skipping
it, and an unreachable grouper is reported as unreachable rather than as a run
that found nothing to group.

## Reproducing the published figures

The figures on the front page come from a graded sweep of five bundled demo
applications that declare their own deliberate defects in code, plus a clean
control with nothing planted. The suite grades Parallax against those
declarations, so a false positive is measured rather than asserted.

It needs the demo fleet already listening; it does not start one:

```bash
python demo/serve.py &
python scripts/run_demo_suite.py --no-vision --host http://127.0.0.1:8080
```

The run rewrites `web/graded-summary.json` and the sweeps under `runs/`, prints a
per-application table, and exits non-zero whenever any application has a missed
defect or a false positive — which it currently does. At the commit this README
describes, the totals are **7 defects found, 7 missed, and 99 false positives**
across the five applications, with 2 of those false positives on the clean
control. That ratio is the honest state of the tool: the deterministic probe is
noisy, and the front page leads with the number rather than hiding it.

If the suite reports every surface dead and logins failing with HTTP 401, the
demo fleet is not running on the host passed to `--host`.

## Tests

The repository test suite is run from the repository root with:

```bash
python -m pip install pytest
python -m pytest -q
```

`pyproject.toml` supplies the import paths, so no `PYTHONPATH` is needed. The suite
runs 206 tests without a browser: witnesses, compositor and Gemini client are all
injected as fakes.
