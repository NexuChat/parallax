#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-rasikh-fleet-2026}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-parallax}"
REPOSITORY="${REPOSITORY:-parallax}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${SERVICE}:latest"
DOMAIN="perallax.mlki.app"

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  --project="$PROJECT_ID"

if ! gcloud artifacts repositories describe "$REPOSITORY" \
  --location="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$REPOSITORY" \
    --repository-format=docker --location="$REGION" --project="$PROJECT_ID"
fi

gcloud builds submit --tag "$IMAGE" --project="$PROJECT_ID" .

# GEMINI_API_KEY must already exist as a Secret Manager secret; its value is never
# placed in this script, image, or source tree.
# Seven concurrent Chromium contexts plus JPEG mosaic composition do not fit the
# 512Mi default. The run registry lives in one instance's memory, so a second
# instance would answer GET /runs/<id> with 404; pin the service to one. A sweep
# outlives the 300s request default, and it continues on a background thread, so
# the CPU must stay allocated between requests.
gcloud run deploy "$SERVICE" \
  --image="$IMAGE" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --platform=managed \
  --allow-unauthenticated \
  --memory=4Gi \
  --cpu=4 \
  --timeout=900 \
  --max-instances=1 \
  --no-cpu-throttling \
  --set-secrets="GEMINI_API_KEY=GEMINI_API_KEY:latest"

cat <<EOF

Service deployed. Do not run this automatically; map the domain after verifying
ownership of mlki.app with Google Search Console:

gcloud beta run domain-mappings create --service "$SERVICE" --domain "$DOMAIN" --region "$REGION" --project "$PROJECT_ID"

For the mlki.app DNS zone, add this record after creating the mapping:
  CNAME  perallax  ghs.googlehosted.com.

Then inspect any verification or additional records Google returns with:
gcloud beta run domain-mappings describe --domain "$DOMAIN" --region "$REGION" --project "$PROJECT_ID"
EOF
