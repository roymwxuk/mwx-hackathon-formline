"""Fact sections for typed questions: "RAG over computed facts".

A typed question is answered from 1–3 of these sections, chosen by the Question Router
(`analyst/router.py`). Every section is computed by code from the events known at the
comment's moment, never by a model, so the Analyst can answer the viewer's own question
freely while the verifier still checks every number and name against these facts. The four
catalog questions (`analyst/followups.py`) are sections too; merged sections share one set of
player placeholders, so SCORER_A means the same player everywhere.
"""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from formline.analyst.facts import OUTCOME, FactsPack
from formline.analyst.followups import (
    Moment,
    _key,
    _minute,
    _pct,
    _per_side,
    _Roles,
    _xg,
    player_tonight_pack,
    score_pack,
    situation_pack,
    team_stats_pack,
)

MAX_SECTIONS = 3

# What each section holds: the Router reads these to choose.
SECTIONS = {
    "match_info": "the fixture: competition, season and matchday, the venue, the kick-off time, "
                  "which team is at home, both clubs' season record before tonight",
    "situation": "the score, the goals and the shots so far, the last 10 minutes in brief, cards",
    "score": "why the score is what it is: goals and their chance quality, the best missed "
             "chances, the goalkeepers' saves",
    "team_stats": "both teams side by side: shots, on target, xG, corners, cards, passes",
    "team_tonight": "one team in detail (needs club_id): its goals, shots by outcome, xG, its "
                    "best missed chances, the opposing goalkeeper's saves, corners, cards",
    "player_tonight": "one player who has shot (needs player_id): his shots, on target, goals, "
                      "best chance, fastest shot, speed vs his own season norm",
    "player_info": "any player of either squad (needs player_id): club, shirt number, "
                   "position, preferred foot, his season before tonight (appearances, goals, "
                   "assists, shots, shot-speed norm) and what he has done tonight",
    "chances": "the best chances of the match so far, both teams, by chance quality",
    "discipline": "fouls and cards per team, and who was booked or sent off",
    "recent": "the last 10 minutes: shots, corners and cards per team, and each shot",
}

LABELS = {
    "en": {"match_info": "Match info", "situation": "Match so far", "score": "Score", "team_stats": "Team comparison",
           "team_tonight": "{club} tonight", "player_tonight": "{player} tonight",
           "player_info": "About {player}",
           "chances": "Best chances", "discipline": "Fouls and cards",
           "recent": "Last 10 minutes"},
    "ja": {"match_info": "試合情報", "situation": "試合の流れ", "score": "スコア", "team_stats": "両チーム比較",
           "team_tonight": "今夜の{club}", "player_tonight": "今夜の{player}",
           "player_info": "{player}について",
           "chances": "決定機", "discipline": "ファウルとカード", "recent": "直近10分"},
}


def _is_corner(e) -> bool:
    return e.type == "pass" and getattr(e, "pass_type", None) == "corner"


def _chance_line(s, m: Moment, roles: _Roles) -> str:
    return (f"{roles('CHANCE', s.player_id)} ({m.clubs[s.team_id]}) in minute {_minute(s)}: "
            f"{_pct(_xg(s, m))} chance (model estimate, xG), {OUTCOME[s.outcome]}")


def team_tonight(m: Moment, roles: _Roles, club: str) -> tuple[dict, list[str]]:
    opp = m.away if club == m.home else m.home
    mine = [s for s in m.shots if s.team_id == club]
    goals = [s for s in mine if s.outcome == "goal"]
    by = {o: sum(s.outcome == o for s in mine) for o in OUTCOME}
    facts: dict = {
        "team": m.clubs[club],
        "goals": ("; ".join(f"{roles('SCORER', g.player_id)} in minute {_minute(g)}" for g in goals)
                  if goals else "no goals yet"),
        "shots": (f"{len(mine)} shot(s): {by['goal']} scored, {by['saved']} saved, "
                  f"{by['blocked']} blocked, {by['off_target'] + by['post']} off target or post"),
        "chance_quality_total": f"total xG {sum(_xg(s, m) for s in mine):.1f} (model estimate)",
        "saves_against": f"the {m.clubs[opp]} goalkeeper made {by['saved']} save(s)",
        "corners": f"{sum(_is_corner(e) and e.team_id == club for e in m.events)} corner(s)",
        "cards": f"{sum(e.type == 'card' and e.team_id == club for e in m.events)} card(s)",
    }
    misses = sorted((s for s in mine if s.outcome != "goal"), key=lambda s: -_xg(s, m))[:3]
    if misses:
        facts["best_missed_chances"] = "; ".join(_chance_line(s, m, roles) for s in misses)
    return facts, [s.event_id for s in mine]


