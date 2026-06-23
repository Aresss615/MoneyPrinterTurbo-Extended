"""Lightweight liveness endpoint for the bot backend.

The always-on website (GitHub Pages at johnchrisley.dev/legal) pings this from
the browser to flag whether the bot/Mac is online. It must stay cheap — no
upstream API calls — and is served at a clean path (no /api/v1, no 'tiktok')
so the offline badge degrades to 'offline' the moment the Mac/tunnel is down.
"""

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health", summary="Liveness check for the bot backend")
def health(request: Request):
    return {"status": "ok"}
