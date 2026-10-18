import { useEffect, useRef, useState } from 'react';
import { freshComment } from '@/lib/analyst';
import { t } from '@/lib/i18n';
import type { CommentState } from '@/lib/logic';
import type { Lang } from '@/lib/types';

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
      <span className="comment-tag">{t(lang).analyst} · {t(lang).question[c.question as Q]}</span>
      <strong className="comment-headline">{c.headline}</strong>
      <p className="comment-body">{c.body}</p>
    </div>
  );
}

/** Every comment so far, newest first, with its evidence; withdrawn ones struck through. */
export function AnalystPanel({ comments, lang, limit }: { comments: CommentState[]; lang: Lang; limit?: number }) {
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
            <strong className="comment-headline">{c.headline}</strong>
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
