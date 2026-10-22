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
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_framework import Agent, BaseChatClient, ChatResponse, Content, Message
from agent_framework._tools import FunctionInvocationLayer

from formline.config import settings

PROMPT_VERSION = "v3"  # v3: comparison vs shot details kept apart, shorter casual subs  # bump when prompts change, so cached answers are not reused


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


# ---------- tool-using agents (the Researcher) ----------

# The current research run's per-round-trip hook (request-local through asyncio's context):
# every model round-trip of a tool loop, including the framework's final no-tools call,
# is charged here before it is sent.
ON_MODEL_CALL: ContextVar[Callable[[], None] | None] = ContextVar("on_model_call", default=None)

# What a scripted fake sees of the conversation: (role, kind, text) per content, where kind is
# "text" or "function_result"; it replies with tool calls [(name, args)] or a final text.
ToolScript = Callable[[int, list[tuple[str, str, str]]], "list[tuple[str, dict]] | str"]

# Fixed tool-loop settings for the research client; our own request-local counter enforces
# the real limits (the framework's max_function_calls is checked only after a batch).
TOOL_LOOP = {"max_iterations": 6, "allow_concurrent_invocation": False,
             "max_consecutive_errors_per_request": 3}


def _charge_model_call() -> None:
    hook = ON_MODEL_CALL.get()
    if hook is not None:
        hook()


class FakeToolChatClient(FunctionInvocationLayer, BaseChatClient):
    """A scripted chat client that can call tools, so tests run the real framework tool loop
    offline. `script(turn, seen)` returns tool calls or the final text; `turn` counts this
    run's round-trips (from the conversation, so one client serves many runs)."""

    def __init__(self, script: ToolScript, **kwargs: Any):
        super().__init__(**kwargs)
        self.script = script
        self.turns = 0

    def _inner_get_response(self, *, messages: Sequence[Message], stream: bool,
                            options: dict, **kwargs: Any) -> Awaitable[ChatResponse]:
        if stream:
            raise NotImplementedError("FakeToolChatClient does not stream")
        _charge_model_call()
        self.turns += 1  # all runs, for tests that count round-trips
        turn = 1 + sum(m.role == "assistant" for m in messages)  # this run's turn
        seen = [(m.role, c.type, str(c.result) if c.type == "function_result" else (c.text or ""))
                for m in messages for c in m.contents if c.type in ("text", "function_result")]
        reply = self.script(turn, seen)

        async def respond() -> ChatResponse:
            if isinstance(reply, list):
                calls = [Content.from_function_call(f"call_{self.turns}_{i}", name, arguments=args)
                         for i, (name, args) in enumerate(reply)]
                return ChatResponse(messages=[Message("assistant", calls)], model="fake")
            return ChatResponse(messages=[Message("assistant", [reply])], model="fake")
        return respond()


def _scripted_done(turn: int, seen: list[tuple[str, str, str]]) -> str:
    return '{"cannot_answer": true}'


# ---------- client factory ----------

# Reasoning model families: they reject `temperature` (a 400), and their hidden reasoning
# counts against the output limit, so they get more room (docs/eval/gpt-6-luna-notes.md).
REASONING = ("gpt-5", "gpt-6")
REASONING_MAX_TOKENS = 1000


@dataclass(frozen=True)
class LLMConfig:
    endpoint: str = ""
    deployment: str = ""
    temperature: float | None = 0.2  # None: not sent
    max_tokens: int = 400
    max_calls: int = 600  # per run: the live match needs ~22 insights × 4 variants + retries

    @classmethod
    def from_settings(cls) -> "LLMConfig":
        deployment = settings.azure_ai_model_deployment_name
        if deployment.startswith(REASONING):
            return cls(endpoint=settings.azure_ai_project_endpoint, deployment=deployment,
                       temperature=None, max_tokens=REASONING_MAX_TOKENS)
        return cls(endpoint=settings.azure_ai_project_endpoint, deployment=deployment)

    @property
    def options(self) -> dict:
        opts: dict = {"max_tokens": self.max_tokens}
        if self.temperature is not None:
            opts["temperature"] = self.temperature
        return opts

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


def make_tool_client(config: LLMConfig, script: ToolScript | None = None):
    """A chat client for tool-using agents, with fixed loop settings. Foundry when
    configured; otherwise a scripted fake. Each model round-trip is charged first."""
    if config.uses_foundry:
        from agent_framework.foundry import FoundryChatClient
        from azure.identity import DefaultAzureCredential

        class CountingFoundryChatClient(FoundryChatClient):
            def _inner_get_response(self, **kwargs: Any):
                _charge_model_call()
                return super()._inner_get_response(**kwargs)

        client = CountingFoundryChatClient(project_endpoint=config.endpoint,
                                           model=config.deployment,
                                           credential=DefaultAzureCredential())
    else:
        client = FakeToolChatClient(script or _scripted_done)
    client.function_invocation_configuration.update(TOOL_LOOP)
    return client


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
    tool_client: Any = None  # for tool-using agents (make_tool_client), created on first use
    tool_script: ToolScript | None = None  # the fake's research script
    usage: list[dict] = field(default_factory=list)  # one entry per uncached agent run

    def _record(self, agent_name: str, response) -> None:
        """Token counts and why the model stopped ("length": cut off by max_tokens)."""
        u = getattr(response, "usage_details", None) or {}
        reason = getattr(response, "finish_reason", None)
        self.usage.append({"agent": agent_name,
                           "input": u.get("input_token_count") or 0,
                           "output": u.get("output_token_count") or 0,
                           "reasoning": u.get("reasoning_output_token_count") or 0,
                           "finish": str(getattr(reason, "value", reason)) if reason else None})

    def __post_init__(self) -> None:
        if self.budget is None:
            self.budget = CallBudget(self.config.max_calls)

    @property
    def remaining(self) -> int:
        return self.budget.max_calls - self.budget.calls

    async def research(self, agent_name: str, instructions: str, user_input: str,
                       tools: list, max_model_calls: int) -> str:
        """One tool-using agent run: the model calls `tools` (each guards its own limits)
        and replies. Every round-trip is charged to the shared budget and to this run's
        allowance first; over either, BudgetExceeded is raised and the run stops. Not cached:
        a tool loop depends on what the tools return."""
        if self.tool_client is None:
            self.tool_client = make_tool_client(self.config, self.tool_script)
        used = 0

        def charge() -> None:
            nonlocal used
            if used >= max_model_calls:
                raise BudgetExceeded(f"research allowance of {max_model_calls} model calls reached")
            self.budget.spend()
            used += 1
        token = ON_MODEL_CALL.set(charge)
        try:
            agent = Agent(self.tool_client, instructions, name=agent_name, tools=tools)
            response = await agent.run(user_input, options=self.config.options)
            self._record(agent_name, response)
            return response.text
        finally:
            ON_MODEL_CALL.reset(token)

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
        response = await agent.run(user_input, options=self.config.options)
        self._record(agent_name, response)
        text = response.text
        self.cache.put(key, text)
        return text


def make_runner(config: LLMConfig | None = None, fake_responder: Responder = echo_responder,
                cache_path: Path | None = None) -> LLMRunner:
    config = config or LLMConfig.from_settings()
    client, kind = make_chat_client(config, fake_responder)
    return LLMRunner(client, kind, config, ResponseCache(cache_path),
                     tool_script=getattr(fake_responder, "research", None))


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
