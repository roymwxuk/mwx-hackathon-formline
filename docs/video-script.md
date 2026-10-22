# Demo video: script and shot list (draft)

Target **1:55** (limit 2:00). Built on the moments in [video-plan.md](video-plan.md). Recorded
against the Azure deployment; synthetic data only, no real clubs, players, logos or music
(silence or a royalty-free bed you made or licensed). Voiceover about 270 words, read at a calm
pace (about 145 words a minute); captions repeat the key line of each scene.

Viewer: https://formline-web.bravestone-2a024c10.japaneast.azurecontainerapps.io
Jump to a moment with `?t=mm:ss`; open the two-viewer page with `?view=two`.

## Shot list

| Time | Scene | On screen | Voiceover | Caption |
|---|---|---|---|---|
| 0:00–0:08 | Title | "Formline: personal baselines for live football" over the 2D pitch | "Baseball compares every pitch with the pitcher's own norm. Formline does that for football, live." | Personal baselines, live |
| 0:08–0:26 | Moment 1, 12:05 | Live viewer, EN casual, **focus Reyner**. The card "101 km/h, about 13 km/h above his norm (estimate)" appears; the focus strip updates | "Reyner shoots at 101 kilometres an hour. The card compares it with his own shots: about 13 above his norm, an estimate from his history, shrunk toward his position group when his sample is small." | Compared with his own history |
| 0:26–0:40 | Moment 2, 40:12 | Settings: **my metric** all → shot speed. The placement card is replaced by "84 km/h vs 92" | "Personalisation changes *which* insight you see, not just the wording. Pick shot speed as your metric, and a different card appears for the same shot." | Your metric picks the insight |
| 0:40–0:50 | Moment 3, 52:42 | Analyst mode: "his fastest header this season, 60 vs 51 km/h" | "It compares like with like: a header only with his other headers." | Like with like |
| 0:50–1:08 | Two viewers, 63:42 (`?view=two&t=63:30`) | Left: Japanese casual fan. Right: English analyst. Same goal, 118 km/h, two different cards | "Two viewers, the same moment. A casual fan in Japanese gets a short card; an analyst in English gets the numbers behind it. Every number is checked against the engine before it is shown." | Same moment, two viewers |
| 1:08–1:20 | VAR, 65:24 | Correction banner; the goal card is corrected and a secondary card withdrawn | "Then VAR disallows the goal. The feed sends a correction; the cards built on that event are withdrawn and his baselines rebuilt. Every card cites its source events, so the system knows what to undo." | Corrections roll back |
| 1:20–1:40 | Ask the analyst | Ask tab. Typed: "How did Harbourside's top scorer do in his last 3 games?" → answer with Reyner's three games. Then: "What is Milo Vexford's nationality?" → "I can't find Milo Vexford among tonight's players or clubs." | "Viewers can ask in their own words. A research agent chains lookups, finding the top scorer, then his last three games, and a second agent writes the answer from those facts only. Ask about a player who doesn't exist, and it says so, instead of making one up." | Answers from facts only |
| 1:40–1:55 | Architecture and evidence | `docs/architecture/architecture.png`, then a slide of numbers and services | "Agents on Microsoft Agent Framework and Microsoft Foundry, running on Azure Container Apps with a managed identity, no keys. The verifier catches 99.3% of injected errors; replaying a messy feed rebuilds the same baselines 300 times out of 300; and we test the answers on 90 hand-scored questions, including a head-to-head between two models." | Microsoft Foundry · Agent Framework · Azure Container Apps |
| 1:55 | End card | "Formline · synthetic data · github.com/roymwxuk/mwx-hackathon-formline" | (silence) | |

## Numbers slide (1:40–1:55)

- Verifier: **99.3%** of 1,066 injected errors caught, 0 false positives
- Feed robustness: **300 / 300** chaotic replays rebuild identical baselines
- Typed questions: **90** hand-scored questions, two runs: 80 and 84 handled correctly (answerable: 58–60 of 61)
- Model comparison: gpt-4.1-mini vs gpt-6-luna with criteria fixed in advance
- Azure: Microsoft Foundry, Microsoft Agent Framework, Azure Container Apps, Entra ID managed identity, GitHub Actions

## Before recording

1. Warm both apps: open the viewer and call `/health` once (cold start takes a few seconds).
2. Check each moment with `?t=` (12:05, 40:12, 52:42, 63:42, 65:24); the stream slows around shots.
3. Ask both typed questions once before recording: answers take 5–9 s, so cut the waiting in the edit
   (keep a short "thinking" beat), or record the answer appearing and trim.
4. Browser at 1920×1080, zoom 100%, no bookmarks bar or other tabs; hide the cursor when idle.
5. Record each scene as its own clip; join them in the editor and add the captions.

## Notes

- Keep every claim in the voiceover to something visible or measured; "estimate" is said
  aloud for every probability, as on the cards.
- If time runs short, cut scene 3 (52:42, header) first; it repeats the like-for-like point.
- No real league, club, player, broadcaster or betting names anywhere, including the voiceover.
