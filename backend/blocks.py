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

# ツール名から一意に種別ラベルが決まるもの。render_chartのみ引数のstyleに依存する
FIXED_VARIANTS = {
    "render_choropleth": "choropleth",
    "render_spider": "spider",
}


class Block(BaseModel):
    """チャット表示用の1ブロック(テキストまたはツール結果のHTML)。"""

    type: Literal["text", "chart", "map"]
    # チャート種別(bar/line/scatter/pie)や地図種別(choropleth/spider)の詳細ラベル
    variant: str | None = None
    text: str | None = None
    html: str | None = None


def messages_to_blocks(messages: list[Message]) -> list[Block]:
    """assistantの発言とHTML描画ツールの結果を、発生順のブロック列に変換する。"""
    tool_info_by_id: dict[str, tuple[str, str | None]] = {}
    blocks: list[Block] = []

    for message in messages:
        for content in message["content"]:
            if "toolUse" in content:
                tool_use_id = content["toolUse"]["toolUseId"]
                name = content["toolUse"]["name"]
                block_type = HTML_TOOL_BLOCK_TYPES.get(name)
                if block_type:
                    variant = FIXED_VARIANTS.get(name) or content["toolUse"]["input"].get("style")
                    tool_info_by_id[tool_use_id] = (block_type, variant)
            elif "toolResult" in content:
                tool_use_id = content["toolResult"]["toolUseId"]
                info = tool_info_by_id.get(tool_use_id)
                if info:
                    block_type, variant = info
                    html = _extract_text(content["toolResult"])
                    if html:
                        blocks.append(Block(type=block_type, variant=variant, html=html))
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
