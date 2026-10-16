# Formline — live viewer UI

The viewer for Formline: a 2D pitch, synchronized overlay cards, a player-focus strip, an overlay log and a personalization panel, plus a "two viewers" page that shows the same moment to two differently configured viewers.

Next.js (App Router) + React + TypeScript. No UI library. Design reference: `docs/ui/`. Background: ADR-004 in `docs/decisions.md`.

## Run

```bash
pnpm install
pnpm dev           # http://localhost:3000
pnpm test          # logic tests (event store, retractions, personalization)
pnpm lint && pnpm typecheck
pnpm build
```

`?t=mm:ss` opens the mock replay at that moment, e.g. `/?t=63:40` for the VAR sequence. Useful for screenshots and recording the demo.

## Data source

The UI reads one stream of `StreamMessage` objects (see `src/lib/types.ts`):

```ts
{ kind: 'event',   event: MatchEvent }   // raw match events (DATA_SCHEMA.md §4–5)
{ kind: 'overlay', overlay: Overlay }    // overlay contract (DATA_SCHEMA.md §6.5)
```

- **Mock mode (default).** With no environment variable set, `src/mock/demo-match.ts` replays a fictional match: 6 insights in EN/JA × casual/analyst, filler passes, and a VAR overturn at 65:27. Playback slows down around key moments so the overlays can be read.
- **Live mode.** Set `NEXT_PUBLIC_STREAM_URL` to the backend's Server-Sent Events endpoint. Each SSE `data:` line must be one `StreamMessage` as JSON. The value is inlined at build time.

```bash
NEXT_PUBLIC_STREAM_URL=http://localhost:8080/stream pnpm dev
```

## Where the logic lives

| File | What it does |
|---|---|
| `src/lib/logic.ts` | Event store (idempotent, highest version wins), score, overlay show/retract, personalization rules, focus stats |
| `src/lib/useMatchStream.ts` | Shared stream for all viewers: mock replay or SSE |
| `src/lib/i18n.ts` | EN/JA UI strings |
| `src/components/App.tsx` | Top bar, Live viewer / Two viewers tabs (client component) |
| `src/components/Viewer.tsx` | One viewer: stage + focus + log + settings |
| `src/components/Pitch.tsx` | SVG pitch: recent passes, shot line, freeze frame, ball. Analyst mode adds the shot cone and nearest-defender distance |
| `src/components/OverlayCard.tsx` | Overlay card (bars for casual, detail rows for analyst), withdrawn state, correction banner |
| `src/mock/demo-match.ts` | Mock data only. Delete once the backend streams real overlays |

## Personalization rules

Settings change **which** overlays appear, not only their wording:

- language and mode pick the overlay variant;
- "My metric" keeps only overlays for that metric (VAR corrections always pass);
- casual viewers with favorites see only their favorite players or clubs;
- analysts see every insight, with favorites marked.

Currently the client filters a stream that contains every variant. Later the backend can filter per viewer instead; the contract stays the same.

## Handover to the backend work

1. Make the backend emit `StreamMessage` JSON over SSE.
2. Point `NEXT_PUBLIC_STREAM_URL` at it and check the three key moments: a shot overlay, the two-viewer view, and the VAR retraction.
3. Remove `src/mock/` and the `CLUBS`/`PLAYERS` import in `src/components/App.tsx`, and load clubs and players from the backend instead.
