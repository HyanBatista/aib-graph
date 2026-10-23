from types import SimpleNamespace

import pytest

from llm.client import FakeLLM, GeminiLLM, LLMError, get_llm
from llm.schemas import GradeDraft, QuestionRouting


class FakeModels:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def generate_content(self, model, contents, config):
        self.calls.append((model, contents, config))
        if self.error:
            raise self.error
        return self.response


class FakeFiles:
    def __init__(self, states):
        self.states = list(states)

    def upload(self, file, config):
        return SimpleNamespace(name="files/1", uri="https://files/1", state=self.states.pop(0))

    def get(self, name):
        return SimpleNamespace(name=name, uri="https://files/1", state=self.states.pop(0))


def gemini_with(models=None, files=None):
    llm = object.__new__(GeminiLLM)
    llm._client = SimpleNamespace(models=models, files=files)
    llm.model_pro, llm.model_flash = "pro", "flash"
    return llm


def test_gemini_uses_structured_output_and_flash_for_routing():
    parsed = QuestionRouting(answer_md="ok", target_topic_id=3)
    models = FakeModels(SimpleNamespace(parsed=parsed, text=""))
    result = gemini_with(models).route_question("q?", {"title": "T"}, [], "excerpt", "en")
    assert result == parsed
    model, _, config = models.calls[0]
    assert model == "flash"
    assert config.response_mime_type == "application/json"
    assert config.response_schema is QuestionRouting


def test_gemini_falls_back_to_parsing_text():
    models = FakeModels(SimpleNamespace(parsed=None, text='{"score": 0.5, "feedback": "half"}'))
    assert gemini_with(models).grade_open("p", "r", "a", "en") == GradeDraft(score=0.5, feedback="half")


def test_gemini_errors_become_llm_errors():
    with pytest.raises(LLMError):
        gemini_with(FakeModels(error=RuntimeError("quota"))).grade_open("p", "r", "a", "en")
    with pytest.raises(LLMError):
        gemini_with(FakeModels(SimpleNamespace(parsed=None, text="not json"))).grade_open("p", "r", "a", "en")


def test_upload_waits_until_active(monkeypatch):
    monkeypatch.setattr("llm.client.time.sleep", lambda s: None)
    llm = gemini_with(files=FakeFiles(["PROCESSING", "PROCESSING", "ACTIVE"]))
    assert llm.upload_pdf("book.pdf") == "https://files/1"
    with pytest.raises(LLMError):
        gemini_with(files=FakeFiles(["PROCESSING", "FAILED"])).upload_pdf("book.pdf")


def test_provider_selection(settings):
    settings.LLM_PROVIDER = "fake"
    assert isinstance(get_llm(), FakeLLM)
    settings.LLM_PROVIDER, settings.GEMINI_API_KEY = "gemini", ""
    with pytest.raises(LLMError):
        get_llm()
