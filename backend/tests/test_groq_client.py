from types import SimpleNamespace

import pytest

from app.groq_client import ask_text, ask_image, GroqAnswerError


class FakeGroqClient:
    def __init__(self, content, raise_exc=None):
        self._content = content
        self._raise_exc = raise_exc
        self.last_call = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.last_call = kwargs
        if self._raise_exc:
            raise self._raise_exc
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))]
        )


def test_ask_text_returns_stripped_answer():
    client = FakeGroqClient(content="  B. Queue  ")
    answer = ask_text(client, "Which data structure uses FIFO?")
    assert answer == "B. Queue"
    assert client.last_call["messages"][1]["content"] == "Which data structure uses FIFO?"


def test_ask_text_raises_on_empty_answer():
    client = FakeGroqClient(content="   ")
    with pytest.raises(GroqAnswerError):
        ask_text(client, "What is polymorphism?")


def test_ask_text_wraps_sdk_errors():
    client = FakeGroqClient(content=None, raise_exc=ConnectionError("boom"))
    with pytest.raises(GroqAnswerError):
        ask_text(client, "What is polymorphism?")


def test_ask_image_sends_data_url_and_returns_answer():
    client = FakeGroqClient(content="B. Paris")
    answer = ask_image(client, b"fake-bytes", "image/jpeg")
    assert answer == "B. Paris"
    image_part = client.last_call["messages"][1]["content"][1]
    assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_ask_image_raises_on_empty_answer():
    client = FakeGroqClient(content="")
    with pytest.raises(GroqAnswerError):
        ask_image(client, b"fake-bytes", "image/jpeg")
