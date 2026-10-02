# CLAUDE.md

Bu dosya, Claude Code bu depoda çalışırken rehber olarak kullanılır.

## Proje nedir

Google Cloud Run üzerinde çalışan, LangGraph tabanlı asenkron bir ajan
mikroservisi. FastAPI üzerinden `/invoke` ile çağrılır, Vertex AI (Gemini)
modelini kullanır, araçlarını ayrı bir **MCP (Model Context Protocol)**
sunucusu (`mcp-tools-service`, kendi Cloud Run servisi) üzerinden çağırarak
BigQuery'den gerçek veri okur, kritik durumlarda insan onayı bekleyen bir
Human-in-the-Loop akışına sahiptir. Durum, container yeniden başlasa bile
kaybolmaması için Firestore'da saklanır.

Mimarinin tam açıklaması için `README.md` dosyasına bakın.

## İki servisli mimari

Repo iki bağımsız Cloud Run servisi içerir:
- **`main.py` (agent-service, repo kökü):** LangGraph grafı, FastAPI uç
  noktaları, Human-in-the-Loop/Firestore mantığı. Kasıtlı olarak **tek bir
  dosyada** tutulur (Cloud Run kaynak-tabanlı dağıtımda basitlik için).
  Dosyayı bölmeden önce kullanıcıyla bu tercihi teyit edin.
- **`mcp-tools-service/mcp_server.py`:** Araçları (şu an sadece
  `query_live_well_pressure`) standart MCP protokolü üzerinden sunan, ayrı
  bir Cloud Run servisi. Kendi `Dockerfile` ve `requirements.txt`'si vardır,
  `main.py`'den tamamen bağımsız deploy edilir.

`main.py` içindeki bölümler (yorum satırlarıyla işaretli):
1. MCP istemci sarmalayıcısı (`@tool` ile işaretli, `MultiServerMCPClient`
   üzerinden `mcp-tools-service`'i çağıran asenkron fonksiyon;
   `_fetch_mcp_id_token` her çağrıda taze bir ID token alır)
2. `AgentState` (TypedDict) — graf durumu
3. Model kurulumu (`ChatVertexAI`)
4. Graf düğümleri (`agent_node`, `tool_node`, `await_approval_node`)
5. Yönlendirme mantığı (`should_continue`, `route_after_tools`)
6. Graf derlemesi (`StateGraph`, `FirestoreSaver` checkpointer)
7. FastAPI uç noktaları

## Komutlar

```bash
# Sözdizimi kontrolü (hızlı, kimlik bilgisi gerektirmez) — her iki servis icin
python3 -c "import ast; ast.parse(open('main.py').read())"
python3 -c "import ast; ast.parse(open('mcp-tools-service/mcp_server.py').read())"

# Bağımlılıkları yerel olarak kurup içe aktarma/bağlantı testini yapma
pip install -r requirements.txt --break-system-packages
python3 -c "import main"   # GOOGLE_CLOUD_PROJECT ve gecerli kimlik bilgisi gerekir

# Once mcp-tools-service'i dagit (agent-service'in MCP_SERVER_URL'e ihtiyaci var)
./scripts/deploy_mcp.sh [MCP_SERVICE_NAME] [REGION] [AGENT_SERVICE_NAME]

# Sonra agent-service'i, MCP_SERVER_URL ile dagit
MCP_SERVER_URL=https://mcp-tools-service-xxx.run.app ./scripts/deploy.sh [SERVICE_NAME] [REGION]

# Operator erisimi (servis hesabi) kurulumu
./scripts/setup_invoker.sh [SERVICE_NAME] [REGION] [INVOKER_SA_NAME]
```

