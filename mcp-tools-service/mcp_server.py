import os
import asyncio
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from google.cloud import bigquery

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", os.getenv("PROJECT_ID", "default-project"))

bq_client = bigquery.Client(project=PROJECT_ID)

# mcp SDK'si varsayilan olarak DNS rebinding korumasi uyguluyor ve Host header'ini
# bos bir allowed_hosts listesine gore dogruluyor; bu da Cloud Run'in kendi
# hostname'inden gelen her istegi "Invalid Host header" (421) ile reddediyordu.
# Servis zaten Cloud Run IAM ile (--no-allow-unauthenticated) korundugu icin,
# DNS rebinding korumasini kapatmak yerine servisin kendi hostname'ini (ve
# yerel test icin localhost'u) acikca allowed_hosts/allowed_origins listesine ekliyoruz.
_SERVICE_HOSTNAME = os.getenv("K_SERVICE_HOSTNAME", "")  # Cloud Run bu degiskeni set etmez, fallback asagida
_RUN_URL = os.getenv("MCP_SELF_URL", "")  # ops. acikca set edilebilir: https://<service>-<hash>.<region>.run.app
_allowed_hosts = ["localhost", "localhost:8080", "127.0.0.1", "127.0.0.1:8080"]
if _RUN_URL:
    _allowed_hosts.append(_RUN_URL.replace("https://", "").replace("http://", "").rstrip("/"))
# Cloud Run her zaman *.run.app altinda servis eder; ek olarak proje/servis'e
# ozel sabit hostname'i de ekliyoruz.
_allowed_hosts.append("mcp-tools-service-84652974991.us-central1.run.app")

_transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=_allowed_hosts,
    allowed_origins=[f"https://{h}" for h in _allowed_hosts] + [f"http://{h}" for h in _allowed_hosts],
)

# stateless_http=True: Cloud Run instance'lari kapanip acilabilir / olceklenebilir,
# bu yuzden MCP oturumlari tek bir container'a sabitlenmemeli.
mcp = FastMCP("telemetry-tools", stateless_http=True, transport_security=_transport_security)


@mcp.tool()
async def query_live_well_pressure(well_id: str) -> str:
    """BigQuery uzerindeki canli kuyu basinc telemetrisini sorgular."""
    query = """
        SELECT well_id, pressure_psi, temperature_c, timestamp
        FROM `{project}.telemetry_data.well_metrics`
        WHERE well_id = @well_id
        ORDER BY timestamp DESC
        LIMIT 1
    """.format(project=PROJECT_ID)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("well_id", "STRING", well_id)
        ]
    )

    loop = asyncio.get_event_loop()
    query_job = await loop.run_in_executor(
        None, lambda: bq_client.query(query, job_config=job_config).result()
    )

    rows = list(query_job)
    if not rows:
        return f"Kuyu kaydi bulunamadi: {well_id}"

    row = rows[0]
    psi = row["pressure_psi"]
    status = "KRITIK SAPMA" if psi > 4000 else "NORMAL"
    return (
        f"[BigQuery Canli Telemetri] Kuyu: {row['well_id']} | "
        f"Basinc: {psi} PSI | Sicaklik: {row['temperature_c']}C | Durum: {status}"
    )


# Cloud Run icin ASGI uygulamasi (Dockerfile bunu "mcp_server:app" olarak calistirir).
# MCP uc noktasi varsayilan olarak /mcp altindadir (streamable_http_path).
app = mcp.streamable_http_app()


async def _health_check(request):
    from starlette.responses import JSONResponse
    return JSONResponse({"status": "healthy"})


# Starlette >=1.0'da @app.route decorator'i kaldirildigi icin route'u dogrudan
# router'a ekliyoruz (uygulama henuz istek almaya baslamadan, import sirasinda
# calistigindan guvenlidir).
from starlette.routing import Route  # noqa: E402
app.router.routes.append(Route("/health", _health_check))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
