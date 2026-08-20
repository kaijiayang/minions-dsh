"""Unit tests for the unified OpenAI-compatible client.

The HTTP layer is mocked, so no local server is required to run these tests.
"""

import pytest
import requests

from minions.clients.openai_compat import (
    PLATFORM_PRESETS,
    SUPPORTED_PLATFORMS,
    OpenAICompatClient,
    resolve_platform,
)


# ---------------------------------------------------------------------------
# Platform resolution
# ---------------------------------------------------------------------------


def test_platform_presets_present():
    for name in ("lmstudio", "ollama", "vllm", "llamacpp"):
        assert name in PLATFORM_PRESETS
        assert PLATFORM_PRESETS[name].base_url
    # generic requires an explicit base_url
    assert "generic" in PLATFORM_PRESETS
    assert not PLATFORM_PRESETS["generic"].base_url


def test_resolve_platform_presets():
    assert resolve_platform("lmstudio")[0] == "http://127.0.0.1:1234/v1"
    assert resolve_platform("ollama")[0] == "http://127.0.0.1:11434/v1"
    assert resolve_platform("vllm")[0] == "http://127.0.0.1:8000/v1"
    assert resolve_platform("llamacpp")[0] == "http://127.0.0.1:8080/v1"


def test_resolve_platform_explicit_base_url_wins():
    base, key = resolve_platform("ollama", base_url="http://127.0.0.1:9999/v1", api_key="k")
    assert base == "http://127.0.0.1:9999/v1"
    assert key == "k"


def test_resolve_platform_auto_defaults_to_lmstudio():
    base, _ = resolve_platform("auto")
    assert base == "http://127.0.0.1:1234/v1"


def test_resolve_platform_unknown():
    with pytest.raises(ValueError, match="Unknown local platform"):
        resolve_platform("bogus")


# ---------------------------------------------------------------------------
# Client construction (mocked health check)
# ---------------------------------------------------------------------------


class _FakeChatCompletions:
    def __init__(self, response):
        self._response = response

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return self._response


class _FakeChat:
    def __init__(self, response):
        self.completions = _FakeChatCompletions(response)


class _FakeModels:
    def __init__(self):
        class _Model:
            def __init__(self, id_):
                self.id = id_
                self.object = "model"

            def model_dump(self):
                return {"id": self.id, "object": self.object}

        self._items = [_Model("m")]

    def list(self):
        class _Page:
            data = self._items

        return _Page()


class _FakeOpenAI:
    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key
        self.base_url = base_url
        self.chat = _FakeChat(None)
        self.models = _FakeModels()


class _FakeUsage:
    prompt_tokens = 11
    completion_tokens = 7


class _FakeChoice:
    def __init__(self):
        class M:
            content = "hello"

        self.message = M()
        self.finish_reason = "stop"


class _FakeResponse:
    usage = _FakeUsage()
    choices = [_FakeChoice()]


def _make_client(monkeypatch, **kwargs):
    """Build a client with a fake openai SDK and a stubbed health check."""
    fake = _FakeOpenAI()
    model_name = kwargs.pop("model_name", "qwen3-8b")

    def fake_init(api_key=None, base_url=None):
        return fake

    monkeypatch.setattr("openai.OpenAI", fake_init)
    monkeypatch.setattr("requests.get", lambda url, timeout=10: _FakeGet(200))
    return OpenAICompatClient(model_name=model_name, verify_server=True, **kwargs)


class _FakeGet:
    def __init__(self, status):
        self._status = status

    def raise_for_status(self):
        if self._status >= 400:
            raise RuntimeError(f"HTTP {self._status}")

    def json(self):
        return {"object": "list", "data": []}


def test_client_platform_defaults(monkeypatch):
    monkeypatch.setattr("openai.OpenAI", lambda api_key=None, base_url=None: None)
    monkeypatch.setattr("requests.get", lambda url, timeout=10: _FakeGet(200))
    client = OpenAICompatClient(model_name="m", platform="ollama")
    assert client.base_url == "http://127.0.0.1:11434/v1"
    assert client.api_key == "ollama"


def test_client_explicit_base_url(monkeypatch):
    monkeypatch.setattr("openai.OpenAI", lambda api_key=None, base_url=None: None)
    monkeypatch.setattr("requests.get", lambda url, timeout=10: _FakeGet(200))
    client = OpenAICompatClient(
        model_name="m", base_url="http://127.0.0.1:8080/v1", api_key="k"
    )
    assert client.base_url == "http://127.0.0.1:8080/v1"
    assert client.api_key == "k"


def test_client_health_check_failure(monkeypatch):
    monkeypatch.setattr("openai.OpenAI", lambda api_key=None, base_url=None: None)

    def boom(url, timeout=10):
        raise requests.exceptions.ConnectionError("connection refused")

    monkeypatch.setattr("requests.get", boom)
    with pytest.raises(RuntimeError, match="not running or reachable"):
        OpenAICompatClient(model_name="m", platform="lmstudio")


def test_client_chat(monkeypatch):
    client = _make_client(monkeypatch, model_name="qwen3-8b", platform="lmstudio")
    client.client.chat = _FakeChat(_FakeResponse())

    responses, usage, reasons = client.chat(
        [{"role": "user", "content": "hi"}], max_tokens=64
    )
    assert responses == ["hello"]
    assert reasons == ["stop"]
    assert usage.prompt_tokens == 11
    assert usage.completion_tokens == 7

    last = client.client.chat.completions.last_kwargs
    assert last["model"] == "qwen3-8b"
    assert last["max_tokens"] == 64  # local servers expect max_tokens


def test_list_models(monkeypatch):
    client = _make_client(monkeypatch, model_name="m", platform="ollama")
    out = client.list_models()
    assert out["data"][0]["id"] == "m"
