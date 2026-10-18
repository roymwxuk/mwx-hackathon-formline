import { afterEach, describe, expect, it, vi } from 'vitest';
import { AskLimited, answerKey, askAnalyst, askFree, askUrlFor, asOfLatest, commentsFor, freshComment, latestAskable } from '@/lib/analyst';
import { applyComments } from '@/lib/logic';
import type { AnalystComment, MatchEvent } from '@/lib/types';

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

describe('follow-up questions', () => {
  const ask = { moment: 'shot_outcome_evt_3100323', seq: 323 };
  const me = { question: 'player_tonight' as const, label: 'How is Ito doing tonight?', player_id: 'ply_0203' };
  const score = { question: 'score' as const, label: 'Why is it 1–0?', player_id: null };

  afterEach(() => vi.unstubAllGlobals());

  it('asks about the newest comment that has questions, never a withdrawn one', () => {
    const suggestions = [score];
    const states = applyComments([
      c('a', 1_000, 'en', { ask, suggestions }),
      c('b', 2_000, 'en', { ask: { moment: 'corner_evt_9', seq: 400 }, suggestions }),
      c('old', 3_000), // no questions
    ]);
    expect(latestAskable(states)?.comment.comment_id).toBe('b');
    const withdrawn = applyComments([
      c('a', 1_000, 'en', { ask, suggestions }),
      c('b', 2_000, 'en', { ask: { moment: 'corner_evt_9', seq: 400 }, suggestions }),
      c('b_retract', 4_000, 'en', { op: 'retract', supersedes_comment_id: 'b' }),
    ]);
    expect(latestAskable(withdrawn)?.comment.comment_id).toBe('a');
    expect(latestAskable([])).toBeUndefined();
  });

  it('posts to /ask next to the stream URL', () => {
    expect(askUrlFor('http://localhost:8000/matches/m1/stream?speed=20&slow=false'))
      .toBe('http://localhost:8000/matches/m1/ask');
  });

  it('keys an answer like the backend: moment, question, player, language', () => {
    expect(answerKey(c('a', 0, 'ja', { ask }), me)).toBe('shot_outcome_evt_3100323|player_tonight|ply_0203|ja');
    expect(answerKey(c('a', 0, 'en', { ask }), score)).toBe('shot_outcome_evt_3100323|score||en');
  });

  it("sends the comment's ask, the question and the language", async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ headline: 'H', body: 'B' }) });
    vi.stubGlobal('fetch', fetch);
    const answer = await askAnalyst('http://x/matches/m1/ask', c('a', 0, 'ja', { ask }), me);
    expect(answer.headline).toBe('H');
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe('http://x/matches/m1/ask');
    expect(JSON.parse(init.body)).toEqual({ ...ask, question: 'player_tonight', player_id: 'ply_0203', lang: 'ja' });
  });

  it('asks "as of" the latest event received, from kick-off', () => {
    expect(asOfLatest([])).toBeNull();
    const ev = (id: string, clock: number, version = 1) => ({ event_id: id, version, match_clock_ms: clock }) as MatchEvent;
    expect(asOfLatest([ev('e1', 0), ev('e2', 52 * 60_000 + 10_000, 2)])).toEqual({ event_id: 'e2', version: 2, minute: "53'" });
  });

  it('sends a typed question to /ask/free with the event and the language', async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ retrieved: null, answer: null, declined: 'no' }) });
    vi.stubGlobal('fetch', fetch);
    const out = await askFree('http://x/matches/m1/ask', { event_id: 'evt_9', version: 2, minute: "53'" }, 'レイナーは？', 'ja');
    expect(out.declined).toBe('no');
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe('http://x/matches/m1/ask/free');
    expect(JSON.parse(init.body)).toEqual({ event_id: 'evt_9', version: 2, text: 'レイナーは？', lang: 'ja' });
  });

  it('tells the rate limit apart from other errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 429 }));
    await expect(askFree('http://x/ask', { event_id: 'e', version: 1, minute: "1'" }, 'score?', 'en')).rejects.toBeInstanceOf(AskLimited);
  });

  it('fails on an error status, so the panel can offer a retry', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 422 }));
    await expect(askAnalyst('http://x/ask', c('a', 0, 'en', { ask }), score)).rejects.toThrow('422');
  });
});
