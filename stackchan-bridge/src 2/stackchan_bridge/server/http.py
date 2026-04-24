from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from stackchan_bridge.protocol.json_models import ChatRequest, ChatResponse


router = APIRouter()


def _context(request: Request):
    return request.app.state.context


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/devices")
async def list_devices(request: Request) -> list[dict]:
    ctx = _context(request)
    ctx.sessions.expire_stale(ctx.settings.session_stale_seconds)
    return [summary.model_dump(mode="json") for summary in ctx.sessions.list_summaries(ctx.settings.session_stale_seconds)]


@router.post("/api/chat")
async def chat(request: Request, payload: ChatRequest) -> ChatResponse:
    ctx = _context(request)
    if not ctx.sessions.get(payload.device_id):
        raise HTTPException(status_code=404, detail=f"Device {payload.device_id} is not connected.")

    result = await ctx.agent.handle_text(payload.device_id, payload.text)
    return ChatResponse(
        device_id=payload.device_id,
        text=result.text,
        actions_sent=[action.kind for action in result.actions],
        tool_results=[item.content for item in result.tool_results],
    )

