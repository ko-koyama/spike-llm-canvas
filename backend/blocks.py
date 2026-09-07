"""Strands Agentのメッセージ列をチャット表示用のブロック列に変換する。"""

from typing import Literal

from pydantic import BaseModel
from strands.types.content import Message
from strands.types.tools import ToolResult

HTML_TOOL_NAMES = {"render_chart", "render_map"}


class Block(BaseModel):
    """チャット表示用の1ブロック(テキストまたはツール結果のHTML)。"""

    type: Literal["text", "chart"]
    text: str | None = None
    html: str | None = None


def messages_to_blocks(messages: list[Message]) -> list[Block]:
    """assistantの発言とrender_chartの結果を、発生順のブロック列に変換する。"""
    html_tool_use_ids: set[str] = set()
    blocks: list[Block] = []

    for message in messages:
        for content in message["content"]:
            if "toolUse" in content:
                if content["toolUse"]["name"] in HTML_TOOL_NAMES:
                    html_tool_use_ids.add(content["toolUse"]["toolUseId"])
            elif "toolResult" in content:
                if content["toolResult"]["toolUseId"] in html_tool_use_ids:
                    html = _extract_text(content["toolResult"])
                    if html:
                        blocks.append(Block(type="chart", html=html))
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
