import { useEffect, useRef, useState } from 'react';
import { answerKey, askAnalyst, freshComment } from '@/lib/analyst';
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

type Asked = { status: 'loading' } | { status: 'done'; answer: FollowupAnswer } | { status: 'error' };

/** The comment's suggested questions as chips; a click asks the Analyst and shows the answer. */
function FollowUps({ comment: c, askUrl, lang }: { comment: AnalystComment; askUrl: string; lang: Lang }) {
  const str = t(lang);
  const [open, setOpen] = useState<FollowupSuggestion | null>(null);
  const [asked, setAsked] = useState<Record<string, Asked>>({});
  const suggestions = c.suggestions ?? [];
  if (!c.ask || suggestions.length === 0) return null;

  const choose = (s: FollowupSuggestion) => {
    const key = answerKey(c, s);
    if (open && answerKey(c, open) === key) return setOpen(null); // a second click closes it
    setOpen(s);
    if (asked[key] && asked[key].status !== 'error') return; // asked before: show it again
    setAsked((a) => ({ ...a, [key]: { status: 'loading' } }));
    askAnalyst(askUrl, c, s)
      .then((answer) => setAsked((a) => ({ ...a, [key]: { status: 'done', answer } })))
      .catch(() => setAsked((a) => ({ ...a, [key]: { status: 'error' } })));
  };
  const current = open ? asked[answerKey(c, open)] : undefined;

  return (
    <div className="followups">
      <div className="followup-chips" role="group" aria-label={str.ask}>
        {suggestions.map((s) => (
          <button key={s.question} type="button" className="followup-chip"
            aria-pressed={open?.question === s.question} onClick={() => choose(s)}>
            {s.label}
          </button>
        ))}
      </div>
      {open && current && (
        <div className="followup-answer" aria-live="polite">
          {current.status === 'loading' && <p className="muted">{str.thinking}</p>}
          {current.status === 'error' && <p className="danger-text">{str.askError}</p>}
          {current.status === 'done' && (
            <>
              <strong className="comment-headline">{current.answer.headline}</strong>
              <p className="comment-body">{current.answer.body}</p>
              {current.answer.evidence.length > 0 && (
                <p className="analyst-evidence muted">
                  {str.evidence}: {current.answer.evidence.map((e) => `${e.type.replace('_', ' ')} ${e.minute}`).join(' · ')}
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

/** Every comment so far, newest first, with its evidence; withdrawn ones struck through.
 *  With `askUrl` (live mode), each comment offers its follow-up questions. */
export function AnalystPanel({ comments, lang, limit, askUrl = null }: { comments: CommentState[]; lang: Lang; limit?: number; askUrl?: string | null }) {
  const str = t(lang);
  const items = [...comments].reverse().slice(0, limit);
  return (
    <section className="panel analyst" lang={lang} aria-label={str.analyst}>
      <div className="panel-head"><h2>{str.analyst}</h2></div>
      {items.length === 0 && <p className="muted">{str.analystEmpty}</p>}
      <ul className="analyst-list">
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
            {askUrl && !retracted && <FollowUps comment={c} askUrl={askUrl} lang={lang} />}
          </li>
        ))}
      </ul>
    </section>
  );
}
