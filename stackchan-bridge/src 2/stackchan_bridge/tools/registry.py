from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from stackchan_bridge.adapters.home_assistant import HomeAssistantAdapter
from stackchan_bridge.agent.types import ToolDefinition
from stackchan_bridge.rover.protocol import RoverCommand, RoverCommandName
from stackchan_bridge.protocol.json_models import (
    CaptureSnapshotAction,
    MoveHeadAction,
    SetExpressionAction,
    SpeakTextAction,
)
from stackchan_bridge.server.device import BridgeDevice

from stackchan_bridge.rover.linux_controller import RoverLinuxController


class ToolExecutionResult(BaseModel):
    tool_name: str
    content: str
    actions: list[Any] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class ToolContext(BaseModel):
    device: BridgeDevice
    home_assistant: HomeAssistantAdapter
    rover_controller: Any | None = None

    model_config = {"arbitrary_types_allowed": True}


class MoveHeadArgs(BaseModel):
    yaw: int
    pitch: int


class SetExpressionArgs(BaseModel):
    name: str


class SpeakTextArgs(BaseModel):
    text: str


class EmptyArgs(BaseModel):
    pass


class HomeAssistantArgs(BaseModel):
    domain: str
    service: str
    data: dict[str, Any] = Field(default_factory=dict)


class RoverDriveArgs(BaseModel):
    left_pwm: int
    right_pwm: int
    duration_ms: int


class RoverTurnArgs(BaseModel):
    left_pwm: int
    right_pwm: int
    duration_ms: int


