# Parallax

Parallax is a browser-based regression investigator for an existing web application. It visits the same discovered surfaces from seven isolated contexts, records what each context can reach and what it renders, then turns broken expectations into findings and Playwright regression specs. The live console is available at [perallax.mlki.app](https://perallax.mlki.app).

## Quickstart

Parallax requires Python 3.12+, Chromium for Playwright, and its runtime packages. From the repository root, install the runtime packages and the browser:

```bash
python -m pip install playwright Pillow google-genai
python -m playwright install chromium
```

Run a deterministic sweep. `PYTHONPATH=src` runs the package directly from this checkout; `--no-vision` makes the run independent of a Gemini API key.

```bash
PYTHONPATH=src python -m parallax https://app.example.com --out runs/first --no-vision
```

To include authenticated contexts, supply Playwright storage-state files for the roles your application uses:

```bash
PYTHONPATH=src python -m parallax https://app.example.com --out runs/first --storage-state owner=.auth/owner.json --storage-state member=.auth/member.json --no-vision
```

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

Parallax observes rendered surfaces and discovered controls; it does not prove application policy, API authorization, or behavior outside the exercised browser flow. It uses the role storage states you supply, so a missing or incorrect role state limits what its privilege witnesses can establish. The Gemini visual lens is advisory: deterministic geometry and probe checks are the evidence-bearing checks, while aesthetic and visual-outlier judgement is model-assisted and may be absent when no key is configured.

## Tests

The repository test suite is run with:

```bash
PYTHONPATH=src python -m pytest tests/ -q
```
