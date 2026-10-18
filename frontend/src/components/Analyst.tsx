import { useEffect, useRef, useState } from 'react';
import { AskLimited, answerKey, askAnalyst, askFree, freshComment, latestAskable } from '@/lib/analyst';
import { t } from '@/lib/i18n';
import type { CommentState } from '@/lib/logic';
import type { AnalystComment, FollowupAnswer, FollowupSuggestion, Lang } from '@/lib/types';

const BUBBLE_MS = 9_000; // real time, long enough to read two sentences at any speed

type Q = 'shot_outcome' | 'corner' | 'card' | 'var';

/** The latest Analyst comment, popping up next to the insight card for a few seconds. */
export function CommentBubble({ comments, clockMs, lang, paused = false }: { comments: CommentState[]; clockMs: number; lang: Lang; paused?: boolean }) {
  const shown = useRef(new Set<string>());
  const [current, setCurrent] = useState<CommentState | null>(null);
  const fresh = paused ? undefined : freshComment(comments, clockMs, shown.current);
  useEffect(() => {
    if (!fresh) return;
    shown.current.add(fresh.comment.comment_id);
    setCurrent(fresh);
  }, [fresh]);
  useEffect(() => { // hide after BUBBLE_MS; separate, so the next render does not cancel it
    if (!current) return;
    const timer = setTimeout(() => setCurrent(null), BUBBLE_MS);
    return () => clearTimeout(timer);
  }, [current]);
  if (!current) return null;
  const c = current.comment;
  return (
    <div key={c.comment_id} className="comment-bubble" role="status" lang={lang}>
      <button type="button" className="card-close" aria-label="Close" title="Close" onClick={() => setCurrent(null)}>×</button>
      <span className="comment-tag">{t(lang).analyst} · {t(lang).question[c.question as Q]}</span>
      <strong className={`comment-headline${c.goal ? ' goal' : ''}`}>{c.headline}</strong>
      <p className="comment-body">{c.body}</p>
    </div>
  );
}

type Asked =
  | { status: 'loading' }
  | { status: 'done'; answer: Pick<FollowupAnswer, 'headline' | 'body' | 'evidence'>; basedOn?: string; partial?: boolean }
  | { status: 'declined'; message: string }
  | { status: 'limited' }
  | { status: 'error' };
/** One question asked in the Ask tab: a suggested one (`label`) or typed (`label` = the text). */
interface AskedItem { key: string; lang: Lang; label: string; minute: string; state: Asked }

const MAX_TEXT = 200; // backend analyst/router.py MAX_TEXT

