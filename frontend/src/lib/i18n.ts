import type { Lang } from '@/lib/types';

const dict = {
  en: {
    focusTitle: 'Player focus',
    focusSub: 'Tonight vs his own season norm',
    shotsTonight: 'Shots tonight',
    avgSpeed: 'Avg shot speed',
    lastShot: 'Last shot',
    goals: 'Goals',
    norm: 'norm',
    below: 'below his norm',
    above: 'above his norm',
    noShots: 'No shots yet',
    log: 'Overlay log',
    logEmpty: 'Insights appear here as the match unfolds.',
    verified: 'Verified',
    withdrawn: 'WITHDRAWN',
    withdrawnNote: 'Withdrawn after a data correction',
    source: 'Source',
    waiting: 'Waiting for the first insight…',
    favorite: 'Favorite',
    goal: 'GOAL!',
  },
  ja: {
    focusTitle: '選手フォーカス',
    focusSub: '今夜の数字と本人の今季平均',
    shotsTonight: '今夜のシュート',
    avgSpeed: '平均シュート速度',
    lastShot: '直近のシュート',
    goals: 'ゴール',
    norm: '平均',
    below: '本人平均より遅い',
    above: '本人平均より速い',
    noShots: 'まだシュートなし',
    log: 'オーバーレイ履歴',
    logEmpty: '試合の進行に合わせてここに表示されます。',
    verified: '検証済み',
    withdrawn: '取り消し',
    withdrawnNote: 'データ訂正により取り消されました',
    source: 'ソース',
    waiting: '最初のインサイトを待っています…',
    goal: 'ゴール！',
    favorite: '推し',
  },
} satisfies Record<Lang, Record<string, string>>;

export type Strings = (typeof dict)['en'];
export const t = (lang: Lang): Strings => dict[lang];
