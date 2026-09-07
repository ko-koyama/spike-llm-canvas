"""Strands Agentのメッセージ列をチャット表示用のブロック列に変換する。"""

from typing import Literal

from pydantic import BaseModel
from strands.types.content import Message
from strands.types.tools import ToolResult

# HTML描画ツール名 → チャット表示用のブロック種別
HTML_TOOL_BLOCK_TYPES = {
    "render_chart": "chart",
    "render_choropleth": "map",
    "render_spider": "map",
}


class Block(BaseModel):
    """チャット表示用の1ブロック(テキストまたはツール結果のHTML)。"""

    type: Literal["text", "chart", "map"]
    text: str | None = None
    html: str | None = None


def messages_to_blocks(messages: list[Message]) -> list[Block]:
    """assistantの発言とHTML描画ツールの結果を、発生順のブロック列に変換する。"""
    block_types_by_tool_use_id: dict[str, str] = {}
    blocks: list[Block] = []

    for message in messages:
        for content in message["content"]:
            if "toolUse" in content:
                tool_use_id = content["toolUse"]["toolUseId"]
                block_type = HTML_TOOL_BLOCK_TYPES.get(content["toolUse"]["name"])
                if block_type:
                    block_types_by_tool_use_id[tool_use_id] = block_type
            elif "toolResult" in content:
                tool_use_id = content["toolResult"]["toolUseId"]
                block_type = block_types_by_tool_use_id.get(tool_use_id)
                if block_type:
                    html = _extract_text(content["toolResult"])
                    if html:
                        blocks.append(Block(type=block_type, html=html))
            elif "text" in content and message["role"] == "assistant":
                if content["text"]:
                    blocks.append(Block(type="text", text=content["text"]))

    return blocks


def _extract_text(tool_result: ToolResult) -> str | None:
    """ToolResultのcontentからtextを取り出す。"""
    for item in tool_result["content"]:
        if "text" in item:
            return item["text"]
    return None
