import base64
import re

SYSTEM_PROMPT = (
    "Answer the user's question directly. Be extremely concise. "
    "Give only the answer and, when necessary, one short explanation "
    "(max 30-50 words total). Do not provide introductions, "
    "conclusions, or unnecessary details."
)

TEXT_MODEL = "openai/gpt-oss-20b"
VISION_MODEL = "qwen/qwen3.8-27b"

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class GroqAnswerError(Exception):
    """Raised when Groq fails to return a usable answer."""


async def ask_text(client, content: str) -> str:
    try:
        response = await client.chat.completions.create(
            model=TEXT_MODEL,
            temperature=0.2,
            include_reasoning=False,
            reasoning_effort="low",
            messages=[
                {"role": "user", "content": f"{SYSTEM_PROMPT}\n\n{content}"},
            ],
        )
    except Exception as exc:
        raise GroqAnswerError(f"Groq request failed: {exc}") from exc
    return _extract_answer(response)


async def ask_image(client, image_bytes: bytes, mime_type: str) -> str:
    b64_image = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{b64_image}"
    try:
        response = await client.chat.completions.create(
            model=VISION_MODEL,
            temperature=0.2,
            reasoning_format="hidden",
            reasoning_effort="low",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"{SYSTEM_PROMPT}\n\nAnswer the question shown in this image.",
                        },
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
    if answer:
        answer = _THINK_BLOCK_RE.sub("", answer).strip()
    if not answer:
        raise GroqAnswerError("Groq returned an empty answer")
    return answer
