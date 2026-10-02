#!/usr/bin/env bash
# mcp-tools-service'i Google Cloud Run'a dagitir ve agent-service'in kendi
# calisma zamani servis hesabina (varsayilan: Compute Engine default SA)
# bu servisi cagirma (roles/run.invoker) yetkisi verir.
#
# Onem: Bu adim, ana deploy.sh (agent-service) ile scripts/setup_invoker.sh
# (operator -> agent-service erisimi) adimlarindan BAGIMSIZDIR. mcp-tools-service,
# agent-service'in kendisi tarafindan (operator tarafindan degil) MCP protokolu
# uzerinden cagrilir; bu yuzden invoker olarak agent-service'in runtime SA'si
# yetkilendirilir, agent-invoker degil.
#
# Kullanim: ./scripts/deploy_mcp.sh [MCP_SERVICE_NAME] [REGION] [AGENT_SERVICE_NAME]
set -euo pipefail

MCP_SERVICE_NAME="${1:-mcp-tools-service}"
REGION="${2:-us-central1}"
AGENT_SERVICE_NAME="${3:-agent-service}"
PROJECT_ID="$(gcloud config get-value project)"
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
AGENT_RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "Proje: ${PROJECT_ID} | MCP servisi: ${MCP_SERVICE_NAME} | Bolge: ${REGION}"

pushd mcp-tools-service >/dev/null
gcloud run deploy "${MCP_SERVICE_NAME}" \
  --source . \
  --platform managed \
  --region "${REGION}" \
  --no-allow-unauthenticated \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
  --cpu 1 \
  --memory 512Mi \
  --timeout 120s
popd >/dev/null

MCP_URL="$(gcloud run services describe "${MCP_SERVICE_NAME}" --region "${REGION}" --format 'value(status.url)')"

echo ""
echo "mcp-tools-service dagitildi: ${MCP_URL}"
echo "Not: Bu servisin kodu (mcp_server.py) kendi hostname'ini mcp sunucusunun"
echo "DNS rebinding korumasi icin allowed_hosts listesine zaten ekler; farkli"
echo "bir proje/servis adiyla dagitiyorsaniz mcp-tools-service/mcp_server.py"
echo "icindeki _allowed_hosts.append(...) satirini guncelleyin."

echo ""
echo "${AGENT_SERVICE_NAME}'in calisma zamani servis hesabina (${AGENT_RUNTIME_SA})"
echo "mcp-tools-service'i cagirma yetkisi veriliyor..."

gcloud run services add-iam-policy-binding "${MCP_SERVICE_NAME}" \
  --region="${REGION}" \
  --member="serviceAccount:${AGENT_RUNTIME_SA}" \
  --role="roles/run.invoker"

echo ""
echo "Hazir. agent-service'i su MCP_SERVER_URL ile (yeniden) dagitmayi unutmayin:"
echo "  gcloud run deploy ${AGENT_SERVICE_NAME} --source . --region ${REGION} \\"
echo "    --no-allow-unauthenticated \\"
echo "    --set-env-vars GOOGLE_CLOUD_PROJECT=${PROJECT_ID},MCP_SERVER_URL=${MCP_URL}"
echo "veya dogrudan: ./scripts/deploy.sh ${AGENT_SERVICE_NAME} ${REGION}"
echo "(deploy.sh'yi MCP_SERVER_URL=${MCP_URL} ortam degiskenini set ederek"
echo "cagirirsaniz bu deger otomatik olarak --set-env-vars'a eklenir.)"
