/**
 * Resolve a feed into the event state visible at a given match clock.
 *
 * Timing: the pitch stands in for the video feed, so a `create` becomes visible
 * at its event time (`match_clock_ms`). Updates and deletes are data
 * corrections, so they apply only once the provider has sent them (`emitted_at`).
 * That is why a VAR-cancelled goal shows as a goal until the update arrives.
 */

import type { EventId, FeedMessage, MatchEvent } from "@/contract";

export interface Correction {
  event_id: EventId;
  clockMs: number;
  previous: MatchEvent | null;
  current: MatchEvent | null;
}

export interface ResolvedFeed {
  /** Latest visible version of each event, in event-time order. */
  events: MatchEvent[];
  byId: Map<EventId, MatchEvent>;
  /** Applied updates and deletes, in arrival order. */
  corrections: Correction[];
}

export function arrivalClockMs(message: FeedMessage, kickoffMs: number): number {
  return message.op === "create"
    ? message.event.match_clock_ms
    : Date.parse(message.emitted_at) - kickoffMs;
}

export function resolveFeed(feed: FeedMessage[], clockMs: number, kickoffMs: number): ResolvedFeed {
  const arrived = feed
    .map((message) => ({ message, at: arrivalClockMs(message, kickoffMs) }))
    .filter(({ at }) => at <= clockMs)
    .sort((a, b) => a.at - b.at || a.message.version - b.message.version);

  const latest = new Map<EventId, { version: number; event: MatchEvent | null }>();
  const corrections: Correction[] = [];

  for (const { message, at } of arrived) {
    const prev = latest.get(message.event_id);
    // Duplicate deliveries and stale versions are ignored: the highest version wins.
    if (prev && prev.version >= message.version) continue;
    latest.set(message.event_id, { version: message.version, event: message.event });
    if (prev) {
      corrections.push({
        event_id: message.event_id,
        clockMs: at,
        previous: prev.event,
        current: message.event,
      });
    }
  }

  const events = [...latest.values()]
    .map((v) => v.event)
    .filter((e): e is MatchEvent => e !== null)
    .sort((a, b) => a.match_clock_ms - b.match_clock_ms);

  return { events, byId: new Map(events.map((e) => [e.event_id, e])), corrections };
}
