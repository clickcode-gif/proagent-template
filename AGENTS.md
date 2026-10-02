# AGENTS.md

Bu dosya, bu depo üzerinde çalışan AI kodlama ajanları (Codex ve benzerleri)
için rehberdir.

## Proje özeti

LangGraph + FastAPI + Google Vertex AI (Gemini) ile yazılmış, Google Cloud
Run'a dağıtılan bir ajan mikroservisi. BigQuery'den gerçek veri okur, kritik
durumlarda bir insan onayı bekler (Human-in-the-Loop) ve durumunu kalıcı
olarak Firestore'da saklar. Tüm uygulama mantığı `main.py` dosyasındadır.
Mimari detayları için `README.md`, Claude Code'a özel notlar için `CLAUDE.md`
dosyasına bakın (bu dosyayla büyük ölçüde örtüşür).

## Kurulum

```bash
pip install -r requirements.txt
```

Yerel olarak `main.py`'yi tam anlamıyla çalıştırmak (içe aktarmak) için
geçerli bir Google Cloud kimlik bilgisi ve `GOOGLE_CLOUD_PROJECT` ortam
değişkeni gerekir, çünkü modül yüklenirken `bigquery.Client()` ve
`ChatVertexAI()` örnekleri oluşturulur.

## Değişiklik yapmadan önce

- `main.py` tek dosyalık bir uygulamadır; bölmeyi önermeden önce kullanıcıya
  danışın (Cloud Run kaynak-tabanlı dağıtımı basitleştirmek için kasıtlıdır).
- Servis varsayılan olarak **herkese açık değildir**
  (`--no-allow-unauthenticated`). Bunu değiştirmek güvenlik etkisi olan bir
  karardır.

## Doğrulama / test komutları

```bash
# 1. Sözdizimi kontrolü (hızlı, kimlik bilgisi gerektirmez)
python3 -c "import ast; ast.parse(open('main.py').read())"

# 2. Graf mantığını InMemorySaver ile test et (gerçek GCP gerektirmez):
#    - langgraph.checkpoint.memory.InMemorySaver kullanan, agent_node ve
#      tool_node'u sahte (mock) fonksiyonlarla değiştiren ayrı bir betik
#      yazın; interrupt_before="await_approval" davranışını ve
#      approve/reject akışını assert'lerle doğrulayın.

# 3. Dağıtım sonrası uçtan uca test (gerçek GCP kimlik bilgisi gerekir):
./scripts/deploy.sh
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

## Yeni bir projeye uyarlama

`README.md`'deki "Bu şablonu yeni bir projeye uyarlamak" bölümüne bakın.
