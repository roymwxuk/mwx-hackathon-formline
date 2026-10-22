# Notes: gpt-6-luna, the output-token limit and hidden reasoning (2026-10-22)

Background for the model comparison. Results: [model-comparison-results.md](model-comparison-results.md);
method and criteria: [model-comparison-plan.md](model-comparison-plan.md).

## What happened

Two complete runs of the 90 typed questions on `gpt-6-luna` (deployed alongside `gpt-4.1-mini`
in the Foundry project `formline-ai-mwx`, GlobalStandard, 50K TPM) scored **81 / 90** in both
runs, against 80 and 84 for `gpt-4.1-mini`. Luna failed two of the five criteria set in advance:
a new false claim (v04: Okafor's 10 goals "last season") and truncated replies. The live app
stays on `gpt-4.1-mini`.

Two code changes were needed just to call Luna:

- It rejects `temperature` (400 "Unsupported parameter"). The client now sends no temperature
  to GPT-5 / GPT-6 deployments (`46bf538`, `NO_TEMPERATURE` in `agents/llm.py`).
- Nothing else; the same prompts, tools and limits were used.

## The 400-token limit is an output limit

- `LLMConfig.max_tokens = 400` (`backend/src/formline/agents/llm.py`) is sent with every model
  call (Researcher, Router, Analyst) as `options={"max_tokens": 400}`.
- The Microsoft Agent Framework's `FoundryChatClient` uses the Azure OpenAI **Responses API** and
  translates it to **`max_output_tokens`** (`agent_framework_openai/_chat_client.py`).
- Azure enforces it on the server. When it is hit, the response is marked incomplete
  (`incomplete_details.reason = "max_output_tokens"`) and the framework reports finish reason
  **`length`**. We do not log the finish reason yet.
- It does **not** limit the input. The input stays small by other means: the viewer's question is
  cut at 200 characters (`MAX_TEXT`), facts come only from the sections looked up, and the
  Researcher makes at most 5 tool calls.
- It is a ceiling, not a target: billing counts the tokens actually generated.

## Why Luna was cut off and gpt-4.1-mini was not

- `gpt-4.1-mini` is a non-reasoning model: every output token is the visible answer. Our answers
  are short JSON (headline ≤ 70 characters, body ≤ 260), roughly 60–150 tokens, so 400 is plenty.
  It never truncated.
- `gpt-6-luna` is a reasoning model. It produces hidden reasoning tokens before the answer, and
  they count against `max_output_tokens`. At its default effort (`medium`) the reasoning
  sometimes used most or all of the 400, leaving an empty or cut-off answer.
- Evidence: 15 of Luna's raw replies in the response cache were not valid JSON, many of them
  empty. The Researcher's reply became "malformed" and the question fell through to the generic
  decline. Japanese, which needs more tokens, was hit hardest (j06, a37_08, a37_09).
- Reasoning tokens are billed as output, so Luna's real cost per answer is higher than the list
  price ratio (about $0.10 / $0.50 per 1M tokens against about $0.40 / $1.60 for `gpt-4.1-mini`)
  suggests.

## Hidden reasoning can be lowered or turned off

GPT-6 Luna takes a `reasoning.effort` parameter: `none`, `low`, `medium` (default), `high`,
`xhigh`, `max`. `minimal` is rejected. OpenAI documents `none` for Luna; third-party reports on
Azure deployments conflict, so one smoke call would have to confirm it on ours. Our code does not
send the parameter yet.

What turning it off (`none`) would likely change, not yet measured:

| Likely better | At risk (may have come from the reasoning) | Probably unchanged |
|---|---|---|
| No truncation: the 400 tokens go to the answer | m01: the only model that chained to the player's own last game | Name clarification, the verifier, length limits (code) |
| Faster, closer to gpt-4.1-mini's latency | Overturned-goal premises corrected (var04, d02, var01 / var02) | Injection resistance (mostly prompt and code) |
| Cheaper: no reasoning tokens billed | unknown03 declined instead of inventing an identity | |

In short: turning reasoning off trades care for speed and room. Only a measured run can show
whether our tasks (pick lookups, summarise facts) need the care.

## Options for a second try (none run yet)

| Option | Tests | Keeps Luna's reasoning wins? |
|---|---|---|
| A. `max_tokens` 1,000 for GPT-6, default effort | whether truncation alone explains the losses | yes, likely |
| B. `reasoning.effort: none`, `max_tokens` 400 | whether Luna without reasoning is good enough | unknown |
| C. Log token usage and finish reason per call | the real reasoning size, truncation counts, real cost | (measurement, any model) |

Doing C first makes A or B measurable: the run would report how many reasoning tokens Luna
actually uses and whether any call still ends with `length`.

**Done (2026-10-22): A with C.** 1,000 output tokens for GPT-5 / GPT-6 and per-call token
logging (`b92b51c`). Measured: about 13,000 reasoning tokens per 90-question run, at most 935 in
one call; cut-offs fell from 15 to 1 and 0. Score 82 / 90 twice, but the verdict stands (new
"last season" claims, p90 13–15 s). Remaining Luna issues are not about tokens: empty final
replies from the Researcher's tool loop, and declining whole questions when one part is
unsupported. Details: [model-comparison-results.md](model-comparison-results.md). B
(`effort: none`) is still untested.

## Sources

- [GPT-6 Luna model page (OpenAI)](https://developers.openai.com/api/docs/models/gpt-6-luna)
- [Using GPT-6 (OpenAI)](https://developers.openai.com/api/docs/guides/latest-model)
- [Azure OpenAI reasoning models (Microsoft Learn)](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning)
- [GPT-6 Astra, Sol, and Luna in Microsoft Foundry (Azure blog)](https://azure.microsoft.com/en-us/blog/gpt-6-astra-sol-and-luna-for-production-agents-in-microsoft-foundry/)
- [GPT-6 Luna Azure pricing (azurespeed)](https://www.azurespeed.com/AzureAiModelPricing/Models/openai-gpt-6-luna)
- [Hermes Agent issue #120263](https://github.com/NousResearch/hermes-agent/issues/120263),
  [Zoo-Code issue #2040](https://github.com/Zoo-Code-Org/Zoo-Code/issues/2040),
  [Liedertafel issue #122](https://github.com/JakobFerdinand/liedertafel/issues/122): conflicting
  reports on `effort: none` with Azure deployments
