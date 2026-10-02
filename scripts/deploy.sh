#!/usr/bin/env bash
# Bu projeyi Google Cloud Run'a dagitir.
# On kosullar: gcloud yuklu ve `gcloud auth login` / `gcloud config set project`
# yapilmis olmali; asagidaki API'lar etkin olmali:
#   aiplatform.googleapis.com run.googleapis.com artifactregistry.googleapis.com
#   cloudbuild.googleapis.com bigquery.googleapis.com firestore.googleapis.com
#
# mcp-tools-service'in URL'ini (bkz. scripts/deploy_mcp.sh) ortam degiskeni
# olarak MCP_SERVER_URL=... set ederek cagirirsaniz, ajanin BigQuery aracini
# MCP protokolu uzerinden o servise yonlendirmesi icin otomatik eklenir.
# Bos birakilirsa, main.py'deki MCP istemcisi devre disi kalir (acik hata doner).
#
# Kullanim: ./scripts/deploy.sh [SERVICE_NAME] [REGION]
#   MCP_SERVER_URL=https://mcp-tools-service-xxx.run.app ./scripts/deploy.sh
set -euo pipefail

SERVICE_NAME="${1:-agent-service}"
REGION="${2:-us-central1}"
PROJECT_ID="$(gcloud config get-value project)"
MCP_SERVER_URL="${MCP_SERVER_URL:-}"

echo "Proje: ${PROJECT_ID} | Servis: ${SERVICE_NAME} | Bolge: ${REGION}"
if [ -n "${MCP_SERVER_URL}" ]; then
  echo "MCP_SERVER_URL: ${MCP_SERVER_URL}"
fi

ENV_VARS="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_REGION=${REGION},CHECKPOINTS_COLLECTION=agent_checkpoints"
if [ -n "${MCP_SERVER_URL}" ]; then
  ENV_VARS="${ENV_VARS},MCP_SERVER_URL=${MCP_SERVER_URL}"
fi

gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --platform managed \
  --region "${REGION}" \
  --no-allow-unauthenticated \
  --set-env-vars "${ENV_VARS}" \
  --cpu 1 \
  --memory 1Gi \
  --timeout 300s

echo ""
echo "Dagitim tamamlandi. Servis herkese acik DEGIL (--no-allow-unauthenticated)."
echo "Bir cagirici servis hesabi olusturmak icin scripts/setup_invoker.sh dosyasina bakin."
if [ -z "${MCP_SERVER_URL}" ]; then
  echo ""
  echo "Not: MCP_SERVER_URL set edilmedi. BigQuery aracini kullanabilmek icin once"
  echo "  ./scripts/deploy_mcp.sh"
  echo "ile mcp-tools-service'i dagitin, sonra bu komutu MCP_SERVER_URL ile tekrar calistirin."
fi