Bu depoda birim test çatısı yoktur; değişiklik sonrası doğrulama şu şekilde
yapılır:
1. `ast.parse` ile sözdizimi kontrolü.
2. Sahte (mock) LLM/araç ve `langgraph.checkpoint.memory.InMemorySaver` ile
   graf mantığının yerel olarak doğrulanması (bkz. aşağıdaki "Graf mantığını
   test etme" bölümü) — gerçek GCP kimlik bilgisi gerektirmez.
3. Gerçek deploy sonrası `curl` ile `/invoke`, `/approve/{thread_id}`,
   `/status/{thread_id}` uç noktalarının uçtan uca test edilmesi.

### Graf mantığını test etme (GCP kimlik bilgisi gerektirmez)

`FirestoreSaver` gerçek bir Firestore bağlantısı gerektirdiğinden, graf
yönlendirme mantığını (interrupt/resume, onay akışı) değiştirirken yerel
testte `langgraph.checkpoint.memory.InMemorySaver` ile sahte bir `agent_node`
ve `tool_node` kullanan ayrı bir test betiği yazın (bkz. proje geçmişinde
`_logic_test.py` deseni). `ChatVertexAI` ve `bigquery.Client` constructor'ları
import sırasında gerçek kimlik bilgisi arar; wiring'i (bağlantıları) test
etmek için `google.auth.default`'u `AnonymousCredentials` ile mock'layın.

## Önemli kısıtlar / dikkat edilmesi gerekenler

- **Servis herkese açık DEĞİL** (`--no-allow-unauthenticated`). Public yapmak
  güvenlik kararı gerektirir — kullanıcıya danışmadan değiştirmeyin.
- **Circuit breaker:** `step_count >= 5` olduğunda graf zorla sonlanır. Yeni
  düğümler eklerken bu sınırı atlamadığınızdan emin olun.
- **Kritik durum tetikleyicisi** (`route_after_tools` içindeki
  `"KRITIK SAPMA" in content` kontrolü) metin eşleşmesine dayanır — yeni bir
  araç eklerken onun çıktısının bu desenle (veya güncellenmiş deseninizle)
  tutarlı olduğundan emin olun.
- **Firestore koleksiyon adı** `CHECKPOINTS_COLLECTION` ortam değişkeni ile
  kontrol edilir; birden fazla ajan projesi aynı Firestore projesini
  paylaşıyorsa her biri için farklı bir koleksiyon adı kullanın.
- Cloud Shell'de büyük dosya değişikliklerini terminale doğrudan `cat <<EOF`
  ile yazdırmak karakter kaybına yol açabilir (gözlemlenmiş bir sorun) —
  büyük dosya güncellemelerinde Cloud Shell'in "Karşıya Yükle" (Upload)
  özelliğini, `base64 | wc -c` ile dogrulanmis parcali aktarimi, veya
  `gcloud run deploy --source .` ile doğrudan yerel/Git tabanlı kaynağı
  tercih edin.
- **`mcp-tools-service` ve `agent-service` ayrı deploy edilir** ve
  `agent-service`'in `MCP_SERVER_URL` ortam değişkeni, mcp-tools-service'in
  gerçek Cloud Run URL'ine işaret etmelidir. mcp-tools-service'i yeniden
  deploy ederseniz URL değişmez (aynı servis adını kullandığınız sürece),
  ama ilk kurulumda sırayı atlamayın (önce mcp, sonra agent).

## Bilinen tuzaklar (bu projede daha önce yaşandı)

- **`mcp` paketinin 2.x sürümü `FastMCP`'yi taşıdı/yeniden adlandırdı**
  (`mcp.server.fastmcp.FastMCP` artık `mcp.server.mcpserver.MCPServer`).
  Bu yüzden hem `requirements.txt` hem de `mcp-tools-service/requirements.txt`
  içinde `mcp>=1.9.0,<2.0.0` ile sabitlenmiştir. Üst sürüme geçerken
  `mcp_server.py` ve `main.py`'deki ilgili import'ları migration rehberine
  göre güncelleyin.
- **MCP SDK'nin DNS rebinding koruması, Cloud Run hostname'ini reddedebilir**
  (`421 Invalid Host header`). `mcp_server.py`, `TransportSecuritySettings`
  ile kendi hostname'ini `allowed_hosts`'a açıkça ekler
  (`_allowed_hosts.append("mcp-tools-service-...run.app")`). Servisi farklı
  bir adla/projeyle deploy ederseniz bu satırı güncellemeyi unutmayın —
  aksi halde `mcp-tools-service` sağlıklı görünür (`/health` 200 döner) ama
  `/mcp` uç noktası tüm istekleri 421 ile reddeder; hata `curl -i` veya
  ham `httpx` ile `/mcp`'ye POST atılarak teşhis edilebilir (hata mesajı
  `langchain_mcp_adapters` tarafında yutulup genel bir LLM yanıtına dönüşür).

## Yeni bir projeye uyarlama

`README.md` dosyasındaki "Bu şablonu yeni bir projeye uyarlamak" bölümüne
bakın. Özetle: aracı, kritik durum kontrolünü, `AgentState` alanlarını,
modeli ve Firestore koleksiyon adını değiştirin.
