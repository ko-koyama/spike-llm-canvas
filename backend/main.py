"""検証用のシンプルなAIチャットのFastAPIバックエンド。"""

from fastapi import FastAPI
from pydantic import BaseModel
from strands import Agent

# 会話履歴は永続化せず、プロセスが生きている間だけメモリ上に保持する。
AGENTS: dict[str, Agent] = {}


class ChatRequest(BaseModel):
    message: str
    # 会話履歴はsession_id単位でAgentをメモリに紐付けて管理する。
    session_id: str


class ChatResponse(BaseModel):
    reply: str


app = FastAPI(title="Spike LLM Canvas")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat")
async def chat(req: ChatRequest) -> ChatResponse:
    agent = AGENTS.setdefault(req.session_id, Agent())
    result = await agent.invoke_async(req.message)
    return ChatResponse(reply=str(result))
