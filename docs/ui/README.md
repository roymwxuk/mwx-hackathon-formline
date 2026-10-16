# Formline UI reference images

These images are the visual target for the viewer UI.

## mockup/ — the design target (static)

| File | Screen |
|---|---|
| `1-live-viewer.png` | Live viewer: 2D pitch, overlay card, player focus strip, overlay log, "Make it yours" settings |
| `2-two-viewers.png` | Same moment for two viewers: casual Japanese fan vs English analyst |
| `3-var-correction.png` | Before and after VAR overturns a goal: card withdrawn, correction banner, steps the system took |

## prototype/ — what formline-ui already renders (mock data)

| File | Screen |
|---|---|
| `1-live-viewer.png` | Live viewer at 40:20, Reyner's shot card |
| `2-two-viewers.png` | Two viewers right after the VAR correction |
| `3-var-correction.png` | Live viewer after VAR: card withdrawn, banner, log |
| `4-phone.png` | Live viewer at phone width (390 px) |

## Notes for Claude Code

- The working UI is ``frontend/``. Treat it as the source of truth for layout and behavior; the mockups show intent where the two differ.
- Differences on purpose: in the prototype the overlay card sits bottom-left (so it doesn't cover the goal), and on phones the card moves below the pitch.
- Clubs and players are fictional. Keep it that way.
