# ProAgent Template — Asenkron Ajan Mikroservisi

Google Cloud üzerinde **LangGraph + FastAPI + Vertex AI (Gemini)** ile kurulmuş,
üretim kalitesinde bir ajan mikroservisi şablonu. Google'ın Austin ve Houston
etkinliklerinde anlatılan mimariden yola çıkılarak geliştirildi; sıfırdan yeni
bir ajan projesine başlarken (müşteri destek botu, finans analiz botu, DevOps
triage botu vb.) bu repo bir başlangıç noktası olarak kullanılabilir.

## Mimari

```
İstek → FastAPI (/invoke) → LangGraph State Machine
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
                 agent          tools        await_approval
            (Gemini karar)  (BigQuery SQL)  (insan onayı — koşullu)
                    │              │              │
                    └──────────────┴──────────────┘
                                   │
                        Firestore Checkpointer
                 (kalıcı durum — container yeniden başlasa
                  veya başka bir instance'a düşse bile kaybolmaz)
```

### Temel özellikler

- **Durum makinesi (LangGraph):** Serbest promptlar yerine deterministik bir
  graf; adım sayacı ile sonsuz döngü koruması (circuit breaker, varsayılan 5 adım).
- **Asenkron araçlar:** Dış sistemlere (BigQuery örneğinde) non-blocking sorgu.
- **Knowledge Core (BigQuery):** Sahte/simüle veri yerine gerçek bir tablodan
  canlı SQL sorgusu. `query_live_well_pressure` aracı örnek implementasyondur.
- **Human-in-the-Loop:** Araç sonucu kritik bir durum bildirdiğinde
  (`KRITIK SAPMA`), graf `await_approval` düğümünden **önce** otomatik olarak
  duraklar. Ajan operatör onayı almadan ileri bir eylem almaz.
- **Kalıcı checkpointer (Firestore):** Onay bekleyen iş parçacıkları
  (`thread_id`) Firestore'da saklanır — Cloud Run container'ı yeniden başlasa,
  ölçeklense veya farklı bir instance'a düşse bile bekleyen onay kaybolmaz.
- **Güvenli erişim (IAM):** Servis herkese açık değil (`--no-allow-unauthenticated`).
  Yalnızca ayrılmış bir servis hesabı (`agent-invoker`) çağırabilir.

## Dizin yapısı

```
.
├── main.py                   # Graf, FastAPI uygulaması, tüm uç noktalar
├── Dockerfile
├── requirements.txt
├── scripts/
│   ├── deploy.sh              # Cloud Run'a tek komutla dağıtım
│   ├── setup_invoker.sh       # Güvenli erişim (servis hesabı + IAM) kurulumu
│   └── setup_bigquery.sql     # Örnek BigQuery şeması ve veri
├── CLAUDE.md                  # Claude Code için repo rehberi
└── AGENTS.md                  # Codex / diğer ajanlar için repo rehberi
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

# 4. Cloud Run'a dağıtın
chmod +x scripts/*.sh
./scripts/deploy.sh

# 5. Güvenli erişimi kurun (servis hesabı ile çağırma)
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

1. **Aracı değiştirin:** `main.py` içindeki `query_live_well_pressure`
   fonksiyonunu kendi iş mantığınızla (başka bir BigQuery tablosu, bir REST
   API çağrısı, bir CRM sorgusu vb.) değiştirin.
2. **Kritik durum tetikleyicisini güncelleyin:** `route_after_tools`
   fonksiyonundaki `"KRITIK SAPMA" in content` kontrolünü kendi onay
   gerektiren koşulunuzla değiştirin.
3. **Durumu genişletin:** `AgentState` TypedDict'ine projenize özel alanlar
   ekleyin (ör. `customer_id`, `ticket_id`).
4. **Modeli/promptu ayarlayın:** `llm = ChatVertexAI(...)` satırını ve sistem
   mesajlarını ihtiyacınıza göre güncelleyin.
5. **Firestore koleksiyon adını değiştirin:** `CHECKPOINTS_COLLECTION` ortam
   değişkeni ile her proje için ayrı bir koleksiyon kullanın.

Bu repo'yu GitHub'da **Template repository** olarak işaretlerseniz
(`Settings → Template repository`), her yeni proje için "Use this template"
butonuyla temiz bir kopya oluşturabilirsiniz.

## Lisans

MIT — `LICENSE` dosyasına bakın.