/** "Ask the analyst": the latest moment's suggested questions, and the answers asked so far. */
function AskTab({ comments, askUrl, lang, limit }: { comments: CommentState[]; askUrl: string; lang: Lang; limit?: number }) {
  const str = t(lang);
  const latest = latestAskable(comments)?.comment;
  const [items, setItems] = useState<AskedItem[]>([]);
  const [text, setText] = useState('');
  const mine = items.filter((i) => i.lang === lang);
  const settle = (key: string, state: Asked) => setItems((list) => list.map((i) => (i.key === key ? { ...i, state } : i)));
  const failed = (key: string) => (err: unknown) => settle(key, err instanceof AskLimited ? { status: 'limited' } : { status: 'error' });

  const ask = (c: AnalystComment, s: FollowupSuggestion) => {
    const key = answerKey(c, s);
    const existing = items.find((i) => i.key === key);
    const item: AskedItem = existing && existing.state.status !== 'error'
      ? existing // asked before: bring it back to the top
      : { key, lang: c.lang, label: s.label, minute: c.evidence[0]?.minute ?? '', state: { status: 'loading' } };
    setItems((list) => [item, ...list.filter((i) => i.key !== key)]);
    if (item !== existing) askAnalyst(askUrl, c, s).then((answer) => settle(key, { status: 'done', answer })).catch(failed(key));
  };

  const askTyped = (c: AnalystComment) => {
    const question = text.trim().slice(0, MAX_TEXT);
    if (!question) return;
    const key = `free|${c.ask?.moment}|${question}|${c.lang}`;
    setText('');
    setItems((list) => [{ key, lang: c.lang, label: question, minute: c.evidence[0]?.minute ?? '', state: { status: 'loading' } },
      ...list.filter((i) => i.key !== key)]);
    askFree(askUrl, c, question)
      .then((r) => settle(key, r.answer && r.retrieved
        ? { status: 'done', answer: r.answer, basedOn: r.retrieved.label, partial: r.answer.coverage === 'partial' }
        : { status: 'declined', message: r.declined ?? '' }))
      .catch(failed(key));
  };

  return (
    <div className="ask-tab">
      {!latest && <p className="muted">{str.askEmpty}</p>}
      {latest && (
        <div className="ask-moment">
          <span className="comment-tag">{str.askAbout} · {latest.evidence[0]?.minute ?? ''}</span>
          <strong className={`comment-headline${latest.goal ? ' goal' : ''}`}>{latest.headline}</strong>
          <div className="followup-chips" role="group" aria-label={str.ask}>
            {(latest.suggestions ?? []).map((s) => (
              <button key={s.question} type="button" className="followup-chip"
                aria-pressed={mine[0]?.key === answerKey(latest, s)} onClick={() => ask(latest, s)}>
                {s.label}
              </button>
            ))}
          </div>
          <form className="ask-form" onSubmit={(e) => { e.preventDefault(); askTyped(latest); }}>
            <textarea rows={2} value={text} maxLength={MAX_TEXT} placeholder={str.askPlaceholder}
              aria-label={str.askPlaceholder} onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { // Enter asks, Shift+Enter starts a new line (not while composing Japanese)
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); askTyped(latest); }
              }} />
            <button type="submit" className="ctl" disabled={!text.trim()}>{str.askSend}</button>
          </form>
        </div>
      )}
      {mine.length > 0 && (
        <ul className="analyst-list">
          {mine.slice(0, limit).map((i) => (
            <li key={i.key} className="followup-answer" aria-live="polite">
              <span className="comment-tag ask-q">{i.minute} · {i.label}</span>
              {i.state.status === 'loading' && <p className="muted">{str.thinking}</p>}
              {i.state.status === 'error' && <p className="danger-text">{str.askError}</p>}
              {i.state.status === 'limited' && <p className="danger-text">{str.askLimited}</p>}
              {i.state.status === 'declined' && <p className="comment-body muted">{i.state.message}</p>}
              {i.state.status === 'done' && (
                <>
                  {i.state.basedOn && <span className="muted ask-routed">{str.basedOn}: {i.state.basedOn}</span>}
                  <strong className="comment-headline">{i.state.answer.headline}</strong>
                  <p className="comment-body">{i.state.answer.body}</p>
                  {i.state.partial && <p className="muted ask-routed">{str.askPartial}</p>}
                  {limit === undefined && i.state.answer.evidence.length > 0 && (
                    <p className="analyst-evidence muted">
                      {str.evidence}: {i.state.answer.evidence.map((e) => `${e.type.replace('_', ' ')} ${e.minute}`).join(' · ')}
                    </p>
                  )}
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

type Tab = 'comments' | 'ask';

/** Two tabs: the commentary (every comment so far, newest first, with its evidence; withdrawn
 *  ones struck through) and, in live mode (`askUrl`), "Ask the analyst". A dot on the Ask tab
 *  says the latest moment has new questions. */
export function AnalystPanel({ comments, lang, limit, askUrl = null }: { comments: CommentState[]; lang: Lang; limit?: number; askUrl?: string | null }) {
  const str = t(lang);
  const items = [...comments].reverse().slice(0, limit);
  const [tab, setTab] = useState<Tab>('comments');
  const latestMoment = latestAskable(comments)?.comment.ask?.moment;
  const [seen, setSeen] = useState<string | undefined>();
  useEffect(() => { if (tab === 'ask') setSeen(latestMoment); }, [tab, latestMoment]);
  const fresh = askUrl !== null && tab !== 'ask' && latestMoment !== undefined && latestMoment !== seen;
  const showAsk = askUrl !== null && tab === 'ask';
  return (
    <section className="panel analyst" lang={lang} aria-label={str.analyst}>
      <div className="panel-head"><h2>{str.analyst}</h2></div>
      {askUrl && (
        <div className="panel-tabs" role="tablist" aria-label={str.analyst}>
          <button type="button" role="tab" aria-selected={tab === 'comments'} onClick={() => setTab('comments')}>{str.tabCommentary}</button>
          <button type="button" role="tab" aria-selected={tab === 'ask'} onClick={() => setTab('ask')}>
            {str.ask}{fresh && <span className="tab-dot" title={str.newQuestions} aria-label={str.newQuestions} />}
          </button>
        </div>
      )}
      {askUrl && <div hidden={!showAsk}><AskTab comments={comments} askUrl={askUrl} lang={lang} limit={limit} /></div>}
      {!showAsk && items.length === 0 && <p className="muted">{str.analystEmpty}</p>}
      <ul className="analyst-list" hidden={showAsk}>
        {items.map(({ comment: c, retracted }) => (
          <li key={c.comment_id} className={retracted ? 'retracted' : ''}>
            <div className="analyst-meta">
              <span className="log-clock">{c.evidence[0]?.minute ?? ''}</span>
              <span className="comment-tag">{str.question[c.question as Q]}</span>
              {retracted && <span className="danger-text">{str.analystWithdrawn}</span>}
            </div>
            <strong className={`comment-headline${c.goal ? ' goal' : ''}`}>{c.headline}</strong>
            <p className="comment-body">{c.body}</p>
            {limit === undefined && (
              <p className="analyst-evidence muted">
                {str.evidence}: {c.evidence.map((e) => `${e.type.replace('_', ' ')} ${e.minute}`).join(' · ')}
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
