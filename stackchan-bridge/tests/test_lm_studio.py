from __future__ import annotations

import asyncio
import json

import httpx

from stackchan_bridge.adapters.lm_studio import LocalLLMAdapter
from stackchan_bridge.agent.types import ToolDefinition


TOOLS = [ToolDefinition(name="speak_text", description="Speak text.", parameters={"type": "object"})]


def mock_transport(payload: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


def test_lm_studio_plain_text_reply() -> None:
    async def run() -> None:
        adapter = LocalLLMAdapter(
            base_url="http://localhost:1234/v1",
            model="demo",
            transport=mock_transport({"choices": [{"message": {"content": "hello"}}]}),
        )
        response = await adapter.chat([{"role": "user", "content": "hi"}], TOOLS)
        assert response.content == "hello"
        assert response.tool_calls == []

    asyncio.run(run())


def test_lm_studio_tool_call_reply() -> None:
    async def run() -> None:
        adapter = LocalLLMAdapter(
            base_url="http://localhost:1234/v1",
            model="demo",
            transport=mock_transport(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "function": {
                                            "name": "speak_text",
                                            "arguments": json.dumps({"text": "hello"}),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            ),
        )
        response = await adapter.chat([{"role": "user", "content": "hi"}], TOOLS)
        assert response.tool_calls[0].name == "speak_text"
        assert response.tool_calls[0].arguments["text"] == "hello"

    asyncio.run(run())


def test_lm_studio_inline_tool_fallback() -> None:
    async def run() -> None:
        adapter = LocalLLMAdapter(
            base_url="http://localhost:1234/v1",
            model="demo",
            transport=mock_transport(
                {
                    "choices": [
                        {
                            "message": {
                                "content": 'TOOL:speak_text {"text":"hello from fallback"}',
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "function": {
                                            "name": "speak_text",
                                            "arguments": "{bad json",
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            ),
        )
        response = await adapter.chat([{"role": "user", "content": "hi"}], TOOLS)
        assert response.tool_calls[0].name == "speak_text"
        assert response.tool_calls[0].arguments["text"] == "hello from fallback"

    asyncio.run(run())

