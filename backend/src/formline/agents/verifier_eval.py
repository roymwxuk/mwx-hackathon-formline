"""Verifier catch rate: inject one error into valid narrations and count what's caught.

Base texts are the template narrator's output for every live-match insight in all
four variants (EN/JA × casual/analyst), which the verifier must pass (false-positive
check). Each mutator injects exactly one error. A mutation counts as caught when the
verifier rejects the mutated text.

Misses are reported, not hidden: e.g. replacing "his norm is 92 km/h" with
"84 km/h" uses a real speed fact (this shot's speed) in the wrong role, which a
number-matching verifier cannot see.

Run: `uv run python -m formline.agents.verifier_eval`
"""

import argparse
import random
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from formline.agents.catalog import TEMPLATE_FOR_INSIGHT
from formline.agents.template_narrator import names_for, narrate
from formline.agents.verifier import (
    NUMBER,
    LeagueNames,
    VerifyContext,
    allowed_numbers,
    league_names,
    verify,
)
from formline.engine.engine import BaselineEngine
from formline.engine.ingest import Applied
from formline.engine.insights import Insight, InsightCreated
from formline.engine.log import current_events
from formline.engine.pipeline import LivePipeline
from formline.generator.season import generate_season

VARIANTS = [(lang, mode) for lang in ("en", "ja") for mode in ("casual", "analyst")]


@dataclass(frozen=True)
class Case:
    insight: Insight
    lang: str
    mode: str
    slots: dict
    ctx: VerifyContext


@dataclass
class World:
    cases: list[Case]
    league: LeagueNames
    others: dict[str, list[str]]  # player_id -> other players' names to inject (EN, JA)
    clubs: dict[str, list[str]]  # player_id -> other clubs' names
    foreign_numbers: list[str]  # numbers from other insights' facts


Mutator = Callable[[Case, World, random.Random], dict | None]


# ---------- mutators: each returns mutated slots, or None if not applicable ----------

def _numbers_in(slots: dict) -> list[tuple[str, re.Match]]:
    return [(k, m) for k in ("headline", "sub") for m in NUMBER.finditer(slots[k])]


def _replace_number(case: Case, rng: random.Random, make: Callable[[str], str | None]):
    found = _numbers_in(case.slots)
    rng.shuffle(found)
    for key, m in found:
        new = make(m.group(0))
        if new is None or new == m.group(0):
            continue
        text = case.slots[key]
        return case.slots | {key: text[:m.start()] + new + text[m.end():]}
    return None


def _fmt_like(old: str, value: float) -> str:
    decimals = len(old.split(".")[1]) if "." in old else 0
    return f"{value:.{decimals}f}"


def num_off_by_one(case, world, rng):
    return _replace_number(case, rng, lambda s: _fmt_like(s, float(s) + (1 if "." not in s
                                                                          else 0.1)))


def num_scaled(case, world, rng):
    def make(s):
        v = float(s)
        new = _fmt_like(s, v * 1.1)
        return new if new != s else _fmt_like(s, v + 2)
    return _replace_number(case, rng, make)


def num_swapped_digits(case, world, rng):
    def make(s):
        digits = s.replace(".", "")
        if len(set(digits)) < 2:
            return None
        whole = s.split(".")[0]
        if len(whole) >= 2 and whole[0] != whole[1]:
            return whole[1] + whole[0] + s[len(whole):]
        return None
    return _replace_number(case, rng, make)


def num_foreign(case, world, rng):
    own = allowed_numbers(case.ctx.facts)
    pool = [n for n in world.foreign_numbers if n not in own]
    if not pool:
        return None
    pick = rng.choice(pool)
    return _replace_number(case, rng, lambda s: pick if ("." in s) == ("." in pick) else None)


def _own_name(case: Case, world: World) -> str:
    en, ja = world.league.players[case.insight.player_id]
    return ja.split("・")[-1] if case.lang == "ja" and "・" in ja else (
        ja if case.lang == "ja" else en.split()[-1])


def _swap_name(case, world, rng, pool_key: str):
    own = _own_name(case, world)
    candidates = world.others[f"{case.insight.player_id}:{pool_key}:{case.lang}"]
    if own not in case.slots["headline"] or not candidates:
        return None
    return case.slots | {"headline": case.slots["headline"].replace(own, rng.choice(candidates))}