def chances(m: Moment, roles: _Roles) -> tuple[dict, list[str]]:
    best = sorted(m.shots, key=lambda s: -_xg(s, m))[:5]
    if not best:
        return {"best_chances": "no shots yet"}, []
    return ({"best_chances": "; ".join(_chance_line(s, m, roles) for s in best)},
            [s.event_id for s in best])


def discipline(m: Moment, roles: _Roles) -> tuple[dict, list[str]]:
    fouls = [e for e in m.events if e.type == "foul_committed"]
    cards = [e for e in m.events if e.type == "card"]
    kind = {"yellow": "yellow card", "second_yellow": "second yellow card, sent off",
            "red": "straight red card, sent off"}
    facts = {
        "fouls": "fouls: " + _per_side(m, lambda t: sum(f.team_id == t for f in fouls)),
        "cards": "cards: " + _per_side(m, lambda t: sum(c.team_id == t for c in cards)),
        "booked": ("; ".join(f"{roles('BOOKED', c.player_id)} ({m.clubs[c.team_id]}) "
                             f"{kind[c.card]} in minute {_minute(c)}" for c in cards)
                   if cards else "nobody booked yet"),
        "not_in_the_data": "the feed does not record who was fouled or why",
    }
    return facts, [c.event_id for c in cards]


def recent(m: Moment, roles: _Roles) -> tuple[dict, list[str]]:
    now = max(m.events, key=_key)

    def last10(e) -> bool:
        return e.period == now.period and now.match_clock_ms - e.match_clock_ms <= 10 * 60_000

    shots = [s for s in m.shots if last10(s)]
    corners = [e for e in m.events if _is_corner(e) and last10(e)]
    cards = [e for e in m.events if e.type == "card" and last10(e)]
    facts = {
        "window": f"minutes {max(1, _minute(now) - 10)} to {_minute(now)}",
        "shots": "shots: " + _per_side(m, lambda t: sum(s.team_id == t for s in shots)),
        "corners": "corners: " + _per_side(m, lambda t: sum(c.team_id == t for c in corners)),
        "cards": "cards: " + _per_side(m, lambda t: sum(c.team_id == t for c in cards)),
    }
    if shots:
        facts["each_shot"] = "; ".join(
            f"{roles('SHOT_BY', s.player_id)} ({m.clubs[s.team_id]}) in minute {_minute(s)}, "
            f"{OUTCOME[s.outcome]}" for s in shots)
    return facts, [s.event_id for s in shots]


def _record_text(club: str, r: dict | None) -> str:
    if not r:
        return f"{club}: no matches before tonight"
    return (f"{club}: {r['played']} played, {r['won']} won, {r['drawn']} drawn, {r['lost']} lost, "
            f"goals {r['goals_for']} for and {r['goals_against']} against")


def match_info(m: Moment, info: dict, records: dict) -> tuple[dict, list[str]]:
    """The fixture, from the match list (not the events), and both clubs' season so far."""
    home, away = m.clubs[m.home], m.clubs[m.away]
    kickoff = datetime.fromisoformat(str(info["kickoff_at"]))
    now = max(m.events, key=_key)
    facts = {
        "competition": "a synthetic league of six fictional clubs",
        "season": f"season {info['season']}, matchday {info['matchday']}",
        "fixture": f"{home} (home) against {away} (away)",
        "venue": f"played at {info['venue']}, the home ground of {home}",
        "kick_off": f"kick-off {kickoff:%H:%M} UTC on {kickoff.day} {kickoff:%B %Y}",
        "now": f"minute {_minute(now)}, {'first' if now.period == 1 else 'second'} half",
        "season_so_far": "before tonight: " + "; ".join(
            _record_text(m.clubs[c], records.get(c)) for c in (m.home, m.away)),
        "not_in_the_data": "attendance, weather, the referee and team news are not in the data",
    }
    return facts, []


