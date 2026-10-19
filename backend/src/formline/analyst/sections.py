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
                  "which team is at home, weather and temperature, attendance, the referee, "
                  "both clubs' season record before tonight",
    "situation": "the score, the goals and the shots so far, the last 10 minutes in brief, cards",
    "score": "why the score is what it is: goals and their chance quality, the best missed "
             "chances, the goalkeepers' saves",
    "team_stats": "both teams side by side: shots, on target, xG, corners, cards, passes",
    "team_tonight": "one team in detail (needs club_id): its goals, shots by outcome, xG, its "
                    "best missed chances, the opposing goalkeeper's saves, corners, cards",
    "player_tonight": "one player who has shot (needs player_id): his shots, on target, goals, "
                      "best chance, fastest shot, speed vs his own season norm",
    "player_info": "any player of either squad (needs player_id): club, shirt number, "
                   "position, preferred foot, nationality (country), birthday/date of birth, "
                   "birthplace (city and country where born), "
                   "his season before tonight (appearances, goals, "
                   "assists, shots, shot-speed norm) and what he has done tonight",
    "chances": "the best chances of the match so far, both teams, by chance quality",
    "discipline": "fouls and cards per team, and who was booked or sent off",
    "recent": "the last 10 minutes: shots, corners and cards per team, and each shot",
    # history before tonight (the season so far), from the past matches
    "season_leaders": "both clubs' season leaders before tonight: top scorers, most assists, "
                      "most shots",
    "player_recent": "one player's last n games before tonight (needs player_id and n, 1–5): "
                     "per game the opponent, result, goals, assists, shots, passes, plus totals",
    "team_recent": "one team's last n games before tonight (needs club_id and n, 1–5): per "
                   "game the opponent, home or away, result, score and scorers, plus totals",
}
MAX_RECENT = 5  # games back for player_recent and team_recent

