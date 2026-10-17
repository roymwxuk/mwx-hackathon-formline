import asyncio

import pytest

from formline.agents import llm
from formline.agents.llm import (
    BudgetExceeded,
    CallBudget,
    FakeChatClient,
    LLMConfig,
    LLMRunner,
    ResponseCache,
    make_chat_client,
    make_runner,
)

FOUNDRY = LLMConfig(endpoint="https://example.services.ai.azure.com/api/projects/p",
                    deployment="small-model")


def run(coro):
    return asyncio.run(coro)


def test_factory_uses_the_fake_without_an_endpoint():
    client, kind = make_chat_client(LLMConfig())
    assert kind == "fake" and isinstance(client, FakeChatClient)


def test_factory_uses_foundry_when_configured():
    client, kind = make_chat_client(FOUNDRY)  # constructing needs no network
    assert kind == "foundry" and type(client).__name__ == "FoundryChatClient"


def test_foundry_auth_is_identity_based(monkeypatch):
    """No keys: DefaultAzureCredential covers az login locally and managed identity in Azure."""
    import azure.identity

    used = []

    class SpyCredential(azure.identity.DefaultAzureCredential):
        def __init__(self, *args, **kwargs):
            used.append(True)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(azure.identity, "DefaultAzureCredential", SpyCredential)
    make_chat_client(FOUNDRY)
    assert used == [True]


def test_runner_goes_through_agent_framework():
    runner = make_runner(LLMConfig(), fake_responder=lambda texts: f"reply to {texts[-1]}")
    assert run(runner.complete("narrator", "Be brief.", "ping")) == "reply to ping"
    assert runner.client.calls == [["ping"]]


def test_cache_makes_repeat_calls_free():
    runner = make_runner(LLMConfig(), fake_responder=lambda t: "x")
    run(runner.complete("narrator", "Be brief.", "ping"))
    run(runner.complete("narrator", "Be brief.", "ping"))
    assert len(runner.client.calls) == 1 and runner.cache_hits == 1
    run(runner.complete("narrator", "Be brief.", "ping", use_cache=False))
    assert len(runner.client.calls) == 2


def test_cache_key_depends_on_agent_instructions_and_input():
    keys = {ResponseCache.key("v1", "m", a, i, u)
            for a in ("narrator", "selector") for i in ("A", "B") for u in ("x", "y")}
    assert len(keys) == 8


def test_prompt_version_invalidates_the_cache(monkeypatch):
    runner = make_runner(LLMConfig(), fake_responder=lambda t: "x")
    run(runner.complete("narrator", "Be brief.", "ping"))
    monkeypatch.setattr(llm, "PROMPT_VERSION", "v2")
    run(runner.complete("narrator", "Be brief.", "ping"))
    assert len(runner.client.calls) == 2


def test_persistent_cache_survives_a_restart(tmp_path):
    path = tmp_path / "cache.jsonl"
    first = make_runner(LLMConfig(), fake_responder=lambda t: "answer", cache_path=path)
    run(first.complete("narrator", "Be brief.", "ping"))
    second = make_runner(LLMConfig(), fake_responder=lambda t: "different", cache_path=path)
    assert run(second.complete("narrator", "Be brief.", "ping")) == "answer"
    assert second.client.calls == []


def test_budget_stops_runaway_cost():
    client = FakeChatClient(lambda t: "x")
    runner = LLMRunner(client, "fake", LLMConfig(), budget=CallBudget(max_calls=2))
    run(runner.complete("a", "i", "1"))
    run(runner.complete("a", "i", "2"))
    with pytest.raises(BudgetExceeded):
        run(runner.complete("a", "i", "3"))
    run(runner.complete("a", "i", "1"))  # cached answers cost nothing


def test_smoke_cli_needs_an_endpoint(monkeypatch, capsys):
    monkeypatch.setattr(llm.settings, "azure_ai_project_endpoint", "")
    assert llm.main(["--smoke"]) == 1
    assert "AZURE_AI_PROJECT_ENDPOINT" in capsys.readouterr().out


def test_tests_never_reach_azure():
    """Guard: even with a real endpoint in backend/.env, tests run on the fake model."""
    from formline.agents.llm import LLMConfig

    assert not LLMConfig.from_settings().uses_foundry
    assert make_runner().kind == "fake"
