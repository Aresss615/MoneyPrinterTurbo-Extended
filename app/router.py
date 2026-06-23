"""Application configuration - root APIRouter.

Defines all FastAPI application endpoints.

Resources:
    1. https://fastapi.tiangolo.com/tutorial/bigger-applications

"""

from fastapi import APIRouter

from app.controllers.v1 import creator, facebook, health, legal, llm, tiktok, video

root_api_router = APIRouter()
# v1
root_api_router.include_router(video.router)
root_api_router.include_router(creator.router)
root_api_router.include_router(llm.router)
root_api_router.include_router(tiktok.router)
root_api_router.include_router(facebook.router)
# Public legal pages at clean /legal/* URLs (no /api/v1 prefix, no 'tiktok')
root_api_router.include_router(legal.router)
# Liveness check pinged by the always-on website to flag the bot online/offline
root_api_router.include_router(health.router)
