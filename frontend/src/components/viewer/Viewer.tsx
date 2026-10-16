"use client";

import { useEffect, useMemo } from "react";

import type { ClubId, PlayerId } from "@/contract";
import { demoClockRange, demoClubs, demoFeed, demoMatch, demoPlayers } from "@/mock/demo-match";
import { describeCorrection, describeEvent, parseClock } from "@/replay/describe";
import { overturnedGoalIds, score, varReviewInProgress } from "@/replay/match-state";
import { resolveFeed } from "@/replay/resolve";
import { useReplayClock } from "@/replay/useReplayClock";

import { EventLog, type LogEntry } from "./EventLog";
import { Pitch } from "./Pitch";
import { PitchLayer } from "./PitchLayer";
import { ReplayControls } from "./ReplayControls";
import { Scoreboard } from "./Scoreboard";

const LOG_SIZE = 8;
const HIGHLIGHT_TYPES = new Set(["shot", "card", "var_review_start", "var_review_end"]);

// Step 2 replays the mock directly; step 6 swaps this for the backend stream.
const kickoffMs = Date.parse(demoMatch.kickoff_at);
const clubById = new Map(demoClubs.map((c) => [c.club_id, c]));
const playerById = new Map(demoPlayers.map((p) => [p.player_id, p]));
const home = clubById.get(demoMatch.home_club_id)!;
const away = clubById.get(demoMatch.away_club_id)!;
const colorOf = (id: ClubId) => clubById.get(id)?.colors.primary ?? "#94a3b8";
const nameOf = (id: PlayerId | null) => (id ? (playerById.get(id)?.display_name ?? id) : "—");
const CORRECTION_COLOR = "#facc15";

export function Viewer() {
  const { clockMs, playing, speed, setSpeed, togglePlay, seek } = useReplayClock(demoClockRange);

  // `?t=40:30` opens the replay at that moment (handy for screenshots and the demo video).
  useEffect(() => {
    const t = parseClock(new URLSearchParams(window.location.search).get("t"));
    if (t !== null) seek(t);
  }, [seek]);

  const resolved = useMemo(() => resolveFeed(demoFeed, clockMs, kickoffMs), [clockMs]);

  const visible = resolved.events.filter((e) => e.match_clock_ms <= clockMs);
  const overturned = overturnedGoalIds(resolved.corrections);

  const log: LogEntry[] = [
    ...visible.map((e) => ({
      key: e.event_id,
      clockMs: e.match_clock_ms,
      text: describeEvent(e, nameOf),
      kind: HIGHLIGHT_TYPES.has(e.type) ? ("highlight" as const) : ("event" as const),
      color: colorOf(e.team_id),
    })),
    ...resolved.corrections.map((c) => ({
      key: `corr_${c.event_id}_${c.clockMs}`,
      clockMs: c.clockMs,
      text: describeCorrection(c, nameOf),
      kind: "correction" as const,
      color: CORRECTION_COLOR,
    })),
  ]
    .sort((a, b) => b.clockMs - a.clockMs)
    .slice(0, LOG_SIZE);

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-3 px-4 py-6">
      <Scoreboard
        home={home}
        away={away}
        score={score(visible, [home.club_id, away.club_id])}
        clockMs={clockMs}
        varInProgress={varReviewInProgress(visible)}
      />
      <Pitch>
        <PitchLayer
          events={resolved.events}
          clockMs={clockMs}
          homeClubId={home.club_id}
          overturned={overturned}
          colorOf={colorOf}
          nameOf={nameOf}
        />
      </Pitch>
      <ReplayControls
        clockMs={clockMs}
        range={demoClockRange}
        playing={playing}
        speed={speed}
        onTogglePlay={togglePlay}
        onSeek={seek}
        onSpeed={setSpeed}
      />
      <EventLog entries={log} />
    </div>
  );
}
