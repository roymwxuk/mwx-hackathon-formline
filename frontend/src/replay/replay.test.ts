import { describe, expect, it } from "vitest";

import type { FeedMessage, ShotEvent } from "@/contract";
import { demoClockRange, demoFeed, demoMatch } from "@/mock/demo-match";

import { formatClock, parseClock } from "./describe";
import { overturnedGoalIds, score, varReviewInProgress } from "./match-state";
import { ballState, toPitch } from "./pitch";
import { resolveFeed } from "./resolve";

const kickoffMs = Date.parse(demoMatch.kickoff_at);
const clubs = [demoMatch.home_club_id, demoMatch.away_club_id];
const update = demoFeed.find((m) => m.op === "update")!;
const updateClock = Date.parse(update.emitted_at) - kickoffMs;
const header = update.event as ShotEvent;
const at = (ms: number) => resolveFeed(demoFeed, ms, kickoffMs);

describe("resolveFeed", () => {
  it("shows nothing before the first event and everything at the end", () => {
    expect(at(demoClockRange.startMs - 1).events).toHaveLength(0);
    const creates = demoFeed.filter((m) => m.op === "create").length;
    expect(at(demoClockRange.endMs).events).toHaveLength(creates);
  });

  it("keeps the header as a goal until the VAR update arrives, then flips it", () => {
    const before = at(updateClock - 1);
    expect(before.byId.get(header.event_id)).toMatchObject({ outcome: "goal" });
    expect(before.corrections).toHaveLength(0);

    const after = at(updateClock);
    expect(after.byId.get(header.event_id)).toMatchObject({ outcome: "off_target" });
    expect(overturnedGoalIds(after.corrections)).toEqual(new Set([header.event_id]));
  });

  it("drops the overturned goal from the score", () => {
    expect(score(at(updateClock - 1).events, clubs)).toEqual({
      [demoMatch.home_club_id]: 1,
      [demoMatch.away_club_id]: 1,
    });
    expect(score(at(updateClock).events, clubs)).toEqual({
      [demoMatch.home_club_id]: 0,
      [demoMatch.away_club_id]: 1,
    });
  });

  it("ignores duplicates and stale versions; applies deletes", () => {
    const v2: FeedMessage = { ...update, message_id: "dup" };
    const stale: FeedMessage = { ...update, message_id: "old", version: 1 };
    const del: FeedMessage = {
      ...update,
      message_id: "del",
      op: "delete",
      version: 3,
      event: null,
      emitted_at: new Date(Date.parse(update.emitted_at) + 1000).toISOString(),
    };
    const once = resolveFeed([...demoFeed, v2, stale], demoClockRange.endMs, kickoffMs);
    expect(once.corrections).toHaveLength(1);
    const deleted = resolveFeed([...demoFeed, del], demoClockRange.endMs, kickoffMs);
    expect(deleted.byId.has(header.event_id)).toBe(false);
  });
});

it("flags a VAR review only between its start and end events", () => {
  const { events } = at(demoClockRange.endMs);
  const start = events.find((e) => e.type === "var_review_start")!;
  const end = events.find((e) => e.type === "var_review_end")!;
  expect(varReviewInProgress(at(start.match_clock_ms - 1).events)).toBe(false);
  expect(varReviewInProgress(at(start.match_clock_ms).events)).toBe(true);
  expect(varReviewInProgress(at(end.match_clock_ms).events)).toBe(false);
});

describe("pitch", () => {
  it("flips the away team onto the home team's frame", () => {
    expect(toPitch(demoMatch.home_club_id, demoMatch.home_club_id, 100, 0)).toEqual({ x: 105, y: 0 });
    expect(toPitch(demoMatch.away_club_id, demoMatch.home_club_id, 100, 0)).toEqual({ x: 0, y: 68 });
  });

  it("interpolates the ball along a pass and tags the receiver on arrival", () => {
    const { events } = at(demoClockRange.endMs);
    const pass = events.find((e) => e.type === "pass")!;
    if (pass.type !== "pass") throw new Error("expected a pass");
    const home = demoMatch.home_club_id;
    const start = toPitch(pass.team_id, home, pass.x, pass.y);
    const end = toPitch(pass.team_id, home, pass.end_x, pass.end_y);

    const mid = ballState(events, pass.match_clock_ms + pass.duration_ms! / 2, home)!;
    expect(mid.inFlight).toBe(true);
    expect(mid.playerId).toBe(pass.player_id);
    expect(mid.position.x).toBeCloseTo((start.x + end.x) / 2);
    expect(mid.position.y).toBeCloseTo((start.y + end.y) / 2);

    const landed = ballState(events, pass.match_clock_ms + pass.duration_ms!, home)!;
    expect(landed.inFlight).toBe(false);
    expect(landed.playerId).toBe(pass.recipient_id);
    expect(landed.position).toEqual(end);
  });
});

it("formats the match clock", () => {
  expect(formatClock(38 * 60_000 + 7_900)).toBe("38:07");
  expect(parseClock("40:30")).toBe(40 * 60_000 + 30_000);
  expect(parseClock("40:75")).toBeNull();
  expect(parseClock(null)).toBeNull();
});