def entity_teammate(case, world, rng):
    return _swap_name(case, world, rng, "team")


def entity_opponent(case, world, rng):
    return _swap_name(case, world, rng, "opp")


def entity_club(case, world, rng):
    club = rng.choice(world.clubs[case.insight.player_id])
    addition = f" vs {club}." if case.lang == "en" else f"（vs {club}）"
    return case.slots | {"sub": case.slots["sub"].rstrip(".") + addition}


MARKERS = (" (model estimate)", " (estimate)", "Est. ", "est. ", " Model estimates.",
           "（推定）", "数値はモデルによる推定値です。", "推定", "モデルによる", "about ", "約")


def drop_estimate_marker(case, world, rng):
    text = f"{case.slots['headline']} {case.slots['sub']}"
    triggers = ("%", "percentile", "pct", "chance", "パーセンタイル", "確率")
    if not any(t in text for t in triggers):
        return None
    out = dict(case.slots)
    for key in ("headline", "sub"):
        for m in MARKERS:
            out[key] = out[key].replace(m, "")
    return out if out != case.slots else None


def add_certainty(case, world, rng):
    claim = " He will score next time." if case.lang == "en" else "次は必ず決める。"
    return case.slots | {"sub": case.slots["sub"] + claim}


def over_length(case, world, rng):
    pad = " really, truly remarkable" if case.lang == "en" else "、本当に驚くべき一撃"
    return case.slots | {"headline": case.slots["headline"] + pad * 4}


def missing_slot(case, world, rng):
    return case.slots | {"headline": ""}


def extra_slot(case, world, rng):
    return case.slots | {"bars": []}


def wrong_language(case, world, rng):
    other = "ja" if case.lang == "en" else "en"
    names = names_for(*world.league.players[case.insight.player_id])
    swapped = vars(narrate(case.insight, other, case.mode, names))
    return {k: swapped[k] for k in ("tag", "headline", "sub")}


MUTATORS: dict[str, tuple[str, Mutator]] = {
    "num_off_by_one": ("Numbers", num_off_by_one),
    "num_scaled_10pct": ("Numbers", num_scaled),
    "num_swapped_digits": ("Numbers", num_swapped_digits),
    "num_from_other_insight": ("Numbers", num_foreign),
    "entity_teammate": ("Entities", entity_teammate),
    "entity_opponent": ("Entities", entity_opponent),
    "entity_other_club": ("Entities", entity_club),
    "estimate_marker_removed": ("Estimates", drop_estimate_marker),
    "certainty_claim": ("Certainty", add_certainty),
    "over_length": ("Structure", over_length),
    "missing_slot": ("Structure", missing_slot),
    "extra_slot": ("Structure", extra_slot),
    "wrong_language": ("Language", wrong_language),
}


# ---------- run ----------

@dataclass
class MutatorResult:
    family: str
    applied: int = 0
    caught: int = 0
    misses: list[str] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return self.caught / self.applied if self.applied else 0.0


@dataclass
class CatchRate:
    results: dict[str, MutatorResult]
    base_cases: int
    false_positives: int

    @property
    def applied(self) -> int:
        return sum(r.applied for r in self.results.values())

    @property
    def caught(self) -> int:
        return sum(r.caught for r in self.results.values())


