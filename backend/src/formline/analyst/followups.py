"""Follow-up questions: the fixed catalog a viewer can ask after a key moment (phase 2).

Each Analyst comment offers 2–3 of these questions; the Suggester agent picks which ones
(`analyst/suggester.py`), but only from this catalog and only those that apply, so every
question shown is one the data can answer. The question wording is fixed here, never written
by the model. Each question has a deterministic facts pack built from the events known when
the comment was written; the Analyst agent answers from it and the verifier checks the answer,
exactly as for the comments.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from string import ascii_uppercase

from formline.analyst.facts import OUTCOME, FactsPack, _score_text, score_after
from formline.engine.features import shot_features

FOLLOWUPS = ("situation", "score", "player_tonight", "team_stats")

# What each answer covers: the Suggester reads these to choose.
DESCRIPTIONS = {
    "situation": "the score, the goals and the flow of the match so far",
    "score": "why the score is what it is: the goals and their chance quality, the best missed "
             "chances, the goalkeepers' saves",
    "player_tonight": "how the player in this moment is doing tonight, compared with his own "
                      "season norm",
    "team_stats": "the two teams side by side: shots, on target, chance quality, corners, "
                  "cards, passes",
}

# The Suggester's fallback, best first, per kind of moment (also the order options are offered).
DEFAULT_ORDER = {
    "goal": ("score", "player_tonight", "situation", "team_stats"),
    "shot_outcome": ("player_tonight", "score", "team_stats", "situation"),
    "corner": ("team_stats", "situation", "score"),
    "card": ("situation", "team_stats", "score"),
    "var": ("score", "situation", "team_stats"),
}


def _key(e) -> tuple[int, int]:
    return e.period, e.match_clock_ms


@dataclass
class Moment:
    """What was known when a comment was written: every event so far, and its player."""

    kind: str  # the comment's question: shot_outcome | corner | card | var
    event: object  # the event the comment is about
    events: list  # all known events (latest versions), in match-time order
    player_id: str | None
    home: str
    away: str
    clubs: Mapping[str, str]  # club id -> name
    players: Mapping  # player id -> Player
    norm: Callable[[str], float | None] | None = None  # season shot-speed norm (strong foot)
    _shots: list | None = field(default=None, repr=False)

    @property
    def id(self) -> str:
        return f"{self.kind}_{self.event.event_id}"

    @property
    def shots(self) -> list:
        if self._shots is None:
            self._shots = [e for e in self.events if e.type == "shot"]
        return self._shots

    @property
    def score(self) -> dict[str, int]:
        return score_after(self.events, max(self.events, key=_key), self.home, self.away)

    def default_order(self) -> tuple[str, ...]:
        goal = self.kind == "shot_outcome" and getattr(self.event, "outcome", None) == "goal"
        return DEFAULT_ORDER["goal" if goal else self.kind]


def moment_kind(moment_id: str) -> tuple[str, str] | None:
    """('shot_outcome', 'evt_…') from a moment id, or None if it is not one."""
    for kind in ("shot_outcome", "corner", "card", "var"):
        if moment_id.startswith(kind + "_") and len(moment_id) > len(kind) + 1:
            return kind, moment_id[len(kind) + 1:]
    return None


def applicable(q: str, m: Moment) -> bool:
    if q == "player_tonight":
        return m.player_id is not None and any(s.player_id == m.player_id for s in m.shots)
    return q in FOLLOWUPS


def options(m: Moment) -> list[str]:
    """The questions that apply to this moment, in its default order."""
    return [q for q in m.default_order() if applicable(q, m)]


def label(q: str, lang: str, m: Moment, player_name: str | None) -> str:
    """The button text: fixed wording per question and language."""
    if q == "situation":
        return "What's happening?" if lang == "en" else "いまの試合の流れは？"
    if q == "score":
        h, a = m.score[m.home], m.score[m.away]
        if lang == "ja":
            return f"なぜ{h}–{a}なのか？"
        return f"Why is it still {h}–{a}?" if h == a == 0 else f"Why is it {h}–{a}?"
    if q == "player_tonight":
        return f"How is {player_name} doing tonight?" if lang == "en" else f"今夜の{player_name}の出来は？"
    return "Compare the teams" if lang == "en" else "両チームを比較"


# ---------- facts packs ----------

def _xg(shot, m: Moment) -> float:
    return shot_features(shot, m.players.get(shot.player_id)).xg


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def _minute(e) -> int:
    return e.match_clock_ms // 60_000 + 1


class _Roles:
    """One placeholder per player (SCORER_A, CHANCE_B…), reused if he appears twice."""

    def __init__(self) -> None:
        self.roles: dict[str, str] = {}

    def __call__(self, prefix: str, player_id: str) -> str:
        for role, pid in self.roles.items():
            if pid == player_id:
                return role
        n = sum(r.startswith(prefix + "_") for r in self.roles)
        role = f"{prefix}_{ascii_uppercase[n]}"
        self.roles[role] = player_id
        return role


def _per_side(m: Moment, count: Callable[[str], object]) -> str:
    return f"{m.clubs[m.home]} {count(m.home)}, {m.clubs[m.away]} {count(m.away)}"


def _goals_text(m: Moment, roles: _Roles, with_xg: bool) -> tuple[str, list[str]]:
    goals = [s for s in m.shots if s.outcome == "goal"]
    if not goals:
        return "no goals yet", []
    parts = []
    for g in goals:
        text = f"{roles('SCORER', g.player_id)} ({m.clubs[g.team_id]}) in minute {_minute(g)}"
        if with_xg:
            text += f", a {_pct(_xg(g, m))} chance (model estimate, xG)"
        parts.append(text)
    return "; ".join(parts), [g.event_id for g in goals]


def situation_pack(m: Moment, roles: _Roles | None = None) -> FactsPack:
    roles = roles or _Roles()  # shared when merged into a typed question's facts
    now = max(m.events, key=_key)
    goals, sources = _goals_text(m, roles, with_xg=False)
    facts: dict = {
        "minute": f"minute {_minute(now)}",
        "score_now": _score_text(m.score, m.home, m.away, m.clubs),
        "goals": goals,
        "shots": "shots: " + _per_side(m, lambda t: sum(s.team_id == t for s in m.shots)),
    }
    recent = [s for s in m.shots if s.period == now.period
              and now.match_clock_ms - s.match_clock_ms <= 10 * 60_000]
    facts["recent"] = f"{len(recent)} shot(s) in the last 10 minutes"
    cards = [e for e in m.events if e.type == "card"]
    if cards:
        facts["cards"] = "cards: " + _per_side(m, lambda t: sum(c.team_id == t for c in cards))
    for team in (m.home, m.away):
        if any(c.team_id == team and c.card in ("red", "second_yellow") for c in cards):
            facts[f"down_to_ten_{'home' if team == m.home else 'away'}"] = (
                f"{m.clubs[team]} are down to 10 men")
    return FactsPack("situation", m.event, facts, roles.roles, sources)


def score_pack(m: Moment, roles: _Roles | None = None) -> FactsPack:
    roles = roles or _Roles()
    goals, sources = _goals_text(m, roles, with_xg=True)
    facts: dict = {"score_now": _score_text(m.score, m.home, m.away, m.clubs), "goals": goals}
    misses = sorted((s for s in m.shots if s.outcome != "goal"), key=lambda s: -_xg(s, m))[:2]
    if misses:
        facts["best_missed_chances"] = "; ".join(
            f"{roles('CHANCE', s.player_id)} ({m.clubs[s.team_id]}) in minute {_minute(s)}: "
            f"{_pct(_xg(s, m))} chance (model estimate, xG), {OUTCOME[s.outcome]}" for s in misses)
        sources += [s.event_id for s in misses]
    facts["chance_quality_total"] = "total xG (model estimate): " + _per_side(
        m, lambda t: f"{sum(_xg(s, m) for s in m.shots if s.team_id == t):.1f}")
    facts["goalkeeper_saves"] = "saves by the goalkeeper: " + _per_side(
        m, lambda t: sum(s.outcome == "saved" and s.team_id != t for s in m.shots))
    return FactsPack("score", m.event, facts, roles.roles, sources)


def team_stats_pack(m: Moment, roles: _Roles | None = None) -> FactsPack:
    passes = [e for e in m.events if e.type == "pass"]
    corners = [p for p in passes if getattr(p, "pass_type", None) == "corner"]
    cards = [e for e in m.events if e.type == "card"]
    on_target = [s for s in m.shots if s.outcome in ("goal", "saved")]

    def completed(t: str) -> str:
        mine = [p for p in passes if p.team_id == t]
        return f"{sum(p.outcome == 'complete' for p in mine)} of {len(mine)}"

    facts = {
        "score_now": _score_text(m.score, m.home, m.away, m.clubs),
        "shots": "shots: " + _per_side(m, lambda t: sum(s.team_id == t for s in m.shots)),
        "on_target": "on target: " + _per_side(m, lambda t: sum(s.team_id == t for s in on_target)),
        "chance_quality_total": "total xG (model estimate): " + _per_side(
            m, lambda t: f"{sum(_xg(s, m) for s in m.shots if s.team_id == t):.1f}"),
        "corners": "corners: " + _per_side(m, lambda t: sum(c.team_id == t for c in corners)),
        "cards": "cards: " + _per_side(m, lambda t: sum(c.team_id == t for c in cards)),
        "passes_completed": "passes completed: " + _per_side(m, completed),
    }
    return FactsPack("team_stats", m.event, facts, {}, [])


def player_tonight_pack(m: Moment, roles: _Roles | None = None) -> FactsPack:
    pid = m.player_id
    mine = [s for s in m.shots if s.player_id == pid]
    player = m.players.get(pid)
    feats = [shot_features(s, player) for s in mine]
    goals = sum(s.outcome == "goal" for s in mine)
    on = sum(s.outcome in ("goal", "saved") for s in mine)
    team = mine[0].team_id
    facts: dict = {
        "team": m.clubs[team],
        "shots_tonight": f"{len(mine)} shot(s) tonight, {on} on target, {goals} goal(s)",
    }
    best_i = max(range(len(mine)), key=lambda i: feats[i].xg)
    best = mine[best_i]
    facts["best_chance"] = (f"best chance in minute {_minute(best)}: {_pct(feats[best_i].xg)} "
                            f"(model estimate, xG), {OUTCOME[best.outcome]}")
    facts["fastest_shot"] = f"fastest shot {round(max(f.shot_speed_kmh for f in feats))} km/h"
    strong = [f.shot_speed_kmh for f in feats if f.body_group == "strong_foot"]
    norm = m.norm(pid) if m.norm else None
    if strong and norm:
        facts["speed_vs_norm"] = (f"average speed with his stronger foot tonight "
                                  f"{round(sum(strong) / len(strong))} km/h; his season norm "
                                  f"{round(norm)} km/h")
    if roles is not None:  # merged: name him in the facts with the shared placeholder
        facts = {"player": roles("PLAYER", pid), **facts}
        return FactsPack("player_tonight", m.event, facts, roles.roles,
                         [s.event_id for s in mine])
    return FactsPack("player_tonight", m.event, facts, {"PLAYER": pid},
                     [s.event_id for s in mine])


PACKS = {"situation": situation_pack, "score": score_pack, "team_stats": team_stats_pack,
         "player_tonight": player_tonight_pack}


def followup_pack(q: str, m: Moment) -> FactsPack:
    if not applicable(q, m):
        raise ValueError(f"question {q!r} does not apply to {m.id}")
    return PACKS[q](m)


def answer_key(moment_id: str, q: str, player_id: str | None, lang: str) -> str:
    return f"{moment_id}|{q}|{player_id or ''}|{lang}"