POSITION = {"GK": "goalkeeper", "RB": "right back", "CB": "centre back", "LB": "left back",
            "DM": "defensive midfielder", "CM": "central midfielder",
            "AM": "attacking midfielder", "RW": "right winger", "LW": "left winger",
            "ST": "striker"}


def player_info(m: Moment, roles: _Roles, pid: str, seasons: dict,
                norm: Callable[[str], float | None] | None) -> tuple[dict, list[str]]:
    """A player's public profile (never the generator's hidden ratings), his season before
    tonight from the history, and his involvement tonight so far."""
    p = m.players[pid]
    s = seasons.get(pid, {"appearances": 0, "goals": 0, "assists": 0, "shots": 0, "on_target": 0})
    mine = [e for e in m.events if getattr(e, "player_id", None) == pid]
    passes = [e for e in mine if e.type == "pass"]
    shots = [e for e in mine if e.type == "shot"]
    won = [e for e in mine if e.type in ("duel", "interception", "ball_recovery")]
    facts: dict = {
        "player": roles("PLAYER", pid),
        "club": m.clubs[p.club_id],
        "profile": (f"shirt number {p.shirt_number}, {POSITION.get(p.position, p.position)}, "
                    f"{p.preferred_foot}-footed"),
        "season_before_tonight": (f"{s['appearances']} appearance(s), {s['goals']} goal(s), "
                                  f"{s['assists']} assist(s), {s['shots']} shot(s), "
                                  f"{s['on_target']} on target"),
    }
    speed = norm(pid) if norm else None
    if speed:
        facts["shot_speed_norm"] = (f"season shot-speed norm {round(speed)} km/h with his "
                                    "stronger foot (model estimate)")
    subs = [e for e in m.events if e.type == "substitution" and pid in (e.player_off_id, e.player_on_id)]
    if subs:
        sub = subs[-1]
        facts["substitution"] = (f"{'came on' if sub.player_on_id == pid else 'was substituted'} "
                                 f"in minute {_minute(sub)}")
    if mine or subs:
        facts["tonight"] = (f"tonight so far: {sum(e.outcome == 'complete' for e in passes)} of "
                            f"{len(passes)} passes completed, {len(shots)} shot(s), "
                            f"{sum(e.type == 'foul_committed' for e in mine)} foul(s), "
                            f"{len(won)} duel(s), interception(s) or recoveries")
    else:
        facts["tonight"] = "not involved tonight so far (no events of his yet)"
    facts["not_in_the_data"] = "age, height, nationality, contract and injuries are not in the data"
    return facts, [e.event_id for e in shots]


def _from_pack(build: Callable[..., FactsPack]):
    def section(m: Moment, roles: _Roles) -> tuple[dict, list[str]]:
        pack = build(m, roles)
        return pack.facts, pack.source_event_ids
    return section


BUILDERS = {"situation": _from_pack(situation_pack), "score": _from_pack(score_pack),
            "team_stats": _from_pack(team_stats_pack), "chances": chances,
            "discipline": discipline, "recent": recent}


def facts_for(sections: list[str], m: Moment, club_id: str | None = None,
              player_id: str | None = None, info: dict | None = None,
              records: dict | None = None, seasons: dict | None = None,
              norm: Callable[[str], float | None] | None = None) -> FactsPack:
    """The merged facts of `sections` (one sub-dict each), with one shared roles map."""
    roles = _Roles()
    facts: dict = {}
    sources: list[str] = []
    for sec in sections:
        if sec == "match_info":
            part, src = match_info(m, info or {}, records or {})
        elif sec == "player_info":
            part, src = player_info(m, roles, player_id, seasons or {}, norm or m.norm)
        elif sec == "team_tonight":
            part, src = team_tonight(m, roles, club_id)
        elif sec == "player_tonight":
            pack = player_tonight_pack(_with_player(m, player_id), roles)
            part, src = pack.facts, pack.source_event_ids
        else:
            part, src = BUILDERS[sec](m, roles)
        facts[sec] = part
        sources += [s for s in src if s not in sources]
    return FactsPack("free", m.event, facts, roles.roles, sources)


def _with_player(m: Moment, player_id: str | None) -> Moment:
    return replace(m, player_id=player_id, _shots=None)


def label(sections: list[str], lang: str, club: str | None, player: str | None) -> str:
    """e.g. "Northgate Rovers tonight · Best chances"."""
    return " · ".join(LABELS[lang][s].format(club=club or "", player=player or "")
                      for s in sections)
