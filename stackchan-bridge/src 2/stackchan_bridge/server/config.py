from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


class Settings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    session_stale_seconds: int = 30
    compat_enabled: bool = True
    agent_max_iterations: int = 3
    lm_studio_base_url: str = "http://127.0.0.1:1234/v1"
    lm_studio_model: str = "local-model"
    lm_studio_api_key: str | None = "lm-studio"
    lm_studio_timeout_seconds: float = 30.0
    home_assistant_enabled: bool = False
    home_assistant_base_url: str | None = "http://127.0.0.1:8123"
    home_assistant_token: str | None = None
    rover_enabled: bool = False
    rover_simulation_mode: bool = True
    rover_rpc_socket_path: str | None = "/var/run/arduino-router.sock"
    rover_rpc_host: str = "127.0.0.1"
    rover_rpc_port: int = 50051
    rover_rpc_timeout_seconds: float = 2.0
    rover_loop_interval_ms: int = 500
    rover_admin_socket: str = "/tmp/stackchan-rover-admin.sock"
    rover_observation_sequence: str = "unknown,clear,blocked_left,blocked_right"
    speaker_name: str = "Bridge"
    project_root: Path = Field(default_factory=_project_root)

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(_project_root() / ".env")
        return cls(
            host=_env("STACKCHAN_BRIDGE_HOST", "127.0.0.1"),
            port=int(_env("STACKCHAN_BRIDGE_PORT", "8000")),
            log_level=_env("STACKCHAN_BRIDGE_LOG_LEVEL", "INFO"),
            session_stale_seconds=int(_env("STACKCHAN_BRIDGE_SESSION_STALE_SECONDS", "30")),
            compat_enabled=_env_bool("STACKCHAN_BRIDGE_COMPAT_ENABLED", True),
            agent_max_iterations=int(_env("STACKCHAN_BRIDGE_AGENT_MAX_ITERATIONS", "3")),
            lm_studio_base_url=_env("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234/v1"),
            lm_studio_model=_env("LM_STUDIO_MODEL", "local-model"),
            lm_studio_api_key=_env("LM_STUDIO_API_KEY", "lm-studio"),
            lm_studio_timeout_seconds=float(_env("LM_STUDIO_TIMEOUT_SECONDS", "30")),
            home_assistant_enabled=_env_bool("HOME_ASSISTANT_ENABLED", False),
            home_assistant_base_url=_env("HOME_ASSISTANT_BASE_URL", "http://127.0.0.1:8123"),
            home_assistant_token=_env("HOME_ASSISTANT_TOKEN", "") or None,
            rover_enabled=_env_bool("ROVER_ENABLED", False),
            rover_simulation_mode=_env_bool("ROVER_SIMULATION_MODE", True),
            rover_rpc_socket_path=_env("ROVER_RPC_SOCKET_PATH", "/var/run/arduino-router.sock").strip() or None,
            rover_rpc_host=_env("ROVER_RPC_HOST", "127.0.0.1"),
            rover_rpc_port=int(_env("ROVER_RPC_PORT", "50051")),
            rover_rpc_timeout_seconds=float(_env("ROVER_RPC_TIMEOUT_SECONDS", "2.0")),
            rover_loop_interval_ms=int(_env("ROVER_LOOP_INTERVAL_MS", "500")),
            rover_admin_socket=_env("ROVER_ADMIN_SOCKET", "/tmp/stackchan-rover-admin.sock"),
            rover_observation_sequence=_env("ROVER_OBSERVATION_SEQUENCE", "unknown,clear,blocked_left,blocked_right"),
        )


def _env(name: str, default: str) -> str:
    import os

    return os.getenv(name, default)


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name, "true" if default else "false").strip().lower()
    return value in {"1", "true", "yes", "on"}