class ToolRegistry:
    def __init__(self, home_assistant: HomeAssistantAdapter, rover_controller: RoverLinuxController | None = None) -> None:
        self.home_assistant = home_assistant
        self.rover_controller = rover_controller
        self._definitions: dict[str, ToolDefinition] = {
            "move_head": ToolDefinition(
                name="move_head",
                description="Move the StackChan head using yaw and pitch angles.",
                parameters=MoveHeadArgs.model_json_schema(),
            ),
            "set_expression": ToolDefinition(
                name="set_expression",
                description="Set a named expression such as happy, neutral, sad, or surprised.",
                parameters=SetExpressionArgs.model_json_schema(),
            ),
            "speak_text": ToolDefinition(
                name="speak_text",
                description="Speak a short text response through the device.",
                parameters=SpeakTextArgs.model_json_schema(),
            ),
            "get_time": ToolDefinition(
                name="get_time",
                description="Return the current local UTC timestamp on the bridge host.",
                parameters=EmptyArgs.model_json_schema(),
            ),
            "capture_snapshot": ToolDefinition(
                name="capture_snapshot",
                description="Fetch the latest camera snapshot or request one from the device.",
                parameters=EmptyArgs.model_json_schema(),
            ),
            "trigger_home_assistant_service": ToolDefinition(
                name="trigger_home_assistant_service",
                description="Trigger a Home Assistant service call when the adapter is enabled.",
                parameters=HomeAssistantArgs.model_json_schema(),
            ),
            "rover_stop": ToolDefinition(
                name="rover_stop",
                description="Stop rover body motion immediately through the UNO Q rover controller.",
                parameters=EmptyArgs.model_json_schema(),
            ),
            "rover_drive": ToolDefinition(
                name="rover_drive",
                description="Drive the rover body with left and right PWM values for a bounded duration.",
                parameters=RoverDriveArgs.model_json_schema(),
            ),
            "rover_turn": ToolDefinition(
                name="rover_turn",
                description="Turn the rover body with signed left and right PWM values for a bounded duration.",
                parameters=RoverTurnArgs.model_json_schema(),
            ),
            "rover_status": ToolDefinition(
                name="rover_status",
                description="Return rover body status from the UNO Q Linux or MCU bridge layer.",
                parameters=EmptyArgs.model_json_schema(),
            ),
            "rover_observe_step": ToolDefinition(
                name="rover_observe_step",
                description="Perform one safe stop-observe-decide-move-stop rover step using placeholder perception.",
                parameters=EmptyArgs.model_json_schema(),
            ),
        }

    def definitions(self) -> list[ToolDefinition]:
        return list(self._definitions.values())

    async def execute(self, name: str, arguments: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        if name not in self._definitions:
            raise ValueError(f"Unknown tool: {name}")

        if name == "move_head":
            args = self._validate(MoveHeadArgs, arguments)
            return ToolExecutionResult(
                tool_name=name,
                content=f"Moved head to yaw={args.yaw}, pitch={args.pitch}.",
                actions=[MoveHeadAction(yaw=args.yaw, pitch=args.pitch)],
            )

        if name == "set_expression":
            args = self._validate(SetExpressionArgs, arguments)
            return ToolExecutionResult(
                tool_name=name,
                content=f"Set expression to {args.name}.",
                actions=[SetExpressionAction(name=args.name)],
            )

        if name == "speak_text":
            args = self._validate(SpeakTextArgs, arguments)
            return ToolExecutionResult(
                tool_name=name,
                content=f"Spoke text: {args.text}",
                actions=[SpeakTextAction(text=args.text)],
            )

        if name == "get_time":
            self._validate(EmptyArgs, arguments)
            now = datetime.now(UTC).isoformat()
            return ToolExecutionResult(tool_name=name, content=now, data={"timestamp": now})

        if name == "capture_snapshot":
            self._validate(EmptyArgs, arguments)
            if context.device.latest_snapshot:
                return ToolExecutionResult(
                    tool_name=name,
                    content="Returning latest cached snapshot.",
                    data={"byte_length": len(context.device.latest_snapshot)},
                )
            return ToolExecutionResult(
                tool_name=name,
                content="Requested a fresh snapshot from the device.",
                actions=[CaptureSnapshotAction()],
            )

        if name == "trigger_home_assistant_service":
            args = self._validate(HomeAssistantArgs, arguments)
            result = await context.home_assistant.trigger_service(args.domain, args.service, args.data)
            return ToolExecutionResult(
                tool_name=name,
                content=result["message"] if "message" in result else "Triggered Home Assistant service.",
                data=result,
            )

        if name == "rover_stop":
            self._validate(EmptyArgs, arguments)
            controller = self._resolve_rover(context)
            if controller is None:
                return self._rover_unavailable(name)
            status = await controller.stop()
            return ToolExecutionResult(
                tool_name=name,
                content="Stopped rover body motion.",
                data=status.model_dump(mode="json"),
            )

        if name == "rover_drive":
            args = self._validate(RoverDriveArgs, arguments)
            RoverCommand(
                cmd=RoverCommandName.DRIVE,
                left_pwm=args.left_pwm,
                right_pwm=args.right_pwm,
                duration_ms=args.duration_ms,
            )
            controller = self._resolve_rover(context)
            if controller is None:
                return self._rover_unavailable(name)
            status = await controller.drive(args.left_pwm, args.right_pwm, args.duration_ms)
            return ToolExecutionResult(
                tool_name=name,
                content=f"Rover drive command executed for {args.duration_ms} ms.",
                data=status.model_dump(mode="json"),
            )

        if name == "rover_turn":
            args = self._validate(RoverTurnArgs, arguments)
            RoverCommand(
                cmd=RoverCommandName.TURN,
                left_pwm=args.left_pwm,
                right_pwm=args.right_pwm,
                duration_ms=args.duration_ms,
            )
            controller = self._resolve_rover(context)
            if controller is None:
                return self._rover_unavailable(name)
            status = await controller.turn(args.left_pwm, args.right_pwm, args.duration_ms)
            return ToolExecutionResult(
                tool_name=name,
                content=f"Rover turn command executed for {args.duration_ms} ms.",
                data=status.model_dump(mode="json"),
            )

        if name == "rover_status":
            self._validate(EmptyArgs, arguments)
            controller = self._resolve_rover(context)
            if controller is None:
                return self._rover_unavailable(name)
            status = await controller.status()
            return ToolExecutionResult(
                tool_name=name,
                content="Fetched rover status.",
                data=status.model_dump(mode="json"),
            )

        if name == "rover_observe_step":
            self._validate(EmptyArgs, arguments)
            controller = self._resolve_rover(context)
            if controller is None:
                return self._rover_unavailable(name)
            result = await controller.observe_step(context.device)
            actions = []
            if result.observation.state == "unknown" and self._camera_enabled(context.device) and not context.device.latest_snapshot:
                actions.append(CaptureSnapshotAction())
            return ToolExecutionResult(
                tool_name=name,
                content=f"Observe step chose {result.decision.action}.",
                actions=actions,
                data=result.model_dump(mode="json"),
            )

        raise ValueError(f"Unhandled tool: {name}")

    def _validate(self, model: type[BaseModel], arguments: dict[str, Any]) -> BaseModel:
        try:
            return model.model_validate(arguments)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

    def _resolve_rover(self, context: ToolContext) -> RoverLinuxController | None:
        controller = context.rover_controller or self.rover_controller
        if controller is None:
            return None
        return controller

    def _rover_unavailable(self, tool_name: str) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_name=tool_name,
            content="Rover controller is unavailable.",
            data={"status": "unavailable"},
        )

    def _camera_enabled(self, device: BridgeDevice) -> bool:
        capabilities = device.record.capabilities
        if isinstance(capabilities, dict):
            camera = capabilities.get("camera", {})
            return bool(camera.get("enabled"))
        return bool(capabilities.camera.enabled)
