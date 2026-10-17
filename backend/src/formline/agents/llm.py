"""LLM access for the agents: one code path for Microsoft Foundry and a fake client.

- `make_chat_client()` returns Agent Framework's `FoundryChatClient` when a Foundry
  project endpoint is configured, otherwise a `FakeChatClient`. Tests and CI always
  use the fake, so nothing here needs Azure to run.
- `LLMRunner.complete()` is what every agent calls: response cache → call budget →
  `Agent(client, instructions).run(...)`. The cache makes reruns free (and the demo
  reproducible); the budget caps cost per run.

Auth is identity-based (`DefaultAzureCredential`): your `az login` locally, the app's
managed identity in Azure Container Apps. No API keys anywhere.

Manual smoke test against Foundry (needs the deployment and `az login`):
    uv run python -m formline.agents.llm --smoke
"""

import argparse
import hashlib
import json
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_framework import Agent, BaseChatClient, ChatResponse, Message

from formline.config import settings

PROMPT_VERSION = "v2"  # v2: viewer-ready card facts, examples, name in headline  # bump when prompts change, so cached answers are not reused


# ---------- fake client ----------

Responder = Callable[[list[str]], str]  # message texts in -> reply text out


class FakeChatClient(BaseChatClient):
    """A chat client that answers from a Python function instead of a model.

    Used for tests, CI and offline runs. `calls` records every request so tests can
    assert how many model calls happened.
    """

    def __init__(self, responder: Responder, **kwargs: Any):
        super().__init__(**kwargs)
        self.responder = responder
        self.calls: list[list[str]] = []

    def _inner_get_response(self, *, messages: Sequence[Message], stream: bool,
                            options: dict, **kwargs: Any) -> Awaitable[ChatResponse]:
        if stream:
            raise NotImplementedError("FakeChatClient does not stream")
        texts = [m.text for m in messages]
        self.calls.append(texts)

        async def respond() -> ChatResponse:
            return ChatResponse(messages=[Message("assistant", [self.responder(texts)])],
                                model="fake")
        return respond()


def echo_responder(texts: list[str]) -> str:
    return texts[-1] if texts else ""


# ---------- client factory ----------

@dataclass(frozen=True)
class LLMConfig:
    endpoint: str = ""
    deployment: str = ""
    temperature: float = 0.2
    max_tokens: int = 400
    max_calls: int = 600  # per run: the live match needs ~22 insights × 4 variants + retries

    @classmethod
    def from_settings(cls) -> "LLMConfig":
        return cls(endpoint=settings.azure_ai_project_endpoint,
                   deployment=settings.azure_ai_model_deployment_name)

    @property
    def uses_foundry(self) -> bool:
        return bool(self.endpoint)


def make_chat_client(config: LLMConfig, fake_responder: Responder = echo_responder):
    """Foundry when configured, otherwise the fake. Returns (client, kind)."""
    if config.uses_foundry:
        from agent_framework.foundry import FoundryChatClient
        from azure.identity import DefaultAzureCredential

        # az login locally, managed identity in Azure: the same code, no keys.
        client = FoundryChatClient(project_endpoint=config.endpoint, model=config.deployment,
                                   credential=DefaultAzureCredential())
        return client, "foundry"
    return FakeChatClient(fake_responder), "fake"


# ---------- cost guard ----------

class BudgetExceeded(RuntimeError):
    pass


@dataclass
class CallBudget:
    max_calls: int
    calls: int = 0

    def spend(self) -> None:
        if self.calls >= self.max_calls:
            raise BudgetExceeded(f"LLM call budget of {self.max_calls} reached")
        self.calls += 1


class ResponseCache:
    """Answers keyed by (prompt version, model, agent, instructions, input).

    In memory, optionally persisted as JSON lines (under the gitignored data dir).
    """

    def __init__(self, path: Path | None = None):
        self.path = path
        self._data: dict[str, str] = {}
        if path and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self._data[row["key"]] = row["text"]

    @staticmethod
    def key(*parts: str) -> str:
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def put(self, key: str, text: str) -> None:
        self._data[key] = text
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"key": key, "text": text}, ensure_ascii=False) + "\n")

    def __len__(self) -> int:
        return len(self._data)


# ---------- runner ----------

@dataclass
class LLMRunner:
    client: Any
    kind: str  # "foundry" or "fake"
    config: LLMConfig = field(default_factory=LLMConfig)
    cache: ResponseCache = field(default_factory=ResponseCache)
    budget: CallBudget | None = None
    cache_hits: int = 0

    def __post_init__(self) -> None:
        if self.budget is None:
            self.budget = CallBudget(self.config.max_calls)

    async def complete(self, agent_name: str, instructions: str, user_input: str,
                       use_cache: bool = True) -> str:
        """One model turn for one agent. Retries pass use_cache=False with new input."""
        model = self.config.deployment if self.kind == "foundry" else "fake"
        key = ResponseCache.key(PROMPT_VERSION, model, agent_name, instructions, user_input)
        if use_cache and (hit := self.cache.get(key)) is not None:
            self.cache_hits += 1
            return hit
        self.budget.spend()
        agent = Agent(self.client, instructions, name=agent_name)
        response = await agent.run(user_input, options={
            "temperature": self.config.temperature, "max_tokens": self.config.max_tokens})
        text = response.text
        self.cache.put(key, text)
        return text


def make_runner(config: LLMConfig | None = None, fake_responder: Responder = echo_responder,
                cache_path: Path | None = None) -> LLMRunner:
    config = config or LLMConfig.from_settings()
    client, kind = make_chat_client(config, fake_responder)
    return LLMRunner(client, kind, config, ResponseCache(cache_path))


def main(argv: list[str] | None = None) -> int:
    import asyncio

    parser = argparse.ArgumentParser(prog="python -m formline.agents.llm")
    parser.add_argument("--smoke", action="store_true", help="one real call to Foundry")
    args = parser.parse_args(argv)
    if not args.smoke:
        parser.print_help()
        return 0
    config = LLMConfig.from_settings()
    if not config.uses_foundry:
        print("AZURE_AI_PROJECT_ENDPOINT is not set; see backend/.env.example")
        return 1
    runner = make_runner(config)
    text = asyncio.run(runner.complete(
        "smoke", 'Reply with JSON only: {"ok": true, "model": "<your model name>"}', "ping",
        use_cache=False))
    print(text)
    try:
        json.loads(text)
    except json.JSONDecodeError:
        print("Reply was not valid JSON")
        return 1
    print(f"OK: Foundry deployment {config.deployment!r} answered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
