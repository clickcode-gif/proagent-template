import os
import uuid
import asyncio
import operator
from typing import Annotated, Sequence, TypedDict, Literal, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langchain_google_vertexai import ChatVertexAI
from google.cloud import bigquery
from langgraph_checkpoint_firestore import FirestoreSaver

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", os.getenv("PROJECT_ID", "default-project"))
LOCATION = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
CHECKPOINTS_COLLECTION = os.getenv("CHECKPOINTS_COLLECTION", "agent_checkpoints")

bq_client = bigquery.Client(project=PROJECT_ID)

# 1. Gercek Arac Tanimi (BigQuery Canli Telemetri Sorgusu)
@tool
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

    # Asenkron yurutme (BigQuery client'i senkron oldugu icin executor'a devrediyoruz)
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

# Arac listesi
tools = [query_live_well_pressure]
tools_dict = {t.name: t for t in tools}

# 2. Semalandirilmis Durum (State)
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    step_count: int
    approved: bool

# 3. Model Kurulumu
llm = ChatVertexAI(
    model_name="gemini-2.5-flash",
    project=PROJECT_ID,
    location=LOCATION,
    temperature=0.0
).bind_tools(tools)

# 4. Graf Dugumleri (Nodes)
async def agent_node(state: AgentState) -> dict:
    """Karar dugumu: LLM mevcut durumu analiz eder."""
    current_steps = state.get("step_count", 0)
    response = await llm.ainvoke(state["messages"])
    return {
        "messages": [response],
        "step_count": current_steps + 1
    }

async def tool_node(state: AgentState) -> dict:
    """Arac yurutme dugumu: Talep edilen araclari asenkron calistirir."""
    last_message = state["messages"][-1]
    tool_messages = []

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            selected_tool = tools_dict.get(tool_name)

            if selected_tool:
                result = await selected_tool.ainvoke(tool_args)
            else:
                result = f"Hata: Tanimsiz arac '{tool_name}'."

            tool_messages.append(
                ToolMessage(content=str(result), tool_call_id=tool_call["id"])
            )

    return {"messages": tool_messages}

async def await_approval_node(state: AgentState) -> dict:
    """Human-in-the-Loop dugumu: Grafin yurutmesi bu dugumden ONCE duraklatilir
    (interrupt_before). Buraya gercekten girildiyse, operator /approve uc noktasi
    ile onay vermis demektir."""
    return {"approved": True}

# 5. Kosullu Gecis ve Devre Kesici (Circuit Breaker)
def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
    # 5 adimdan fazla donguye girerse zorla durdur (Circuit Breaker)
    if state.get("step_count", 0) >= 5:
        return END

    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"

    return END

def route_after_tools(state: AgentState) -> Literal["await_approval", "agent", "__end__"]:
    """Arac sonucu kritik bir sapma bildiriyorsa ve henuz onay alinmadiysa,
    grafi insan onayi beklemesi icin await_approval dugumune yonlendirir."""
    if state.get("step_count", 0) >= 5:
        return END

    last_message = state["messages"][-1]
    content = str(getattr(last_message, "content", ""))
    if "KRITIK SAPMA" in content and not state.get("approved", False):
        return "await_approval"

    return "agent"

# 6. Grafin Derlenmesi
workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tool_node)
workflow.add_node("await_approval", await_approval_node)

workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, {
    "tools": "tools",
    END: END
})
workflow.add_conditional_edges("tools", route_after_tools, {
    "await_approval": "await_approval",
    "agent": "agent",
    END: END
})
workflow.add_edge("await_approval", "agent")

# Kalici Checkpointer: Cloud Run container'i yeniden baslasa veya baska bir
# instance'a dussa bile, onay bekleyen (pending approval) is parcacigi
# Firestore'da kalici olarak saklanir.
checkpointer = FirestoreSaver(
    project_id=PROJECT_ID,
    checkpoints_collection=CHECKPOINTS_COLLECTION,
)

agent_executor = workflow.compile(
    checkpointer=checkpointer,
    interrupt_before=["await_approval"],
)

# 7. FastAPI Uygulamasi
app = FastAPI(title="Google Cloud Asynchronous Agent Service", version="2.0.0")

class InvokeRequest(BaseModel):
    prompt: str
    thread_id: Optional[str] = None

class InvokeResponse(BaseModel):
    status: Literal["completed", "pending_approval"]
    thread_id: str
    reply: Optional[str] = None
    pending_detail: Optional[str] = None
    total_steps: int


def _extract_text(raw_content) -> str:
    if isinstance(raw_content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in raw_content
        )
    return raw_content


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post("/invoke", response_model=InvokeResponse)
async def invoke_agent(request: InvokeRequest):
    thread_id = request.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    try:
        initial_state = {
            "messages": [HumanMessage(content=request.prompt)],
            "step_count": 0,
            "approved": False,
        }

        final_state = await agent_executor.ainvoke(initial_state, config=config)
        snapshot = await agent_executor.aget_state(config)

        if snapshot.next:
            # Graf, onay bekleyen bir dugumun hemen oncesinde durduruldu.
            last_message = final_state["messages"][-1]
            return InvokeResponse(
                status="pending_approval",
                thread_id=thread_id,
                pending_detail=_extract_text(last_message.content),
                total_steps=final_state.get("step_count", 0),
            )

        last_message = final_state["messages"][-1]
        return InvokeResponse(
            status="completed",
            thread_id=thread_id,
            reply=_extract_text(last_message.content),
            total_steps=final_state.get("step_count", 0),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/approve/{thread_id}", response_model=InvokeResponse)
async def approve_pending_action(thread_id: str):
    """Operator onayi: duraklatilmis is parcacigini kaldigi yerden devam ettirir."""
    config = {"configurable": {"thread_id": thread_id}}
    try:
        snapshot = await agent_executor.aget_state(config)
        if not snapshot.next:
            raise HTTPException(
                status_code=409,
                detail="Bu is parcacigi (thread_id) onay beklemiyor.",
            )

        final_state = await agent_executor.ainvoke(None, config=config)
        last_message = final_state["messages"][-1]
        return InvokeResponse(
            status="completed",
            thread_id=thread_id,
            reply=_extract_text(last_message.content),
            total_steps=final_state.get("step_count", 0),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reject/{thread_id}")
async def reject_pending_action(thread_id: str):
    """Operator reddi: is parcacigi kalici olarak onay bekler durumda kalir,
    graf devam ettirilmez (yani ajan hicbir ileri eylem almaz)."""
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = await agent_executor.aget_state(config)
    if not snapshot.next:
        raise HTTPException(
            status_code=409,
            detail="Bu is parcacigi (thread_id) onay beklemiyor.",
        )
    await agent_executor.aupdate_state(config, {"approved": False})
    return {"status": "rejected", "thread_id": thread_id}


@app.get("/status/{thread_id}")
async def get_status(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = await agent_executor.aget_state(config)
    if not snapshot.values:
        raise HTTPException(status_code=404, detail="is parcacigi bulunamadi.")

    pending = bool(snapshot.next)
    messages = snapshot.values.get("messages", [])
    last_message = messages[-1] if messages else None

    return {
        "thread_id": thread_id,
        "status": "pending_approval" if pending else "completed",
        "last_message": _extract_text(last_message.content) if last_message else None,
        "step_count": snapshot.values.get("step_count", 0),
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