def build_world(seed: int = 2026) -> World:
    season = generate_season(seed)
    engine = BaselineEngine(season.league.players)
    engine.apply_all(Applied(e) for gm in season.matches if not gm.match.is_live_demo
                     for e in current_events(gm.feed))
    engine.fit_priors()
    live_gm = next(gm for gm in season.matches if gm.match.is_live_demo)
    insights = [c.insight for c in LivePipeline(engine).run(live_gm.feed)
                if isinstance(c, InsightCreated)]
    league = league_names(season.league.players, season.league.clubs)
    players = {p.player_id: p for p in season.league.players}
    in_match = {live_gm.match.home_club_id, live_gm.match.away_club_id}

    cases, others, clubs, foreign = [], {}, {}, set()
    for ins in insights:
        p = players[ins.player_id]
        names = names_for(p.display_name, p.display_name_ja)
        for lang, mode in VARIANTS:
            ctx = VerifyContext(TEMPLATE_FOR_INSIGHT[ins.type], lang, mode, ins.facts,
                                ins.player_id)
            cases.append(Case(ins, lang, mode, vars(narrate(ins, lang, mode, names)), ctx))
        own_surname = p.display_name.split()[-1]
        for key, same_team in (("team", True), ("opp", False)):
            pool = [q for q in players.values() if q.club_id in in_match
                    and (q.club_id == p.club_id) == same_team and q.player_id != p.player_id
                    and q.display_name.split()[-1] != own_surname]
            others[f"{p.player_id}:{key}:en"] = sorted(q.display_name.split()[-1] for q in pool)
            others[f"{p.player_id}:{key}:ja"] = sorted(
                q.display_name_ja.split("・")[-1] if "・" in q.display_name_ja
                else q.display_name_ja for q in pool)
        clubs[p.player_id] = sorted(c.name for c in season.league.clubs if c.club_id != p.club_id)
        foreign |= allowed_numbers(ins.facts)
    return World(cases, league, others, clubs, sorted(foreign, key=float))


def run(world: World, seed: int = 0) -> CatchRate:
    results = {name: MutatorResult(family) for name, (family, _) in MUTATORS.items()}
    false_positives = 0
    for case in world.cases:
        if not verify(case.slots, case.ctx, world.league).ok:
            false_positives += 1
        for name, (_, mutate) in MUTATORS.items():
            rng = random.Random(f"{seed}:{case.insight.insight_id}:{case.lang}:{case.mode}:{name}")
            mutated = mutate(case, world, rng)
            if mutated is None:
                continue
            r = results[name]
            r.applied += 1
            if verify(mutated, case.ctx, world.league).ok:
                if len(r.misses) < 3:
                    r.misses.append(f"{case.lang}/{case.mode}: {mutated.get('headline')} | "
                                    f"{mutated.get('sub')}")
            else:
                r.caught += 1
    return CatchRate(results, len(world.cases), false_positives)


def render(cr: CatchRate) -> str:
    rows = "\n".join(f"| {r.family} | `{name}` | {r.applied} | {r.caught} | {r.rate:.0%} |"
                     for name, r in cr.results.items())
    families: dict[str, list[MutatorResult]] = {}
    for r in cr.results.values():
        families.setdefault(r.family, []).append(r)
    fam_rows = "\n".join(
        f"| {f} | {sum(r.applied for r in rs)} | {sum(r.caught for r in rs)} | "
        f"{sum(r.caught for r in rs) / max(1, sum(r.applied for r in rs)):.0%} |"
        for f, rs in families.items())
    misses = "\n".join(f"- `{name}`: {m}" for name, r in cr.results.items() for m in r.misses)
    return f"""# Verifier catch rate

Generated by `uv run python -m formline.agents.verifier_eval`.

**Method.** Base texts: the template narrator's output for all {cr.base_cases // 4} live-match
insights × 4 variants (EN/JA × casual/analyst) = {cr.base_cases} cards. Each mutator injects
exactly one error into a copy; a mutation is caught when the verifier rejects it.

**Overall: {cr.caught} / {cr.applied} injected errors caught ({cr.caught / cr.applied:.1%}).
False positives on unmutated cards: {cr.false_positives} / {cr.base_cases}.**

## By family

| Family | Injected | Caught | Rate |
|---|---|---|---|
{fam_rows}

## By mutator

| Family | Mutator | Injected | Caught | Rate |
|---|---|---|---|---|
{rows}

## Misses (examples)

{misses or "None."}

## Known limits

- The number check matches values by kind (speed, percentage, sample size, score), not by
  role. A real speed fact in the wrong place ("his norm is 84 km/h" when 84 is this shot's
  speed) passes.
- Club names are checked in their English form; the league has no Japanese club names, so an
  invented katakana club name would not be caught.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m formline.agents.verifier_eval")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[4]
                        / "docs" / "verifier-catch-rate.md")
    args = parser.parse_args(argv)
    cr = run(build_world(args.seed))
    text = render(cr)
    args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
