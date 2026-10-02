#!/usr/bin/env bash
# Bu projeyi Google Cloud Run'a dagitir.
# On kosullar: gcloud yuklu ve `gcloud auth login` / `gcloud config set project`
# yapilmis olmali; asagidaki API'lar etkin olmali:
#   aiplatform.googleapis.com run.googleapis.com artifactregistry.googleapis.com
#   cloudbuild.googleapis.com bigquery.googleapis.com firestore.googleapis.com
#
# Kullanim: ./scripts/deploy.sh [SERVICE_NAME] [REGION]
set -euo pipefail

SERVICE_NAME="${1:-agent-service}"
REGION="${2:-us-central1}"
PROJECT_ID="$(gcloud config get-value project)"

echo "Proje: ${PROJECT_ID} | Servis: ${SERVICE_NAME} | Bolge: ${REGION}"

gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --platform managed \
  --region "${REGION}" \
  --no-allow-unauthenticated \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_REGION=${REGION},CHECKPOINTS_COLLECTION=agent_checkpoints" \
  --cpu 1 \
  --memory 512Mi \
  --timeout 120s

echo ""
echo "Dagitim tamamlandi. Servis herkese acik DEGIL (--no-allow-unauthenticated)."
echo "Bir cagirici servis hesabi olusturmak icin scripts/setup_invoker.sh dosyasina bakin."
