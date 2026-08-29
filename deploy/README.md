# Deploy Parallax to Cloud Run

`cloudrun.sh` deploys the `parallax` service in **us-central1** in GCP project
`rasikh-fleet-2026`. This region is the intended home for the project and its
Gemini `gemini-3.5-flash` usage. It enables Cloud Run, Cloud Build, Artifact
Registry, and Secret Manager; creates an Artifact Registry Docker repository if
needed; submits the current checkout to Cloud Build; and deploys the result.
It is safe to rerun.

The image is based on the official Playwright Python image
`mcr.microsoft.com/playwright/python:v1.62.0-noble`. That is deliberately used
instead of installing Chromium manually: it includes Chromium and the operating
system libraries Playwright needs. The image then installs Parallax, Pillow for
mosaics, and `google-genai` for the Gemini lens.

## Prerequisites

Run this from the repository root with the Google Cloud CLI authenticated and a
principal able to enable APIs, use Cloud Build/Artifact Registry, deploy Cloud
Run, and access Secret Manager. Before deployment, create a Secret Manager
secret named `GEMINI_API_KEY` with the Gemini API key and grant the Cloud Run
runtime service account access to it. The deploy script only references that
secret; it never receives, writes, or embeds the key.

```bash
chmod +x deploy/cloudrun.sh
./deploy/cloudrun.sh
```

Optional environment overrides are `PROJECT_ID`, `REGION`, `SERVICE`, and
`REPOSITORY`. Their defaults are `rasikh-fleet-2026`, `us-central1`, `parallax`,
and `parallax`.

## Service behavior

The container listens on `0.0.0.0:$PORT`. `GET /` serves the static console;
`POST /runs` starts `python -m parallax` in a background process and returns a
run id immediately. Artifacts live under `/data/runs/<id>` and are exposed at
`/runs/<id>/feed.jsonl` and `/runs/<id>/mosaics/...`; feed responses use
`application/x-ndjson`. `GET /runs/<id>` returns the current state and artifact
counts, and `GET /healthz` is the Cloud Run health endpoint.

Cloud Run's writable filesystem is ephemeral and each instance has its own run
registry. For the live demo, keep the service at one instance and use a run
while it is active. Persisting runs or sharing them between instances requires a
separate storage backend, which this deploy intentionally does not add.

## Map `perallax.mlki.app`

The script prints, but never executes, this command:

```bash
gcloud beta run domain-mappings create --service "parallax" --domain "perallax.mlki.app" --region "us-central1" --project "rasikh-fleet-2026"
```

First verify ownership of `mlki.app` in Google Search Console. Then run that
command yourself. In the `mlki.app` DNS zone, add the CNAME record
`perallax CNAME ghs.googlehosted.com.`. Finally use the `domain-mappings
describe` command printed by the script and add any Google verification or
additional records it reports. The script does not create the mapping or alter
DNS.
