import { formatClock } from "@/replay/describe";

export interface LogEntry {
  key: string;
  clockMs: number;
  text: string;
  kind: "event" | "highlight" | "correction";
  color: string;
}

const KIND_STYLE: Record<LogEntry["kind"], string> = {
  event: "text-slate-300",
  highlight: "font-semibold text-white",
  correction: "font-semibold text-yellow-300",
};

export function EventLog({ entries }: { entries: LogEntry[] }) {
  return (
    <div className="rounded-xl bg-slate-900 px-4 py-3">
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Event feed</h2>
      <ol className="space-y-1 text-sm">
        {entries.length === 0 && <li className="text-slate-500">Press play to start the replay.</li>}
        {entries.map((e) => (
          <li key={e.key} className="flex items-baseline gap-3">
            <span className="font-mono text-xs tabular-nums text-slate-500">{formatClock(e.clockMs)}</span>
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: e.color }} />
            <span className={KIND_STYLE[e.kind]}>{e.text}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
