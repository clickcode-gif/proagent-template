# ProAgent Template — Asenkron Ajan Mikroservisi

Google Cloud üzerinde **LangGraph + FastAPI + Vertex AI (Gemini)** ile kurulmuş,
üretim kalitesinde bir ajan mikroservisi şablonu. Google'ın Austin ve Houston
etkinliklerinde anlatılan mimariden yola çıkılarak geliştirildi; sıfırdan yeni
bir ajan projesine başlarken (müşteri destek botu, finans analiz botu, DevOps
triage botu vb.) bu repo bir başlangıç noktası olarak kullanılabilir.

## Mimari

İki ayrı Cloud Run servisinden oluşur: ajan mantığını yürüten **agent-service**
ve araçları standart **MCP (Model Context Protocol)** üzerinden sunan
**mcp-tools-service**. Araçları ajanın kod tabanına doğrudan Python fonksiyonu
olarak gömmek yerine bu şekilde ayırmak, aynı araç sunucusunun birden fazla
ajan projesi tarafından (veya Claude Desktop gibi başka MCP istemcileri
tarafından) yeniden kullanılabilmesini sağlar.

```
İstek → FastAPI (/invoke) → LangGraph State Machine  [agent-service]
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
                 agent          tools        await_approval
            (Gemini karar)  (MCP istemcisi) (insan onayı — koşullu)
                    │              │              │
                    │              ▼              │
                    │   MCP protokolu (HTTPS + IAM ID token)
                    │              │
                    │              ▼
                    │     mcp-tools-service (ayrı Cloud Run servisi)
                    │              │
                    │              ▼
                    │         BigQuery SQL
                    │
                    └──────────────┴──────────────┘
                                   │
                        Firestore Checkpointer
                 (kalıcı durum — container yeniden başlasa
                  veya başka bir instance'a düşse bile kaybolmaz)
```

### Temel özellikler

- **Durum makinesi (LangGraph):** Serbest promptlar yerine deterministik bir
  graf; adım sayacı ile sonsuz döngü koruması (circuit breaker, varsayılan 5 adım).
- **Araçlar MCP arkasında:** `agent-service`, BigQuery'yi doğrudan sorgulamaz;
  istek standart MCP protokolü (streamable HTTP) üzerinden ayrı bir
  `mcp-tools-service`'e gider. Her çağrıda, agent-service'in kendi Cloud Run
  çalışma zamanı kimliğiyle taze bir ID token alınır (token'lar statik olarak
  saklanmaz).
- **Knowledge Core (BigQuery):** Sahte/simüle veri yerine gerçek bir tablodan
  canlı SQL sorgusu. `query_live_well_pressure` aracı örnek implementasyondur
  (bkz. `mcp-tools-service/mcp_server.py`).
- **Human-in-the-Loop:** Araç sonucu kritik bir durum bildirdiğinde
  (`KRITIK SAPMA`), graf `await_approval` düğümünden **önce** otomatik olarak
  duraklar. Ajan operatör onayı almadan ileri bir eylem almaz.
- **Kalıcı checkpointer (Firestore):** Onay bekleyen iş parçacıkları
  (`thread_id`) Firestore'da saklanır — Cloud Run container'ı yeniden başlasa,
  ölçeklense veya farklı bir instance'a düşse bile bekleyen onay kaybolmaz.
- **Güvenli erişim (IAM, iki katman):**
  - Operatör → `agent-service`: Servis herkese açık değil
    (`--no-allow-unauthenticated`); yalnızca ayrılmış bir servis hesabı
    (`agent-invoker`) çağırabilir.
  - `agent-service` → `mcp-tools-service`: Bu servis de herkese açık değildir;
    yalnızca agent-service'in kendi çalışma zamanı servis hesabı (Compute
    Engine default SA) `roles/run.invoker` ile yetkilendirilir — operatörün
    `agent-invoker` hesabının mcp-tools-service'e doğrudan erişimi yoktur.

## Dizin yapısı

```
.
├── main.py                       # Graf, FastAPI uygulaması, tüm uç noktalar (agent-service)
├── Dockerfile
├── requirements.txt
├── mcp-tools-service/             # Ayrı Cloud Run servisi: araçları MCP üzerinden sunar
│   ├── mcp_server.py               # FastMCP sunucusu + BigQuery aracı
│   ├── Dockerfile
│   └── requirements.txt
├── scripts/
│   ├── deploy.sh                  # agent-service'i Cloud Run'a dağıtır
│   ├── deploy_mcp.sh              # mcp-tools-service'i dağıtır + agent-service'e IAM yetkisi verir
│   ├── setup_invoker.sh           # Operatör erişimi (agent-invoker servis hesabı + IAM) kurulumu
│   └── setup_bigquery.sql         # Örnek BigQuery şeması ve veri
├── CLAUDE.md                      # Claude Code için repo rehberi
└── AGENTS.md                      # Codex / diğer ajanlar için repo rehberi
```

