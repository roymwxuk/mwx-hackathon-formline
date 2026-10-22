"""Tools for the Researcher: the fact sections, as functions an agent can call.

Each tool is a thin wrapper over a section builder in `analyst/sections.py` (no new fact
logic). A `ResearchSession` belongs to one typed question and holds:
- the **admission counter**: a call is admitted and charged *before* it runs, so the limit
  holds even inside one batch of parallel calls; invalid calls count too, so errors cannot
  loop forever;
- the **lookups**, keyed by tool + validated arguments: identical calls are deduplicated,
  calls with different arguments (two players, two windows) both survive;
- one **roles map** across all lookups, so PLAYER_A is the same player everywhere.
Bad arguments return an error the agent can act on and add no facts. Tool results carry a
placeholder → player id map, so the agent can chain (find the top scorer, then his games).
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from agent_framework import tool

from formline.analyst.facts import FactsPack
from formline.analyst.followups import Moment, _Roles, player_tonight_pack
from formline.analyst.sections import (
    BUILDERS,
    LABELS,
    MAX_RECENT,
    _with_player,
    match_info,
    player_info,
    player_recent,
    season_leaders,
    team_recent,
    team_tonight,
)
from formline.analyst.store import MatchContext

MAX_TOOL_CALLS = 5

# tool name -> the fact section it returns
SECTION_FOR_TOOL = {
    "get_match_info": "match_info", "get_match_so_far": "situation",
    "get_score_explanation": "score", "get_team_comparison": "team_stats",
    "get_team_tonight": "team_tonight", "get_player_profile": "player_info",
    "get_player_shooting_tonight": "player_tonight", "get_best_chances": "chances",
    "get_discipline": "discipline", "get_last_10_minutes": "recent",
    "get_season_leaders": "season_leaders", "get_player_recent": "player_recent",
    "get_team_recent": "team_recent",
}
TOOL_FOR_SECTION = {v: k for k, v in SECTION_FOR_TOOL.items()}


@dataclass
class Lookup:
    tool: str
    args: dict
    section: str
    facts: dict
    sources: list[str]


@dataclass
class ResearchSession:
    m: Moment
    ctx: MatchContext
    norm: Callable[[str], float | None] | None = None
    max_calls: int = MAX_TOOL_CALLS
    roles: _Roles = field(default_factory=_Roles)
    lookups: dict[str, Lookup] = field(default_factory=dict)
    steps: list[dict] = field(default_factory=list)  # every attempted call, for the viewer and logs
    calls: int = 0

    # ---------- checks ----------

    def _squad(self) -> list[str]:
        return [pid for pid, p in self.m.players.items() if p.club_id in (self.m.home, self.m.away)]

    def _shooters(self) -> set[str]:
        return {s.player_id for s in self.m.shots}

    def _check(self, name: str, args: dict) -> str | None:
        club, pid, n = args.get("club_id"), args.get("player_id"), args.get("n")
        if "club_id" in args and club not in (self.m.home, self.m.away):
            return f"club_id must be {self.m.home} or {self.m.away}, got {club!r}"
        if "player_id" in args and pid not in self._squad():
            return f"player_id must be a player of either squad (see PLAYERS), got {pid!r}"
        if name == "get_player_shooting_tonight" and pid not in self._shooters():
            return "that player has not taken a shot tonight; use get_player_profile"
        if "n" in args and (not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= MAX_RECENT):
            return f"n must be a whole number of games from 1 to {MAX_RECENT}, got {n!r}"
        return None

    # ---------- running a tool ----------

    def call(self, name: str, args: dict, build: Callable[[], tuple[dict, list[str]]]) -> str:
        """Admit, validate, build, store; returns the tool result for the model (JSON)."""
        if self.calls >= self.max_calls:
            self.steps.append({"tool": name, "args": args, "ok": False, "error": "limit"})
            return json.dumps({"error": f"tool call limit of {self.max_calls} reached; stop and "
                                        "reply with the final JSON"})
        self.calls += 1  # admitted (and charged) before running, valid or not
        problem = self._check(name, args)
        if problem:
            self.steps.append({"tool": name, "args": args, "ok": False, "error": problem})
            return json.dumps({"error": problem})
        key = f"{name}({json.dumps(args, sort_keys=True)})"
        if key not in self.lookups:
            facts, sources = build()
            self.lookups[key] = Lookup(name, args, SECTION_FOR_TOOL[name], facts, sources)
        lookup = self.lookups[key]
        self.steps.append({"tool": name, "args": args, "ok": True})
        named = {r: {"id": pid, "name": self.ctx.league.players.get(pid, (pid, pid))[0]}
                 for r, pid in self.roles.roles.items() if r in json.dumps(lookup.facts)}
        return json.dumps({"facts": lookup.facts, "players": named}, ensure_ascii=False)

    # ---------- the gathered facts ----------

    def pack(self) -> FactsPack:
        """Every successful lookup, keyed by tool and arguments, with one roles map."""
        facts: dict = {}
        sources: list[str] = []
        for i, lk in enumerate(self.lookups.values(), start=1):
            facts[f"lookup_{i}_{lk.section}"] = lk.facts
            sources += [s for s in lk.sources if s not in sources]
        return FactsPack("free", self.m.event, facts, self.roles.roles, sources)

    def label(self, lang: str) -> str:
        """e.g. "Season leaders → Reyner: last 3 games"."""
        parts = []
        for lk in self.lookups.values():
            pid, club = lk.args.get("player_id"), lk.args.get("club_id")
            player = None
            if pid:
                en, ja = self.ctx.league.players[pid]
                player = en.split()[-1] if lang == "en" else ja.split("・")[-1]
            parts.append(LABELS[lang][lk.section].format(club=self.ctx.clubs.get(club, ""),
                                                         player=player or "",
                                                         n=lk.args.get("n", 3)))
        return " → ".join(parts)

    # ---------- the tools ----------

    def tools(self) -> list:
        s, m, ctx = self, self.m, self.ctx

        def plain(section: str):
            return lambda: BUILDERS[section](m, s.roles)

        @tool(name="get_match_info", description="The fixture: venue, weather, attendance, referee, "
              "kick-off, season and matchday, both clubs' record before tonight.")
        def get_match_info() -> str:
            return s.call("get_match_info", {}, lambda: match_info(m, ctx.info, ctx.records))

        @tool(name="get_match_so_far", description="Tonight: score, goals, shots, cards so far.")
        def get_match_so_far() -> str:
            return s.call("get_match_so_far", {}, plain("situation"))

        @tool(name="get_score_explanation", description="Tonight: why the score is what it is: "
              "goals and their chance quality, best missed chances, saves.")
        def get_score_explanation() -> str:
            return s.call("get_score_explanation", {}, plain("score"))

        @tool(name="get_team_comparison", description="Tonight: both teams side by side: shots, "
              "on target, xG, corners, cards, passes.")
        def get_team_comparison() -> str:
            return s.call("get_team_comparison", {}, plain("team_stats"))

        @tool(name="get_team_tonight", description="Tonight: one team in detail: goals, shots by "
              "outcome, xG, best missed chances, the opposing keeper's saves, corners, cards.")
        def get_team_tonight(club_id: str) -> str:
            return s.call("get_team_tonight", {"club_id": club_id},
                          lambda: team_tonight(m, s.roles, club_id))

        @tool(name="get_player_profile", description="Any squad player: club, shirt number, "
              "position, foot, nationality, birth date and place, season before tonight, tonight.")
        def get_player_profile(player_id: str) -> str:
            return s.call("get_player_profile", {"player_id": player_id},
                          lambda: player_info(m, s.roles, player_id, ctx.player_seasons,
                                              s.norm or m.norm))

        @tool(name="get_player_shooting_tonight", description="Tonight, for a player who has "
              "shot: his shots, on target, goals, best chance, fastest shot, speed vs his norm.")
        def get_player_shooting_tonight(player_id: str) -> str:
            def build():
                pack = player_tonight_pack(_with_player(m, player_id), s.roles)
                return pack.facts, pack.source_event_ids
            return s.call("get_player_shooting_tonight", {"player_id": player_id}, build)

        @tool(name="get_best_chances", description="Tonight: the best chances of both teams.")
        def get_best_chances() -> str:
            return s.call("get_best_chances", {}, plain("chances"))

        @tool(name="get_discipline", description="Tonight: fouls and cards per team, who was booked.")
        def get_discipline() -> str:
            return s.call("get_discipline", {}, plain("discipline"))

        @tool(name="get_last_10_minutes", description="Tonight: shots, corners, cards in the last "
              "10 minutes.")
        def get_last_10_minutes() -> str:
            return s.call("get_last_10_minutes", {}, plain("recent"))

        @tool(name="get_season_leaders", description="Before tonight, for the two clubs of this "
              "match only: top scorers, most assists, most shots.")
        def get_season_leaders() -> str:
            return s.call("get_season_leaders", {},
                          lambda: season_leaders(m, s.roles, ctx.player_seasons))

        @tool(name="get_player_recent", description="Before tonight: a squad player's last n games "
              "(n 1-5): opponent, result, goals, assists, shots, passes, totals.")
        def get_player_recent(player_id: str, n: int = 3) -> str:
            return s.call("get_player_recent", {"player_id": player_id, "n": n},
                          lambda: player_recent(m, s.roles, player_id, n, ctx.history))

        @tool(name="get_team_recent", description="Before tonight: one of the two clubs' last n "
              "games (n 1-5): opponent, home or away, result, score, scorers, totals.")
        def get_team_recent(club_id: str, n: int = 3) -> str:
            return s.call("get_team_recent", {"club_id": club_id, "n": n},
                          lambda: team_recent(m, s.roles, club_id, n, ctx.history))

        @tool(name="find_player", description="Find squad players by (part of) a name: id, club, "
              "shirt number. Adds no facts.")
        def find_player(name: str) -> str:
            if s.calls >= s.max_calls:
                return json.dumps({"error": "tool call limit reached; reply with the final JSON"})
            s.calls += 1
            s.steps.append({"tool": "find_player", "args": {"name": name}, "ok": True})
            q = name.casefold().strip()
            hits = [{"id": pid, "name": ctx.league.players[pid][0], "name_ja": ctx.league.players[pid][1],
                     "club": ctx.clubs[m.players[pid].club_id], "shirt": m.players[pid].shirt_number}
                    for pid in s._squad()
                    if q and (q in ctx.league.players[pid][0].casefold() or q in ctx.league.players[pid][1])]
            return json.dumps({"candidates": hits[:6]}, ensure_ascii=False)

        @tool(name="find_club", description="Find a club of this match by (part of) its name or "
              "short name: id and name. Adds no facts.")
        def find_club(name: str) -> str:
            if s.calls >= s.max_calls:
                return json.dumps({"error": "tool call limit reached; reply with the final JSON"})
            s.calls += 1
            s.steps.append({"tool": "find_club", "args": {"name": name}, "ok": True})
            q = name.casefold().strip()
            hits = [{"id": cid, "name": ctx.clubs[cid]} for cid in (m.home, m.away)
                    if q and (q in ctx.clubs[cid].casefold() or q == ctx.league.clubs[cid][1].casefold())]
            return json.dumps({"candidates": hits}, ensure_ascii=False)

        return [get_match_info, get_match_so_far, get_score_explanation, get_team_comparison,
                get_team_tonight, get_player_profile, get_player_shooting_tonight,
                get_best_chances, get_discipline, get_last_10_minutes, get_season_leaders,
                get_player_recent, get_team_recent, find_player, find_club]
