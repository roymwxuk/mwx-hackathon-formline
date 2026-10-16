import type { Club } from "@/contract";
import { formatClock } from "@/replay/describe";

interface Props {
  home: Club;
  away: Club;
  score: Record<string, number>;
  clockMs: number;
  varInProgress: boolean;
}

export function Scoreboard({ home, away, score, clockMs, varInProgress }: Props) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-xl bg-slate-900 px-4 py-3">
      <div className="flex items-center gap-3 text-lg font-semibold sm:text-xl">
        <ClubName club={home} />
        <span className="tabular-nums rounded-md bg-slate-800 px-3 py-1">
          {score[home.club_id]} – {score[away.club_id]}
        </span>
        <ClubName club={away} />
      </div>
      <div className="flex items-center gap-3">
        {varInProgress && (
          <span className="animate-pulse rounded-md bg-yellow-400 px-2 py-1 text-xs font-bold text-slate-900">
            VAR CHECK
          </span>
        )}
        <span className="font-mono text-lg tabular-nums text-slate-300">{formatClock(clockMs)}</span>
      </div>
    </div>
  );
}

function ClubName({ club }: { club: Club }) {
  return (
    <span className="flex items-center gap-2">
      <span className="h-3 w-3 rounded-full" style={{ backgroundColor: club.colors.primary }} />
      <span className="hidden sm:inline">{club.name}</span>
      <span className="sm:hidden">{club.short_name}</span>
    </span>
  );
}
