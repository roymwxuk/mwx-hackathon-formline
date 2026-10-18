import { describe, expect, it } from 'vitest';
import { commentsFor, freshComment } from '@/lib/analyst';
import { applyComments } from '@/lib/logic';
import type { AnalystComment } from '@/lib/types';

const c = (id: string, clock: number, lang: 'en' | 'ja' = 'en', extra: Partial<AnalystComment> = {}): AnalystComment => ({
  comment_id: id, op: 'show', supersedes_comment_id: null, question: 'shot_outcome', period: 2,
  match_clock_ms: clock, lang, headline: `h ${id}`, body: 'b', player_id: 'p',
  evidence: [{ event_id: 'e', minute: "64'", type: 'shot' }], verified: true, source: 'llm', ...extra,
});

describe('analyst comments', () => {
  it('keeps arrival order, ignores duplicates, and withdraws on retract', () => {
    const goal = c('goal', 3_822_000);
    const states = applyComments([goal, goal, c('next', 3_830_000),
      c('goal_retract', 3_923_000, 'en', { op: 'retract', supersedes_comment_id: 'goal' })]);
    expect(states.map((s) => s.comment.comment_id)).toEqual(['goal', 'next']);
    expect(states[0].retracted).toBe(true);
  });

  it('filters by the viewer language', () => {
    const states = applyComments([c('a', 1, 'en'), c('b', 1, 'ja')]);
    expect(commentsFor(states, 'ja').map((s) => s.comment.comment_id)).toEqual(['b']);
  });

  it('pops up only a comment that just happened, once', () => {
    const states = applyComments([c('old', 1_000), c('new', 3_822_000)]);
    expect(freshComment(states, 3_825_000, new Set())?.comment.comment_id).toBe('new');
    expect(freshComment(states, 3_825_000, new Set(['new']))).toBeUndefined();
    expect(freshComment(states, 3_900_000, new Set())).toBeUndefined(); // replayed after a jump
  });
});
