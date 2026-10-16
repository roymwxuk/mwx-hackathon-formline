import { formatClock } from "@/replay/describe";
import { REPLAY_SPEEDS, type ReplaySpeed } from "@/replay/useReplayClock";

interface Props {
  clockMs: number;
  range: { startMs: number; endMs: number };
  playing: boolean;
  speed: ReplaySpeed;
  onTogglePlay: () => void;
  onSeek: (ms: number) => void;
  onSpeed: (speed: ReplaySpeed) => void;
}

export function ReplayControls({ clockMs, range, playing, speed, onTogglePlay, onSeek, onSpeed }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl bg-slate-900 px-4 py-3">
      <button
        type="button"
        onClick={onTogglePlay}
        className="w-20 rounded-md bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-slate-950 hover:bg-emerald-400"
      >
        {playing ? "Pause" : "Play"}
      </button>
      <input
        type="range"
        aria-label="Match clock"
        min={range.startMs}
        max={range.endMs}
        step={100}
        value={clockMs}
        onChange={(e) => onSeek(Number(e.target.value))}
        className="min-w-40 flex-1 accent-emerald-500"
      />
      <span className="font-mono text-xs tabular-nums text-slate-400">
        {formatClock(range.startMs)}–{formatClock(range.endMs)}
      </span>
      <div className="flex overflow-hidden rounded-md border border-slate-700" role="group" aria-label="Replay speed">
        {REPLAY_SPEEDS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onSpeed(s)}
            aria-pressed={s === speed}
            className={`px-2.5 py-1 text-xs font-medium ${s === speed ? "bg-slate-200 text-slate-900" : "text-slate-300 hover:bg-slate-800"}`}
          >
            {s}×
          </button>
        ))}
      </div>
    </div>
  );
}
