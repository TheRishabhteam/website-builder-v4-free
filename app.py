import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import anthropic
from fastapi import Body, FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

import designs

app = FastAPI()

INDEX = Path(__file__).parent / "public" / "index.html"
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5").strip() or "claude-sonnet-5-5"
MAX_TOKENS = {"hero": 6500, "services": 7000, "gallery": 5500}


def api_key():
    return os.environ.get("ANTHROPIC_API_KEY", "").strip()


def explain(e):
    """Turn an Anthropic SDK error into a short, actionable message."""
    detail = str(e)
    low = detail.lower()
    if isinstance(e, anthropic.AuthenticationError):
        return "Claude API key galat ya expire hai (401). Vercel me ANTHROPIC_API_KEY check karo, nayi key daalo aur Redeploy karo."
    if isinstance(e, anthropic.PermissionDeniedError):
        return "Is API key ko ye model use karne ki permission nahi hai (403). Console me key/workspace check karo."
    if isinstance(e, anthropic.NotFoundError):
        return "Model '%s' nahi mila (404). Vercel me CLAUDE_MODEL variable se sahi model naam daalo." % MODEL
    if isinstance(e, anthropic.RateLimitError):
        return "Claude ki rate limit lag gayi (429). 1 minute ruk kar dobara try karo."
    if isinstance(e, anthropic.BadRequestError):
        if "credit balance" in low or "billing" in low:
            return "Anthropic account me credits khatam hain ya billing chalu nahi hai. Console -> Plans & Billing me credits add karo."
        return "Claude ne request reject ki (400): %s" % detail[:240]
    if isinstance(e, (anthropic.APIConnectionError, anthropic.APITimeoutError)):
        return "Claude se connection nahi ho paaya / timeout hua. Dobara try karo."
    status = getattr(e, "status_code", None)
    if status in (500, 502, 503, 529):
        return "Claude abhi busy hai (%s). Thodi der baad dobara try karo." % status
    return detail[:300]


def call_claude(system, user, max_tokens):
    client = anthropic.Anthropic(api_key=api_key(), max_retries=5, timeout=250.0)
    msg = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
    return text, msg.stop_reason


@app.get("/", response_class=HTMLResponse)
def home():
    return INDEX.read_text(encoding="utf-8")


@app.get("/api/generate")
@app.get("/api/health")
def health():
    return {
        "status": "AI Website Builder API is running!",
        "key_configured": bool(api_key()),
        "model": MODEL,
    }


@app.post("/api/generate")
def generate(payload: dict = Body(...)):
    try:
        section = str(payload.get("section", "")).strip()

        if section == "brief":
            return designs.make_brief(payload)

        if not api_key():
            return JSONResponse(
                {"error": "ANTHROPIC_API_KEY Vercel me set nahi hai. Settings -> Environment Variables me add karo aur Redeploy karo."},
                status_code=500,
            )

        if section == "ping":
            text, _ = call_claude("Reply with the single word OK.", "ping", 16)
            return {"ok": True, "reply": text.strip()[:40], "model": MODEL}

        if section not in designs.RECIPES:
            return JSONResponse({"error": "Unknown section: %s" % section[:40]}, status_code=400)

        system, user, allowed = designs.build_prompt(section, payload)
        text, stop = call_claude(system, user, MAX_TOKENS.get(section, 5000))
        html = designs.sanitize_html(text, allowed, truncated=(stop == "max_tokens"))
        if len(html) < 120 or "<" not in html:
            return JSONResponse({"error": "Claude ne khaali/galat output diya. Dobara try karo."}, status_code=502)
        return {"html": html, "src": "Claude", "truncated": stop == "max_tokens"}

    except Exception as e:  # noqa: BLE001 - report every failure to the page
        return JSONResponse({"error": explain(e)}, status_code=500)
