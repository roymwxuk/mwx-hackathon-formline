import type { CommentState } from '@/lib/logic';
import type { Lang } from '@/lib/types';

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
