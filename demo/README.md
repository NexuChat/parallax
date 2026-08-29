# Parallax demo fleet

The fleet is five small, independent sites mounted by one server. Each site is
a pure `Site.handle(Request) -> Response` implementation, so the server is
only a transport adapter and the suite can compare a real Parallax sweep with
the defects deliberately declared by the site.

| Site | Purpose | What it plants |
| --- | --- | --- |
| `workspace` | Team workspace and project collaboration | Its `planted` declarations when the site module is available. |
| `shop` | Customer storefront and checkout | Its `planted` declarations when the site module is available. |
| `docs` | Documentation and knowledge base | Its `planted` declarations when the site module is available. |
| `admin` | Administrative operations | Its `planted` declarations when the site module is available. |
| `control` | Known-clean comparison application | Nothing: any finding is a false positive. |

The table intentionally follows the runtime contract while the sites are being
developed independently. Each available site's exact declarations live in its
`planted: list[Planted]`; the graded run reads those declarations directly, so
the report is always the source of truth.

## Seeded accounts

The fleet uses the three roles in Parallax's witness matrix: `owner`, `member`,
and anonymous (`anon`). Individual sites provide their own deterministic
seeded session behavior; no external identity provider or network account is
needed. Locale (`lang=ar`) and theme (`theme=dark`) can also be selected by
query string or cookie for direct manual checks.

## Run it

Start the server first; the suite deliberately does not start it:

```bash
python demo/serve.py
```

It binds `0.0.0.0:${PORT:-8080}`. Visit `http://127.0.0.1:8080/` for the
fleet front door, or `http://127.0.0.1:8080/healthz` for a health check.

In a second terminal, run the graded sweep:

```bash
PYTHONPATH=src python scripts/run_demo_suite.py --no-vision
```

Useful options are `--host http://127.0.0.1:8080`, `--only workspace`, and
`--max-surfaces 20`. Results for each site are written below `runs/<site>/`.
The compact report lists plants found, plants missed, and false positives. A
non-zero exit status means either a plant was missed or an unplanted finding was
raised; for `control`, every finding is necessarily a false positive.
