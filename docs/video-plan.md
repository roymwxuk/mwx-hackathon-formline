# Demo video plan

**Goal:** under 2 minutes, recorded against the Azure deployment, no trademarks, no
copyrighted music. The script and shot list are milestone 5 task 6; this file fixes the
moments first.

## Moments (all Reyner, so player focus follows one story)

| Time | Moment | What it shows | Settings |
|---|---|---|---|
| 12:05 | 101 km/h, about 13 km/h above his norm, est. 91st percentile | The personal baseline idea; the focus strip | Live viewer, EN casual, focus Reyner |
| 40:12 | Placement 44/100, est. 14th percentile; for a shot-speed viewer, 84 km/h vs 92 | Below his norm; **"my metric" changes which insight appears** | Toggle my metric: all → shot speed |
| 52:42 | His fastest header this season, 60 vs 51 km/h | Like for like: headers compared only with his headers | Analyst mode |
| 63:42 | 118 km/h, fastest this season, goal | **Two viewers**, same moment: JA casual vs EN analyst | Two viewers page |
| 65:24 | VAR disallows the goal | Correction banner; card corrected and the placement secondary withdrawn; baselines rebuilt | Two viewers page |

Then: architecture diagram (`docs/architecture/architecture.png`), the measured numbers
(verifier 99.3%, convergence 300/300, shrinkage 30% / 45%), and the Azure services.

## Recording notes

- Speed 20× between moments; the stream slows down around shots automatically.
- Use `start=mm:ss` in the stream URL or the speed control to jump between moments.
- Warm the Container Apps (one request) before recording; cold start takes a few seconds.
