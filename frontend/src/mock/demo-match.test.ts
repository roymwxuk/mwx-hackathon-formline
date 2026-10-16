import { describe, expect, it } from "vitest";

import type { Overlay } from "@/contract";

import { demoFeed, demoMatch, demoOverlays, demoPlayers, demoViewers } from "./demo-match";

const kickoffMs = Date.parse(demoMatch.kickoff_at);
const creates = demoFeed.filter((m) => m.op === "create");
const updates = demoFeed.filter((m) => m.op === "update");
const eventIds = new Set(creates.map((m) => m.event_id));
const playerIds = new Set(demoPlayers.map((p) => p.player_id));
const clubIds = new Set([demoMatch.home_club_id, demoMatch.away_club_id]);

describe("demo feed", () => {
  it("has unique event and message ids", () => {
    expect(eventIds.size).toBe(creates.length);
    expect(new Set(demoFeed.map((m) => m.message_id)).size).toBe(demoFeed.length);
  });

  it("creates events in event-time order, emitted after they happen", () => {
    const clocks = creates.map((m) => m.event!.match_clock_ms);
    expect(clocks).toEqual([...clocks].sort((a, b) => a - b));
    for (const m of demoFeed) {
      expect(Date.parse(m.emitted_at)).toBeGreaterThanOrEqual(Date.parse(m.event!.event_time));
    }
  });

  it("only references known players, clubs and events", () => {
    for (const m of demoFeed) {
      const e = m.event!;
      expect(clubIds).toContain(e.team_id);
      if (e.player_id) expect(playerIds).toContain(e.player_id);
      for (const id of e.related_event_ids) expect(eventIds).toContain(id);
    }
  });

  it("sends updates as higher versions of existing events", () => {
    expect(updates.length).toBeGreaterThan(0);
    for (const u of updates) {
      expect(eventIds).toContain(u.event_id);
      expect(u.version).toBeGreaterThan(1);
      expect(u.event!.event_id).toBe(u.event_id);
    }
  });

  it("includes a VAR-cancelled goal", () => {
    const update = updates.find((u) => u.event?.type === "shot");
    const original = creates.find((m) => m.event_id === update?.event_id);
    expect(original?.event).toMatchObject({ type: "shot", outcome: "goal" });
    expect(update?.event).not.toMatchObject({ outcome: "goal" });
  });
});

describe.each(demoViewers)("overlay stream for $viewer_id", (viewer) => {
  const stream: Overlay[] = demoOverlays[viewer.viewer_id];
  const byId = new Map(stream.map((o) => [o.overlay_id, o]));

  it("exists and matches the viewer's language and mode", () => {
    expect(stream.length).toBeGreaterThan(0);
    expect(byId.size).toBe(stream.length);
    for (const o of stream) {
      expect(o.lang).toBe(viewer.lang);
      expect(o.audience_mode).toBe(viewer.mode);
    }
  });

  it("is in clock order and cites known source events", () => {
    const clocks = stream.map((o) => o.match_clock_ms);
    expect(clocks).toEqual([...clocks].sort((a, b) => a - b));
    for (const o of stream) for (const id of o.source_event_ids) expect(eventIds).toContain(id);
  });

  it("only supersedes earlier overlays in the same stream", () => {
    stream.forEach((o, i) => {
      if (o.op !== "show") expect(o.supersedes_overlay_id).toBeTruthy();
      if (o.supersedes_overlay_id) {
        const target = byId.get(o.supersedes_overlay_id);
        expect(target).toBeDefined();
        expect(stream.indexOf(target!)).toBeLessThan(i);
      }
    });
  });

  it("retracts or corrects every overlay that depended on a corrected event", () => {
    for (const u of updates) {
      const updateClock = Date.parse(u.emitted_at) - kickoffMs;
      const dependents = stream.filter(
        (o) =>
          o.op !== "retract" &&
          o.match_clock_ms < updateClock &&
          o.source_event_ids.includes(u.event_id),
      );
      for (const d of dependents) {
        const fixed = stream.some(
          (o) => o.op !== "show" && o.supersedes_overlay_id === d.overlay_id,
        );
        expect(fixed, `${d.overlay_id} still shows corrected ${u.event_id}`).toBe(true);
      }
    }
  });

  it("phrases baseline comparisons as estimates", () => {
    const word = viewer.lang === "ja" ? "推定" : "estimate";
    for (const o of stream) {
      if (o.op === "retract") continue;
      if (["shot_speed_card", "baseline_percentile_card", "chance_vs_norm_card"].includes(o.template_id)) {
        expect(JSON.stringify(o.slots), o.overlay_id).toContain(word);
      }
    }
  });
});

it("gives the two viewers genuinely different streams", () => {
  const [a, b] = demoViewers.map((v) => new Set(demoOverlays[v.viewer_id].map((o) => o.insight_id)));
  expect([...b].filter((id) => !a.has(id)).length).toBeGreaterThan(0);
});