LABELS = {
    "en": {"match_info": "Match info", "situation": "Match so far", "score": "Score", "team_stats": "Team comparison",
           "team_tonight": "{club} tonight", "player_tonight": "{player} tonight",
           "player_info": "About {player}",
           "chances": "Best chances", "discipline": "Fouls and cards",
           "recent": "Last 10 minutes", "season_leaders": "Season leaders",
           "player_recent": "{player}: last {n} games", "team_recent": "{club}: last {n} games"},
    "ja": {"match_info": "試合情報", "situation": "試合の流れ", "score": "スコア", "team_stats": "両チーム比較",
           "team_tonight": "今夜の{club}", "player_tonight": "今夜の{player}",
           "player_info": "{player}について",
           "chances": "決定機", "discipline": "ファウルとカード", "recent": "直近10分",
           "season_leaders": "今季のチーム内上位", "player_recent": "{player}の直近{n}試合",
           "team_recent": "{club}の直近{n}試合"},
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
    facts: dict = {
        "fixture": f"{home} (home) against {away} (away)",
        "venue": f"played at {info['venue']}, the home ground of {home}",
    }
    c = info.get("conditions")
    if c:
        facts["weather"] = f"{c['weather']}, {c['temperature_c']} °C at kick-off"
        facts["attendance"] = f"{c['attendance']:,} spectators (capacity {c['capacity']:,})"
        facts["referee"] = f"referee {c['referee']}"
    facts |= {
        "kick_off": f"kick-off {kickoff:%H:%M} UTC on {kickoff.day} {kickoff:%B %Y}",
        "now": f"minute {_minute(now)}, {'first' if now.period == 1 else 'second'} half",
        "season": f"season {info['season']}, matchday {info['matchday']}",
        "competition": "a synthetic league of six fictional clubs",
        "season_so_far": "before tonight: " + "; ".join(
            _record_text(m.clubs[club], records.get(club)) for club in (m.home, m.away)),
        "not_in_the_data": ("team news, injuries and the referee's reasons for decisions are "
                            "not in the data"),
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
        "nationality": f"nationality: {p.nationality}" if p.nationality else "nationality not recorded",
        "date_of_birth": (f"date of birth: {p.date_of_birth.isoformat()} (YYYY-MM-DD)"
                          if p.date_of_birth else "date of birth not recorded"),
        "birthplace": f"born in {p.birthplace}" if p.birthplace else "birthplace not recorded",
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
    facts["not_in_the_data"] = "age, height, contract and injuries are not in the data"
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
              norm: Callable[[str], float | None] | None = None,
              history: list | None = None, n: int | None = None) -> FactsPack:
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
        elif sec == "season_leaders":
            part, src = season_leaders(m, roles, seasons or {})
        elif sec == "player_recent":
            part, src = player_recent(m, roles, player_id, n or 3, history or [])
        elif sec == "team_recent":
            part, src = team_recent(m, roles, club_id, n or 3, history or [])
        elif sec == "player_tonight":
            pack = player_tonight_pack(_with_player(m, player_id), roles)
            part, src = pack.facts, pack.source_event_ids
        else:
            part, src = BUILDERS[sec](m, roles)
        facts[sec] = part
        sources += [s for s in src if s not in sources]
    return FactsPack("free", m.event, facts, roles.roles, sources)


def _game_date(row: dict) -> str:
    d = datetime.fromisoformat(row["kickoff_at"])
    return f"{d.day} {d:%b}"


def _result(row: dict, club: str) -> tuple[str, int, int, str]:
    """(won/drawn/lost, goals for, goals against, home/away) for `club` in a past match."""
    home = row["home"] == club
    gf, ga = (row["home_goals"], row["away_goals"]) if home else (row["away_goals"], row["home_goals"])
    return ("won" if gf > ga else "drawn" if gf == ga else "lost"), gf, ga, ("home" if home else "away")


def season_leaders(m: Moment, roles: _Roles, seasons: dict) -> tuple[dict, list[str]]:
    """Each club's top scorers, assists and shots before tonight (ties named together)."""
    facts: dict = {}
    for side, club in (("home", m.home), ("away", m.away)):
        squad = [pid for pid, p in m.players.items() if p.club_id == club]

        def top(stat: str, k: int = 3, squad: list[str] = squad) -> str:
            ranked = sorted((pid for pid in squad if seasons.get(pid, {}).get(stat)),
                            key=lambda pid: -seasons[pid][stat])[:k]
            return ", ".join(f"{roles('PLAYER', pid)} {seasons[pid][stat]}" for pid in ranked) or "none"
        goals = [seasons.get(pid, {}).get("goals", 0) for pid in squad]
        best = max(goals, default=0)
        leaders = [pid for pid in squad if best and seasons.get(pid, {}).get("goals", 0) == best]
        facts[f"{side}_club"] = m.clubs[club]
        facts[f"{side}_top_scorer"] = (
            f"top scorer: {' and '.join(roles('PLAYER', pid) for pid in leaders)} with {best} goal(s)"
            if leaders else "no goals scored before tonight")
        facts[f"{side}_goals"] = "most goals: " + top("goals")
        facts[f"{side}_assists"] = "most assists: " + top("assists")
        facts[f"{side}_shots"] = "most shots: " + top("shots")
    facts["period"] = "the season before tonight's match"
    return facts, []


def player_recent(m: Moment, roles: _Roles, pid: str, n: int, history: list[dict]) -> tuple[dict, list[str]]:
    p = m.players[pid]
    games = [r for r in history if pid in r["players"]][-n:]
    facts: dict = {"player": roles("PLAYER", pid), "club": m.clubs[p.club_id]}
    if not games:
        facts["games"] = "no appearances before tonight"
        return facts, []
    lines, tot = [], {"goals": 0, "assists": 0, "shots": 0, "on_target": 0}
    for r in games:
        s = r["players"][pid]
        res, gf, ga, venue = _result(r, p.club_id)
        opp = m.clubs[r["away"] if venue == "home" else r["home"]]
        lines.append(f"{_game_date(r)}: {venue} against {opp}, {res} {gf}–{ga}: {s['goals']} goal(s), "
                     f"{s['assists']} assist(s), {s['shots']} shot(s), {s['on_target']} on target, "
                     f"{s['passes_completed']} of {s['passes']} passes completed")
        for k in tot:
            tot[k] += s[k]
    facts["games"] = "; ".join(lines)
    facts["totals"] = (f"over these {len(games)} game(s): {tot['goals']} goal(s), {tot['assists']} "
                       f"assist(s), {tot['shots']} shot(s), {tot['on_target']} on target")
    if len(games) < n:
        facts["note"] = f"only {len(games)} appearance(s) before tonight"
    facts["not_in_the_data"] = "minutes played and player ratings are not in the data"
    return facts, []


def team_recent(m: Moment, roles: _Roles, club: str, n: int, history: list[dict]) -> tuple[dict, list[str]]:
    games = [r for r in history if club in (r["home"], r["away"])][-n:]
    facts: dict = {"team": m.clubs[club]}
    if not games:
        facts["games"] = "no games before tonight"
        return facts, []
    lines, tally = [], {"won": 0, "drawn": 0, "lost": 0, "for": 0, "against": 0}
    for r in games:
        res, gf, ga, venue = _result(r, club)
        opp = m.clubs[r["away"] if venue == "home" else r["home"]]
        scorers = [pid for pid, team, _ in r["scorers"] if team == club]
        named = ", ".join(roles("PLAYER", pid) for pid in dict.fromkeys(scorers)) or "no scorers"
        lines.append(f"{_game_date(r)}: {venue} against {opp}, {res} {gf}–{ga} (scorers: {named})")
        tally[res] += 1
        tally["for"] += gf
        tally["against"] += ga
    facts["games"] = "; ".join(lines)
    facts["totals"] = (f"over these {len(games)} game(s): {tally['won']} won, {tally['drawn']} drawn, "
                       f"{tally['lost']} lost, goals {tally['for']} for and {tally['against']} against")
    return facts, []


def _with_player(m: Moment, player_id: str | None) -> Moment:
    return replace(m, player_id=player_id, _shots=None)


def label(sections: list[str], lang: str, club: str | None, player: str | None,
          n: int | None = None) -> str:
    """e.g. "Northgate Rovers tonight · Best chances"."""
    return " · ".join(LABELS[lang][s].format(club=club or "", player=player or "", n=n or 3)
                      for s in sections)