## Hızlı başlangıç

```bash
# 1. Google Cloud projesini hazırlayın
export PROJECT_ID=$(gcloud config get-value project)
gcloud services enable \
  aiplatform.googleapis.com run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com bigquery.googleapis.com firestore.googleapis.com

# 2. Firestore veritabanını oluşturun (yoksa)
gcloud firestore databases create --database='(default)' --location=us-central1 \
  --type=firestore-native

# 3. Örnek BigQuery tablosunu kurun
bq mk --dataset ${PROJECT_ID}:telemetry_data
sed "s/PROJECT_PLACEHOLDER/${PROJECT_ID}/g" scripts/setup_bigquery.sql | \
  bq query --use_legacy_sql=false

# 4. mcp-tools-service'i dağıtın (önce bu — agent-service'in ihtiyacı var)
chmod +x scripts/*.sh
./scripts/deploy_mcp.sh
# Çıktıdaki Service URL'i not edin, ör: https://mcp-tools-service-xxx.run.app

# 5. agent-service'i, MCP_SERVER_URL ile dağıtın
MCP_SERVER_URL=https://mcp-tools-service-xxx.run.app ./scripts/deploy.sh

# 6. Operatör erişimini kurun (agent-invoker servis hesabı ile çağırma)
./scripts/setup_invoker.sh
```

## API uç noktaları

| Yöntem | Yol                      | Açıklama                                                         |
|--------|--------------------------|--------------------------------------------------------------------|
| GET    | `/health`                | Sağlık kontrolü                                                   |
| POST   | `/invoke`                | `{"prompt": "...", "thread_id": "opsiyonel"}` — ajanı çalıştırır  |
| POST   | `/approve/{thread_id}`   | Onay bekleyen iş parçacığını devam ettirir                       |
| POST   | `/reject/{thread_id}`    | Onayı reddeder; ajan ileri bir eylem almaz, iş parçacığı askıda kalır |
| GET    | `/status/{thread_id}`    | Bir iş parçacığının durumunu sorgular (`completed`/`pending_approval`) |

`/invoke` yanıtı `status: "pending_approval"` dönerse, `pending_detail` alanında
operatöre gösterilecek kritik durum metni ve bir `thread_id` gelir. Operatör
`/approve/{thread_id}` çağırana kadar ajan hiçbir ileri eylem almaz.

## Bu şablonu yeni bir projeye uyarlamak

1. **Aracı değiştirin:** `mcp-tools-service/mcp_server.py` içindeki
   `query_live_well_pressure` fonksiyonunu (ve `@mcp.tool()` ile işaretli
   diğer araçları) kendi iş mantığınızla (başka bir BigQuery tablosu, bir
   REST API çağrısı, bir CRM sorgusu vb.) değiştirin. Yeni bir araç
   eklediğinizde `main.py` tarafında yeni bir MCP istemci sarmalayıcısı
   (`@tool` ile işaretli, `session.call_tool(...)` çağıran bir fonksiyon)
   yazıp `tools` listesine ekleyin.
2. **Kritik durum tetikleyicisini güncelleyin:** `main.py` içindeki
   `route_after_tools` fonksiyonundaki `"KRITIK SAPMA" in content` kontrolünü
   kendi onay gerektiren koşulunuzla değiştirin.
3. **Durumu genişletin:** `AgentState` TypedDict'ine projenize özel alanlar
   ekleyin (ör. `customer_id`, `ticket_id`).
4. **Modeli/promptu ayarlayın:** `llm = ChatVertexAI(...)` satırını ve sistem
   mesajlarını ihtiyacınıza göre güncelleyin.
5. **Firestore koleksiyon adını değiştirin:** `CHECKPOINTS_COLLECTION` ortam
   değişkeni ile her proje için ayrı bir koleksiyon kullanın.
6. **mcp-tools-service'i farklı bir isim/projeyle dağıtıyorsanız:**
   `mcp-tools-service/mcp_server.py` içindeki `_allowed_hosts.append(...)`
   satırını yeni Cloud Run hostname'inizle güncelleyin — aksi halde MCP SDK'nin
   DNS rebinding koruması isteği `421 Invalid Host header` ile reddeder (bkz.
   `CLAUDE.md` içindeki "Bilinen tuzaklar" bölümü).

Bu repo'yu GitHub'da **Template repository** olarak işaretlerseniz
(`Settings → Template repository`), her yeni proje için "Use this template"
butonuyla temiz bir kopya oluşturabilirsiniz.

## Lisans

MIT — `LICENSE` dosyasına bakın.
