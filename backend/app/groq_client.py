import base64

SYSTEM_PROMPT = (
    "Answer the user's question directly. Be extremely concise. "
    "Give only the answer and, when necessary, one short explanation "
    "(max 30-50 words total). Do not provide introductions, "
    "conclusions, or unnecessary details."
)

TEXT_MODEL = "llama-3.1-8b-instant"
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


class GroqAnswerError(Exception):
    """Raised when Groq fails to return a usable answer."""


def ask_text(client, content: str) -> str:
    try:
        response = client.chat.completions.create(
            model=TEXT_MODEL,
            temperature=0.2,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
        )
    except Exception as exc:
        raise GroqAnswerError(f"Groq request failed: {exc}") from exc
    return _extract_answer(response)


def ask_image(client, image_bytes: bytes, mime_type: str) -> str:
    b64_image = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{b64_image}"
    try:
        response = client.chat.completions.create(
            model=VISION_MODEL,
            temperature=0.2,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Answer the question shown in this image."},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        )
    except Exception as exc:
        raise GroqAnswerError(f"Groq request failed: {exc}") from exc
    return _extract_answer(response)


def _extract_answer(response) -> str:
    answer = response.choices[0].message.content
    if not answer or not answer.strip():
        raise GroqAnswerError("Groq returned an empty answer")
    return answer.strip()
