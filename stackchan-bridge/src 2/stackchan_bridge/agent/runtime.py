from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from stackchan_bridge.adapters.lm_studio import LocalLLMAdapter
from stackchan_bridge.protocol.json_models import ActionModel, SetExpressionAction, SpeakTextAction
from stackchan_bridge.server.device import BridgeDevice
from stackchan_bridge.server.sessions import SessionManager
from stackchan_bridge.tools.registry import ToolContext, ToolExecutionResult, ToolRegistry


logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You control a physical desktop companion robot.
Use tools when they help. Keep actions short, safe, and visible.
Prefer tool calls for device actions. If you answer in plain text, keep it concise."""


@dataclass
class AgentTurnResult:
    text: str
    actions: list[ActionModel] = field(default_factory=list)
    tool_results: list[ToolExecutionResult] = field(default_factory=list)


class AgentRuntime:
    def __init__(
        self,
        *,
        llm_adapter: LocalLLMAdapter,
        tool_registry: ToolRegistry,
        session_manager: SessionManager,
        speaker_name: str = "Bridge",
        max_iterations: int = 3,
    ) -> None:
        self.llm_adapter = llm_adapter
        self.tool_registry = tool_registry
        self.session_manager = session_manager
        self.speaker_name = speaker_name
        self.max_iterations = max_iterations

    async def handle_text(self, device_id: str, text: str) -> AgentTurnResult:
        session = self.session_manager.get(device_id)
        if not session:
            raise LookupError(f"Device {device_id} is not connected.")

        device = BridgeDevice(session, speaker_name=self.speaker_name)
        tool_context = ToolContext(
            device=device,
            home_assistant=self.tool_registry.home_assistant,
            rover_controller=self.tool_registry.rover_controller,
        )
        messages: list[dict[str, object]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]

        all_actions: list[ActionModel] = []
        tool_results: list[ToolExecutionResult] = []
        final_text = ""

        for _ in range(self.max_iterations):
            response = await self.llm_adapter.chat(messages, self.tool_registry.definitions())
            if not response.tool_calls:
                final_text = response.content.strip()
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments),
                            },
                        }
                        for call in response.tool_calls
                    ],
                }
            )

            for call in response.tool_calls:
                logger.info("executing tool %s", call.name)
                result = await self.tool_registry.execute(call.name, call.arguments, tool_context)
                tool_results.append(result)
                all_actions.extend(result.actions)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": json.dumps(
                            {
                                "content": result.content,
                                "data": result.data,
                            }
                        ),
                    }
                )
        else:
            final_text = ""

        if final_text and not any(action.kind == "speak_text" for action in all_actions):
            all_actions.append(SpeakTextAction(text=final_text))

        if not all_actions:
            fallback_text = final_text or f"I heard: {text}"
            all_actions = [
                SetExpressionAction(name="happy"),
                SpeakTextAction(text=fallback_text),
            ]

        sent_actions = await device.dispatch_actions(all_actions)
        logger.info("sent actions %s", sent_actions)
        return AgentTurnResult(text=final_text or text, actions=all_actions, tool_results=tool_results)
