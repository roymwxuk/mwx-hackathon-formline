# Why a newer model can perform worse in Formline

Recorded 2026-10-22 from Codex's explanation to the owner. Based on the model-comparison plan, results, scores and metrics at commit `21f6c5d`, plus Claude's Luna notes. This records that comparison, not subsequent experiments.

A newer model can have stronger capabilities overall and still perform worse inside a particular application. Your comparison tested **how well each model works in Formline's existing pipeline and configuration**, rather than which model is universally better.

The results show trade-offs:

| Measure | gpt-4.1-mini | Luna |
|---|---:|---:|
| Overall success, two runs | 80/90, 84/90 | 81/90, 81/90 |
| Relevant answers to 61 answerable questions | 58, 60 | 57, 57 |
| Behaviour cases scored wrong | 3, 2 | 1, 1 |
| Median latency | 5.3–5.5 s | 6.9–7.1 s |
| p90 latency | 9.1–9.8 s | 12.0–14.0 s |

Luna made fewer outright mistakes on the behaviour tests, but answered fewer supported questions successfully and took longer.

## 1. The same output limit may affect the models differently

Formline gives each model call a 400-token output allowance. According to Claude's notes, Luna uses that allowance for both internal reasoning and the visible response.

That creates a possible failure chain:

1. The model spends much of its allowance reasoning.
2. It has too little room left to finish the required JSON.
3. The application cannot parse the response.
4. The pipeline retries, uses the Router fallback, or returns a generic decline.
5. The user receives an incomplete or irrelevant response, even if the model was heading toward the correct answer.

The reports identify 15 empty or malformed Luna replies. This supports investigating the output budget, but **does not conclusively prove token exhaustion caused all 15**: per-call token usage and finish reasons were not logged.

So the configuration comparison is useful, but limited. It tells you whether Luna is a good replacement under the current settings. It does not establish Luna's best achievable performance after tuning.

## 2. More caution can improve safety while reducing usefulness

One important Luna improvement involved an invented Japanese player name.

- 4.1-mini assigned Okafor's statistics to the nonexistent player in both runs.
- Luna declined in both runs.

That is a meaningful improvement: declining is preferable to inventing an identity.

However, Luna also declined some questions where part of the requested information was available. For example, if goals are available but minutes played are missing, the desired response is to provide the goals and explain that minutes are unavailable.

A generic refusal avoids fabrication but fails to deliver the supported part. That explains how Luna could have **fewer wrong behaviour outcomes while also having fewer relevant answers**.

## 3. Better reasoning does not guarantee faithful wording

Luna improved some questions that required connecting information across lookups. The report highlights a case where it retrieved the player's own last game rather than substituting the club's last game.

But retrieving the right facts and describing them correctly are separate tasks.

In `v04`, Luna described Okafor's 10 goals as being from "last season," although the facts described the current season. This happened in both Luna runs.

The number and player were correct, but the time frame was wrong. That is still a factual error. Stronger reasoning does not automatically prevent mistakes in relationships such as:

- Which player owns a statistic.
- Which season a statistic covers.
- Whether a statement refers to tonight or historical matches.
- Whether a headline agrees with the body.

Those relationships also expose the limits of a verifier that mainly checks recognized numbers, names and phrases.

## 4. Formline rewards several abilities at once

To succeed, the model must do more than understand football questions. It must:

- Choose appropriate tools and chain lookups.
- Stay within call and time limits.
- Return valid JSON.
- Keep the headline and body short.
- Preserve player, club and time-frame relationships.
- Respond in the requested language.
- Avoid unsupported claims.
- Pass the application's verifier.

A model can improve tool selection while becoming less reliable at finishing JSON within the budget. It can write more cautiously while refusing too often. It can retrieve correct facts but introduce a wrong phrase while summarizing them.

The application's result depends on the whole chain. An improvement at one step can be outweighed by failures elsewhere.

## 5. The decision to keep 4.1-mini was based on requirements, not novelty

Luna's overall average was 81/90, compared with 82/90 for 4.1-mini. With only two runs each, that small difference alone would be weak evidence for a broad claim that one model is better.

The stronger reason to keep 4.1-mini is that Luna failed requirements written before its evaluation:

- It introduced a new false claim on a case the baseline passed twice.
- Its mean p90 latency exceeded the 12-second threshold.
- The reports identified incomplete responses.

For a live viewer, reliable answers and predictable latency matter. A newer model is worth adopting when its measured benefits justify its costs and failure modes.

The defensible conclusion is: **Luna showed useful gains in some reasoning and refusal cases, but it was not a better replacement under Formline's tested configuration.** Logging token usage and finish reasons, then evaluating a larger output budget or a different reasoning setting, would show whether the main losses are configuration problems.

I verified that the score totals match the saved scoring file. Claude performed the answer-quality scoring; I have not independently rescored every response.
