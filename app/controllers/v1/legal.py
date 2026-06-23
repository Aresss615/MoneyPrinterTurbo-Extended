"""Public legal pages served at clean, non-'tiktok' URLs.

TikTok app review rejected the Terms of Service and Privacy Policy links for
containing the word 'tiktok' (they were under /api/v1/tiktok/*). These routes
expose the same documents — plus a simple landing page used as the app's
Website URL — under /legal/* so the URLs entered in the dev portal pass review.

The TikTok domain-verification files are also served beneath these paths so the
/legal URL properties can be verified in the dev portal.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from app.controllers.v1.tiktok import _load_markdown_doc, _serve_verification_file

router = APIRouter()
router.tags = ["legal"]
router.prefix = "/legal"


_LANDING_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JC Video Factory</title>
<style>
  body { font-family: -apple-system, system-ui, sans-serif; max-width: 40rem;
         margin: 4rem auto; padding: 0 1.25rem; line-height: 1.6; color: #1a1a1a; }
  h1 { margin-bottom: 0.25rem; }
  a { color: #c8102e; }
  footer { margin-top: 2.5rem; font-size: 0.9rem; color: #666; }
</style>
</head>
<body>
  <h1>JC Video Factory</h1>
  <p>JC Video Factory is a personal tool that helps create and publish
     short-form videos. It lets the account owner generate a video and send it
     to their own connected social accounts (including TikTok) for posting.</p>
  <p>Legal documents:</p>
  <ul>
    <li><a href="/legal/terms">Terms of Service</a></li>
    <li><a href="/legal/privacy">Privacy Policy</a></li>
  </ul>
  <footer>Contact: johnchrisley4@gmail.com</footer>
</body>
</html>
"""


@router.get("", summary="Legal landing page (app Website URL)")
@router.get("/", summary="Legal landing page (app Website URL)")
def legal_landing(request: Request):
    return HTMLResponse(_LANDING_PAGE)


@router.get("/terms", summary="Terms of Service page")
def legal_terms(request: Request):
    return PlainTextResponse(_load_markdown_doc("tiktok-terms.md"))


@router.get("/privacy", summary="Privacy Policy page")
def legal_privacy(request: Request):
    return PlainTextResponse(_load_markdown_doc("tiktok-privacy.md"))


@router.get("/terms/{verification_filename}")
def legal_terms_verification_file(request: Request, verification_filename: str):
    return _serve_verification_file(verification_filename)


@router.get("/privacy/{verification_filename}")
def legal_privacy_verification_file(request: Request, verification_filename: str):
    return _serve_verification_file(verification_filename)


@router.get("/{verification_filename}")
def legal_verification_file(request: Request, verification_filename: str):
    return _serve_verification_file(verification_filename)
