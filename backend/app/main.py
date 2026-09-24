from datetime import date
from typing import Literal, Optional

from fastapi import FastAPI, Form, File, UploadFile, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from groq import Groq

from app.config import load_settings
from app.db import create_pool, check_and_increment
from app.groq_client import ask_text, ask_image, GroqAnswerError

settings = load_settings()
app = FastAPI()

MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"detail": exc.errors()})


@app.on_event("startup")
async def startup() -> None:
    app.state.db_pool = await create_pool(settings.database_url)
    app.state.groq_client = Groq(api_key=settings.groq_api_key, timeout=15.0)


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

    if type == "text":
        if not content or not content.strip():
            raise HTTPException(status_code=400, detail="content is required for type=text")
    else:
        if image is None:
            raise HTTPException(status_code=400, detail="image file is required for type=image")
        if image.content_type not in ALLOWED_IMAGE_TYPES:
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
            answer = ask_text(client, content.strip())
        else:
            image_bytes = await image.read()
            if len(image_bytes) > MAX_IMAGE_BYTES:
                raise HTTPException(status_code=413, detail="image too large")
            answer = ask_image(client, image_bytes, image.content_type)
    except GroqAnswerError:
        raise HTTPException(status_code=502, detail="failed to get an answer")

    return {"answer": answer}
