from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

import httpx

from stackchan_bridge.agent.types import LLMResponse, ToolCall, ToolDefinition


TOOL_LINE_RE = re.compile(r"TOOL:(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\s+(?P<args>\{.*\})", re.DOTALL)


class LocalLLMAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._transport = transport

    async def chat(self, messages: list[dict[str, Any]], tools: list[ToolDefinition]) -> LLMResponse:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        body = {
            "model": self.model,
            "messages": messages,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in tools
            ],
            "tool_choice": "auto",
        }

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            transport=self._transport,
        ) as client:
            response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
            response.raise_for_status()
            data = response.json()

        message = data["choices"][0]["message"]
        content = message.get("content") or ""
        parsed_calls = self._parse_tool_calls(message.get("tool_calls", []))
        if parsed_calls:
            return LLMResponse(content=content, tool_calls=parsed_calls)

        inline_calls, cleaned_content = self._extract_inline_tool_calls(content)
        return LLMResponse(content=cleaned_content, tool_calls=inline_calls)

    def _parse_tool_calls(self, raw_tool_calls: list[dict[str, Any]]) -> list[ToolCall]:
        parsed: list[ToolCall] = []
        for tool_call in raw_tool_calls:
            function = tool_call.get("function") or {}
            arguments_text = function.get("arguments") or "{}"
            try:
                arguments = json.loads(arguments_text)
            except json.JSONDecodeError:
                continue
            parsed.append(
                ToolCall(
                    id=tool_call.get("id", str(uuid4())),
                    name=function["name"],
                    arguments=arguments,
                )
            )
        return parsed

    def _extract_inline_tool_calls(self, content: str) -> tuple[list[ToolCall], str]:
        stripped = content.strip()
        if not stripped:
            return [], content

        try:
            decoded = json.loads(stripped)
        except json.JSONDecodeError:
            decoded = None

        if isinstance(decoded, dict):
            if "tool" in decoded:
                return [
                    ToolCall(
                        id=str(uuid4()),
                        name=decoded["tool"],
                        arguments=decoded.get("arguments", {}),
                    )
                ], ""
            if "tools" in decoded and isinstance(decoded["tools"], list):
                tool_calls = [
                    ToolCall(
                        id=str(uuid4()),
                        name=entry["tool"],
                        arguments=entry.get("arguments", {}),
                    )
                    for entry in decoded["tools"]
                ]
                return tool_calls, ""

        match = TOOL_LINE_RE.search(stripped)
        if not match:
            return [], content

        try:
            arguments = json.loads(match.group("args"))
        except json.JSONDecodeError:
            return [], content

        tool_call = ToolCall(id=str(uuid4()), name=match.group("name"), arguments=arguments)
        cleaned = stripped.replace(match.group(0), "").strip()
        return [tool_call], cleaned

