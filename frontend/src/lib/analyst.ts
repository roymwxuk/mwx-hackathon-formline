import type { CommentState } from '@/lib/logic';
import type { AnalystComment, FollowupAnswer, FollowupSuggestion, FreeAnswer, Lang } from '@/lib/types';

/** How recent (match time) a comment must be to pop up: comments replayed at once after a
 *  jump or a reconnect are older than this when they arrive, so they only go to the panel. */
export const COMMENT_RECENT_MS = 20_000;

export function commentsFor(states: CommentState[], lang: Lang): CommentState[] {
  return states.filter((s) => s.comment.lang === lang);
}

/** The newest comment that just happened and has not popped up yet, if any. */
export function freshComment(states: CommentState[], clockMs: number, shown: Set<string>): CommentState | undefined {
  const last = states[states.length - 1];
  if (!last || last.retracted || shown.has(last.comment.comment_id)) return undefined;
  return Math.abs(clockMs - last.comment.match_clock_ms) <= COMMENT_RECENT_MS ? last : undefined;
}

/** The /ask endpoint next to a match's stream URL (.../matches/{id}/stream?… → .../ask). */
export function askUrlFor(streamUrl: string): string {
  const url = new URL(streamUrl);
  url.search = '';
  url.pathname = url.pathname.replace(/\/stream\/?$/, '/ask');
  return url.toString();
}

/** One answer per comment moment, question, player and language (as the backend keys it). */
export function answerKey(c: AnalystComment, s: FollowupSuggestion): string {
  return `${c.ask?.moment ?? ''}|${s.question}|${s.player_id ?? ''}|${c.lang}`;
}

/** Ask the Analyst a follow-up question about a comment's moment. */
export async function askAnalyst(url: string, c: AnalystComment, s: FollowupSuggestion, signal?: AbortSignal): Promise<FollowupAnswer> {
  if (!c.ask) throw new Error('this comment has no follow-up questions');
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ ...c.ask, question: s.question, player_id: s.player_id, lang: c.lang }),
    signal,
  });
  if (!res.ok) throw new Error(`ask failed: ${res.status}`);
  return (await res.json()) as FollowupAnswer;
}

/** The newest comment that offers follow-up questions (withdrawn ones do not). */
export function latestAskable(states: CommentState[]): CommentState | undefined {
  for (let i = states.length - 1; i >= 0; i -= 1) {
    const s = states[i];
    if (!s.retracted && s.comment.ask && (s.comment.suggestions?.length ?? 0) > 0) return s;
  }
  return undefined;
}

/** The Analyst's rate limit for typed questions was reached (HTTP 429). */
export class AskLimited extends Error {}

/** Ask a typed question in the context of a comment's moment; the backend routes it to a
 *  catalog question or declines. */
export async function askFree(url: string, c: AnalystComment, text: string, signal?: AbortSignal): Promise<FreeAnswer> {
  if (!c.ask) throw new Error('this comment has no follow-up questions');
  const res = await fetch(`${url}/free`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ ...c.ask, text, lang: c.lang }),
    signal,
  });
  if (res.status === 429) throw new AskLimited('too many questions');
  if (!res.ok) throw new Error(`ask failed: ${res.status}`);
  return (await res.json()) as FreeAnswer;
}
