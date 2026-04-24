from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI

from stackchan_bridge.adapters.home_assistant import HomeAssistantAdapter
from stackchan_bridge.adapters.lm_studio import LocalLLMAdapter
from stackchan_bridge.agent.runtime import AgentRuntime
from stackchan_bridge.rover.linux_controller import (
    CyclingObservationProvider,
    FakeBridgeClient,
    RoverLinuxController,
    SnapshotPlaceholderObservationProvider,
    UnoQRpcClient,
)
from stackchan_bridge.server.config import Settings
from stackchan_bridge.server.http import router as http_router
from stackchan_bridge.server.logging import configure_logging
from stackchan_bridge.server.sessions import SessionManager
from stackchan_bridge.server.ws import router as ws_router
from stackchan_bridge.tools.registry import ToolRegistry


@dataclass
class AppContext:
    settings: Settings
    sessions: SessionManager
    llm_adapter: LocalLLMAdapter
    home_assistant: HomeAssistantAdapter
    rover_controller: RoverLinuxController | None
    tools: ToolRegistry
    agent: AgentRuntime


def create_app(
    settings: Settings | None = None,
    *,
    llm_adapter: LocalLLMAdapter | None = None,
    home_assistant: HomeAssistantAdapter | None = None,
    rover_controller: RoverLinuxController | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level)

    sessions = SessionManager()
    llm = llm_adapter or LocalLLMAdapter(
        base_url=settings.lm_studio_base_url,
        model=settings.lm_studio_model,
        api_key=settings.lm_studio_api_key,
        timeout_seconds=settings.lm_studio_timeout_seconds,
    )
    ha = home_assistant or HomeAssistantAdapter(
        enabled=settings.home_assistant_enabled,
        base_url=settings.home_assistant_base_url,
        token=settings.home_assistant_token,
    )
    rover = rover_controller or _create_rover_controller(settings)
    tools = ToolRegistry(ha, rover_controller=rover)
    agent = AgentRuntime(
        llm_adapter=llm,
        tool_registry=tools,
        session_manager=sessions,
        speaker_name=settings.speaker_name,
        max_iterations=settings.agent_max_iterations,
    )

    app = FastAPI(title="stackchan-bridge", version="0.1.0")
    app.state.context = AppContext(
        settings=settings,
        sessions=sessions,
        llm_adapter=llm,
        home_assistant=ha,
        rover_controller=rover,
        tools=tools,
        agent=agent,
    )
    app.include_router(http_router)
    app.include_router(ws_router)
    return app


def _create_rover_controller(settings: Settings) -> RoverLinuxController | None:
    if not settings.rover_enabled:
        return None

    if settings.rover_simulation_mode:
        bridge_client = FakeBridgeClient(source="in_process")
    else:
        bridge_client = UnoQRpcClient(
            socket_path=settings.rover_rpc_socket_path,
            host=settings.rover_rpc_host,
            port=settings.rover_rpc_port,
            timeout_seconds=settings.rover_rpc_timeout_seconds,
        )

    return RoverLinuxController(
        bridge_client=bridge_client,
        observation_provider=SnapshotPlaceholderObservationProvider(),
        loop_interval_ms=settings.rover_loop_interval_ms,
    )
