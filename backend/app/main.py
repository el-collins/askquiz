from datetime import date
from typing import Literal, Optional

from fastapi import FastAPI, Form, File, UploadFile, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from groq import AsyncGroq

from app.config import load_settings
from app.db import create_pool, check_and_increment
from app.groq_client import ask_text, ask_image, GroqAnswerError

settings = load_settings()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_IMAGE_BYTES = 3_000_000  # keeps base64-encoded payload under Groq's 4MB limit

_IMAGE_SIGNATURES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
}


def _sniff_image_type(data: bytes) -> Optional[str]:
    for mime_type, signatures in _IMAGE_SIGNATURES.items():
        if any(data.startswith(sig) for sig in signatures):
            return mime_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"detail": jsonable_encoder(exc.errors())})


@app.on_event("startup")
async def startup() -> None:
    app.state.db_pool = await create_pool(settings.database_url)
    app.state.groq_client = AsyncGroq(
        api_key=settings.groq_api_key, timeout=15.0, max_retries=0
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ask")
async def ask(
    request: Request,
    type: Literal["text", "image"] = Form(...),
    content: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    x_device_id: str = Header(..., alias="X-Device-Id"),
):
    if not x_device_id.strip():
        raise HTTPException(status_code=400, detail="X-Device-Id header must not be empty")

    image_bytes: Optional[bytes] = None
    detected_image_type: Optional[str] = None

    if type == "text":
        if not content or not content.strip():
            raise HTTPException(status_code=400, detail="content is required for type=text")
    else:
        if image is None:
            raise HTTPException(status_code=400, detail="image file is required for type=image")
        image_bytes = await image.read(MAX_IMAGE_BYTES + 1)
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="image too large")
        detected_image_type = _sniff_image_type(image_bytes)
        if detected_image_type is None:
            raise HTTPException(
                status_code=400, detail=f"unsupported image type: {image.content_type}"
            )

    allowed = await check_and_increment(
        request.app.state.db_pool, x_device_id, settings.daily_request_cap, date.today()
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="daily request limit reached")

    client = request.app.state.groq_client
    try:
        if type == "text":
            answer = await ask_text(client, content.strip())
        else:
            answer = await ask_image(client, image_bytes, detected_image_type)
    except GroqAnswerError:
        raise HTTPException(status_code=502, detail="failed to get an answer")

    return {"answer": answer}
