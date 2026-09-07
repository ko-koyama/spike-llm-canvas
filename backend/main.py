"""検証用のシンプルなAIチャットのFastAPIバックエンド。"""

from fastapi import FastAPI
from pydantic import BaseModel
from strands import Agent

from blocks import Block, messages_to_blocks
from tools import render_chart, render_map

# 会話履歴は永続化せず、プロセスが生きている間だけメモリ上に保持する。
AGENTS: dict[str, Agent] = {}


class ChatRequest(BaseModel):
    message: str
    # 会話履歴はsession_id単位でAgentをメモリに紐付けて管理する。
    session_id: str


class ChatResponse(BaseModel):
    blocks: list[Block]


app = FastAPI(title="Spike LLM Canvas")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat")
async def chat(req: ChatRequest) -> ChatResponse:
    agent = AGENTS.setdefault(req.session_id, Agent(tools=[render_chart, render_map]))
    messages_before = len(agent.messages)
    await agent.invoke_async(req.message)
    new_messages = agent.messages[messages_before:]
    return ChatResponse(blocks=messages_to_blocks(new_messages))
