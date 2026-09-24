import asyncio
import time
from types import SimpleNamespace

import pytest

from app.groq_client import ask_text, ask_image, GroqAnswerError


class FakeGroqClient:
    def __init__(self, content, raise_exc=None, delay=0.0):
        self._content = content
        self._raise_exc = raise_exc
        self._delay = delay
        self.last_call = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.last_call = kwargs
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._raise_exc:
            raise self._raise_exc
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))]
        )


async def test_ask_text_returns_stripped_answer():
    client = FakeGroqClient(content="  B. Queue  ")
    answer = await ask_text(client, "Which data structure uses FIFO?")
    assert answer == "B. Queue"
    assert len(client.last_call["messages"]) == 1
    assert client.last_call["messages"][0]["role"] == "user"
    assert "Which data structure uses FIFO?" in client.last_call["messages"][0]["content"]
    assert client.last_call["include_reasoning"] is False


async def test_ask_text_strips_think_blocks_if_present():
    client = FakeGroqClient(content="<think>internal reasoning</think>B. Queue")
    answer = await ask_text(client, "Which data structure uses FIFO?")
    assert answer == "B. Queue"


async def test_ask_text_raises_on_empty_answer():
    client = FakeGroqClient(content="   ")
    with pytest.raises(GroqAnswerError):
        await ask_text(client, "What is polymorphism?")


async def test_ask_text_wraps_sdk_errors():
    client = FakeGroqClient(content=None, raise_exc=ConnectionError("boom"))
    with pytest.raises(GroqAnswerError):
        await ask_text(client, "What is polymorphism?")


async def test_ask_image_sends_data_url_and_returns_answer():
    client = FakeGroqClient(content="B. Paris")
    answer = await ask_image(client, b"fake-bytes", "image/jpeg")
    assert answer == "B. Paris"
    assert len(client.last_call["messages"]) == 1
    image_part = client.last_call["messages"][0]["content"][1]
    assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert client.last_call["reasoning_format"] == "hidden"


async def test_ask_image_raises_on_empty_answer():
    client = FakeGroqClient(content="")
    with pytest.raises(GroqAnswerError):
        await ask_image(client, b"fake-bytes", "image/jpeg")


async def test_ask_text_does_not_block_the_event_loop():
    client_a = FakeGroqClient(content="answer-a", delay=0.3)
    client_b = FakeGroqClient(content="answer-b", delay=0.3)

    start = time.monotonic()
    results = await asyncio.gather(
        ask_text(client_a, "question a"),
        ask_text(client_b, "question b"),
    )
    elapsed = time.monotonic() - start

    assert results == ["answer-a", "answer-b"]
    assert elapsed < 0.5, f"two concurrent 0.3s calls took {elapsed:.2f}s — event loop was blocked"
