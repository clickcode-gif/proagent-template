#!/usr/bin/env bash
# Servisi herkese acik yapmadan, ayri bir servis hesabina cagirma yetkisi verir.
# Kullanim: ./scripts/setup_invoker.sh [SERVICE_NAME] [REGION] [INVOKER_SA_NAME]
set -euo pipefail

SERVICE_NAME="${1:-agent-service}"
REGION="${2:-us-central1}"
INVOKER_NAME="${3:-agent-invoker}"
PROJECT_ID="$(gcloud config get-value project)"
INVOKER_EMAIL="${INVOKER_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts create "${INVOKER_NAME}" \
  --display-name="Agent Invoker Service Account" 2>/dev/null || \
  echo "Servis hesabi zaten var, devam ediliyor."

gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
  --region="${REGION}" \
  --member="serviceAccount:${INVOKER_EMAIL}" \
  --role="roles/run.invoker"

echo ""
echo "Hazir. Test etmek icin (kendi hesabiniza serviceAccountTokenCreator rolu gerekir):"
echo "  gcloud iam service-accounts add-iam-policy-binding ${INVOKER_EMAIL} \\"
echo "    --member=\"user:\$(gcloud config get-value account)\" \\"
echo "    --role=\"roles/iam.serviceAccountTokenCreator\""
echo ""
echo "  SERVICE_URL=\$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format 'value(status.url)')"
echo "  TOKEN=\$(gcloud auth print-identity-token --impersonate-service-account=${INVOKER_EMAIL} --audiences=\$SERVICE_URL)"
echo "  curl -X POST \"\$SERVICE_URL/invoke\" -H \"Authorization: Bearer \$TOKEN\" -H \"Content-Type: application/json\" -d '{\"prompt\": \"test\"}'"
