# AGENTS.md

Bu dosya, bu depo üzerinde çalışan AI kodlama ajanları (Codex ve benzerleri)
için rehberdir.

## Proje özeti

LangGraph + FastAPI + Google Vertex AI (Gemini) ile yazılmış, Google Cloud
Run'a dağıtılan bir ajan mikroservisi (`agent-service`). Araçlarını
(ör. BigQuery sorgusu) kendi içine gömmek yerine, ayrı bir Cloud Run servisi
olan `mcp-tools-service`'e standart **MCP (Model Context Protocol)**
üzerinden çağırır. Kritik durumlarda bir insan onayı bekler
(Human-in-the-Loop) ve durumunu kalıcı olarak Firestore'da saklar.
agent-service'in uygulama mantığı `main.py` dosyasındadır, MCP araç sunucusu
`mcp-tools-service/mcp_server.py` dosyasındadır — ikisi ayrı ayrı deploy
edilen bağımsız servislerdir. Mimari detayları için `README.md`, Claude
Code'a özel notlar için `CLAUDE.md` dosyasına bakın (bu dosyayla büyük
ölçüde örtüşür).

## Kurulum

```bash
pip install -r requirements.txt                          # agent-service
pip install -r mcp-tools-service/requirements.txt         # mcp-tools-service
```

Yerel olarak `main.py`'yi tam anlamıyla çalıştırmak (içe aktarmak) için
geçerli bir Google Cloud kimlik bilgisi ve `GOOGLE_CLOUD_PROJECT` ortam
değişkeni gerekir, çünkü modül yüklenirken `ChatVertexAI()` örneği
oluşturulur. `mcp_server.py` için aynı şekilde `bigquery.Client()` gerçek
kimlik bilgisi arar.

## Değişiklik yapmadan önce

- `main.py` tek dosyalık bir uygulamadır; bölmeyi önermeden önce kullanıcıya
  danışın (Cloud Run kaynak-tabanlı dağıtımı basitleştirmek için kasıtlıdır).
- Servisler varsayılan olarak **herkese açık değildir**
  (`--no-allow-unauthenticated`, hem agent-service hem mcp-tools-service için).
  Bunu değiştirmek güvenlik etkisi olan bir karardır.
- `mcp-tools-service` ve `agent-service` ayrı deploy edilir; sırayı atlamayın
  (önce `./scripts/deploy_mcp.sh`, sonra `MCP_SERVER_URL=... ./scripts/deploy.sh`).

## Doğrulama / test komutları

```bash
# 1. Sözdizimi kontrolü (hızlı, kimlik bilgisi gerektirmez)
python3 -c "import ast; ast.parse(open('main.py').read())"
python3 -c "import ast; ast.parse(open('mcp-tools-service/mcp_server.py').read())"

# 2. Graf mantığını InMemorySaver ile test et (gerçek GCP gerektirmez):
#    - langgraph.checkpoint.memory.InMemorySaver kullanan, agent_node ve
#      tool_node'u sahte (mock) fonksiyonlarla değiştiren ayrı bir betik
#      yazın; interrupt_before="await_approval" davranışını ve
#      approve/reject akışını assert'lerle doğrulayın.

# 3. Dağıtım sonrası uçtan uca test (gerçek GCP kimlik bilgisi gerekir):
./scripts/deploy_mcp.sh
MCP_SERVER_URL=https://mcp-tools-service-xxx.run.app ./scripts/deploy.sh
./scripts/setup_invoker.sh
# ardından README.md'deki curl örnekleriyle /invoke, /approve, /status test edin
```

Bu depoda otomatik birim test çatısı (pytest vb.) yoktur; yukarıdaki üç
adım mevcut doğrulama akışıdır. Yeni bir test çatısı eklemek isterseniz
`pyproject.toml` veya `pytest.ini` ekleyip bu dosyayı güncelleyin.

## Kod stili

- Python 3.11, type hints (`TypedDict`, `Literal`, `Annotated`) kullanılıyor.
- Yorumlar ve docstring'ler Türkçe, ASCII-only (Türkçe karakter kullanılmıyor:
  `ı`→`i`, `ş`→`s`, `ğ`→`g` gibi) — Cloud Shell terminaline doğrudan yazdırma
  sırasında kodlama sorunlarını önlemek için. Yeni kod eklerken bu kurala
  uyun.
- Fonksiyon/değişken isimleri İngilizce, kullanıcıya dönük metinler
  (log, hata mesajı, API yanıtı) Türkçe.

## Dikkat edilecek noktalar

- `route_after_tools` fonksiyonundaki kritik durum tespiti basit bir metin
  araması (`"KRITIK SAPMA" in content`). Yeni bir araç eklerken çıktısının bu
  kontrolle (veya onu güncellediyseniz yeni haliyle) tutarlı olduğundan emin
  olun.
- `step_count >= 5` devre kesicisini (circuit breaker) kaldırmayın veya
  gevşetmeyin; sonsuz döngüye karşı tek koruma budur.
- `CHECKPOINTS_COLLECTION` ortam değişkenini değiştirmeden birden fazla ajan
  projesini aynı Firestore veritabanında çalıştırmayın (checkpoint'ler
  çakışabilir).
- Büyük dosya değişikliklerini bir uzak terminale (ör. Cloud Shell) doğrudan
  `cat <<EOF` ile yazdırmak yerine dosya yükleme/Git tabanlı yöntemleri
  tercih edin; büyük heredoc'larda karakter kaybı gözlemlenmiştir.
- `mcp` paketi `requirements.txt` ve `mcp-tools-service/requirements.txt`
  içinde `mcp>=1.9.0,<2.0.0` ile kasıtlı olarak sabitlenmiştir (2.x sürümünde
  `FastMCP` taşındı/yeniden adlandırıldı). Üst sürüme geçerken migration
  rehberine bakın ve ilgili import'ları güncelleyin.
- `mcp-tools-service/mcp_server.py` kendi hostname'ini `TransportSecuritySettings`
  ile `allowed_hosts`'a açıkça ekler (MCP SDK'nin DNS rebinding koruması
  aksi halde tüm istekleri `421 Invalid Host header` ile reddeder). Servisi
  farklı bir isim/projeyle deploy ederken bu satırı güncelleyin.

## Yeni bir projeye uyarlama

`README.md`'deki "Bu şablonu yeni bir projeye uyarlamak" bölümüne bakın.
