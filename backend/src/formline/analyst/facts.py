"""Facts packs: what the data says about one moment, built deterministically (no LLM).

The Analyst agent may only use these facts, and the verifier checks its answer against
them. Values are viewer-ready strings in plain football words (no internal codes); every
number the answer may contain appears in some value. Players are referred to by role
(SHOOTER, PASSER, TAKER, PLAYER…); the payload maps roles to names per language.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from formline.engine.features import shot_features
from formline.pitch import PITCH_LENGTH_M

OUTCOME = {"goal": "scored", "saved": "saved by the goalkeeper", "off_target": "off target",
           "post": "hit the post", "blocked": "blocked by a defender"}
BODY = {"left_foot": "left foot", "right_foot": "right foot", "head": "header", "other": "other"}
SET_PIECE = {"free_kick": "a direct free kick", "penalty": "a penalty", "corner": "a corner"}
ON_BALL = {"pass", "shot", "duel", "interception", "ball_recovery"}
CORNER_WINDOW_MS = 15_000


@dataclass
class FactsPack:
    question: str  # shot_outcome | corner | card | var
    event: object  # the event that fired it
    facts: dict
    roles: dict[str, str]  # role -> player_id (the only players the answer may name)
    source_event_ids: list[str] = field(default_factory=list)

    @property
    def match_clock_ms(self) -> int:
        return self.event.match_clock_ms

    @property
    def moment_id(self) -> str:
        return self.event.event_id


def minute(e) -> str:
    return f"{e.match_clock_ms // 60_000 + 1}'"


def _key(e) -> tuple[int, int]:
    return e.period, e.match_clock_ms


def score_after(events: Iterable, upto, home: str, away: str) -> dict[str, int]:
    """Goals per club up to and including `upto` (latest versions only)."""
    goals = {home: 0, away: 0}
    for e in events:
        if e.type == "shot" and e.outcome == "goal" and _key(e) <= _key(upto):
            goals[e.team_id] = goals.get(e.team_id, 0) + 1
    return goals


def _score_text(goals: dict[str, int], home: str, away: str, clubs: Mapping[str, str]) -> str:
    return f"{clubs[home]} {goals[home]}–{goals[away]} {clubs[away]}"


def shot_pack(shot, events: list, players: Mapping, clubs: Mapping[str, str], home: str,
              away: str) -> FactsPack:
    f = shot_features(shot, players.get(shot.player_id))
    roles = {"SHOOTER": shot.player_id}
    facts: dict = {
        "minute": minute(shot),
        "team": clubs[shot.team_id],
        "outcome": OUTCOME[shot.outcome],
        "distance": f"{round(f.distance_m)} m from goal",
        "body_part": BODY[shot.body_part],
        "shot_speed": f"{round(f.shot_speed_kmh)} km/h",
        "chance_quality": f"{round(f.xg * 100)}% chance of a goal from that position (model estimate, xG)",
    }
    if f.nearest_defender_m is not None:
        near = round(f.nearest_defender_m, 1)
        facts["pressure"] = (f"under pressure: nearest defender {near} m away" if f.pressure != "open"
                             else f"no defender close: nearest {near} m away")
    if f.defenders_in_cone:
        facts["defenders_between_ball_and_goal"] = f"{f.defenders_in_cone} defender(s) in the way"
    if f.gk_off_line_m is not None:
        facts["goalkeeper"] = f"goalkeeper {round(f.gk_off_line_m, 1)} m off his line"
    if f.psxg is not None:
        facts["on_target_quality"] = (f"{round(f.psxg * 100)}% chance once on target (model "
                                      "estimate, post-shot xG)")
    if f.placement is not None:
        facts["placement"] = f"placement {round(f.placement * 100)}/100 (100 = top corner)"
    if shot.first_time:
        facts["technique"] = "first-time shot"
    if shot.deflected:
        facts["deflected"] = "the shot was deflected"
    if shot.shot_type in SET_PIECE:
        facts["set_piece"] = f"from {SET_PIECE[shot.shot_type]}"
    sources = [shot.event_id]
    if shot.key_pass_event_id:
        kp = next((e for e in events if e.event_id == shot.key_pass_event_id), None)
        if kp is not None and kp.player_id:
            roles["PASSER"] = kp.player_id
            kind = "cross" if getattr(kp, "cross", False) else (
                "through ball" if getattr(kp, "through_ball", False) else "pass")
            facts["assist"] = f"set up by a {kind} from PASSER"
            sources.append(kp.event_id)
    if shot.outcome == "goal":
        facts["score_now"] = _score_text(score_after(events, shot, home, away), home, away, clubs)
    return FactsPack("shot_outcome", shot, facts, roles, sources)


def corner_pack(corner, after: list, events: list, clubs: Mapping[str, str]) -> FactsPack:
    """`after`: on-ball events that followed the corner, up to its resolution."""
    team = corner.team_id
    roles = {"TAKER": corner.player_id}
    side = "left" if corner.y > 50 else "right"  # the attacking team's view
    tonight = sum(1 for e in events if e.type == "pass" and getattr(e, "pass_type", None) == "corner"
                  and e.team_id == team and _key(e) <= _key(corner))
    facts: dict = {
        "minute": minute(corner),
        "team": clubs[team],
        "side": f"corner from the {side}",
        "corners_tonight": f"corner number {tonight} for {clubs[team]} tonight",
    }
    if corner.end_x is not None:
        depth = "short" if corner.end_x < 84 else ("into the six-yard box" if corner.end_x > 94
                                                  else "into the penalty area")
        facts["delivery"] = f"delivered {depth}"
    speed = getattr(getattr(corner, "tracking", None), "ball_speed_kmh", None)
    if speed:
        facts["delivery_speed"] = f"ball speed {round(speed)} km/h"
    if corner.recipient_id:
        roles["TARGET"] = corner.recipient_id
        facts["first_contact"] = "reached TARGET"
    sources = [corner.event_id]
    shot = next((e for e in after if e.type == "shot" and e.team_id == team), None)
    if shot is not None:
        roles["SHOOTER"] = shot.player_id
        f = shot_features(shot)
        facts["what_followed"] = (f"led to a shot by SHOOTER: {OUTCOME[shot.outcome]}, "
                                  f"{round(f.xg * 100)}% chance (model estimate)")
        sources.append(shot.event_id)
    else:
        won = next((e for e in after if e.team_id != team), None)
        if won is not None:
            facts["what_followed"] = "the defence won the ball back; no shot"
            sources.append(won.event_id)
        else:
            facts["what_followed"] = "no shot came from it"
    return FactsPack("corner", corner, facts, roles, sources)


def card_pack(card, foul, events: list, clubs: Mapping[str, str]) -> FactsPack:
    team = card.team_id
    roles = {"PLAYER": card.player_id}
    kind = {"yellow": "yellow card", "second_yellow": "second yellow card: sent off",
            "red": "straight red card: sent off"}[card.card]
    fouls = sum(1 for e in events if e.type == "foul_committed" and e.player_id == card.player_id
                and _key(e) <= _key(card))
    team_cards = sum(1 for e in events if e.type == "card" and e.team_id == team
                     and _key(e) <= _key(card))
    facts: dict = {
        "minute": minute(card),
        "team": clubs[team],
        "card": kind,
        "his_fouls_tonight": f"foul number {fouls} by PLAYER tonight",
        "team_cards_tonight": f"card number {team_cards} for {clubs[team]} tonight",
        "possession": "the other team had the ball",
        "not_in_the_data": "the feed does not record who was fouled or why",
    }
    sources = [card.event_id]
    if foul is not None:
        facts["where"] = f"about {round(foul.x * PITCH_LENGTH_M / 100)} m from his own goal line"
        if foul.play_pattern == "from_counter":
            facts["context"] = "it stopped a counter-attack"
        sources.append(foul.event_id)
    if card.card == "second_yellow":
        first = next((e for e in events if e.type == "card" and e.player_id == card.player_id
                      and e.card == "yellow" and _key(e) < _key(card)), None)
        if first is not None:
            facts["first_yellow"] = f"his first yellow came in minute {minute(first).rstrip(chr(39))}"
            facts["consequence"] = f"{clubs[team]} are down to 10 men"
            sources.append(first.event_id)
    return FactsPack("card", card, facts, roles, sources)


def var_pack(shot_before, shot_after, events: list, clubs: Mapping[str, str], home: str,
             away: str) -> FactsPack:
    roles = {"SHOOTER": shot_after.player_id}
    facts = {
        "minute": minute(shot_after),
        "team": clubs[shot_after.team_id],
        "decision": "the goal was ruled out after a VAR review",
        "score_now": _score_text(score_after(events, shot_after, home, away), home, away, clubs),
    }
    return FactsPack("var", shot_after, facts, roles, [shot_after.event_id])
