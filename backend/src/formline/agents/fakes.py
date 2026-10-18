"""Fake model behaviour for the Selector, Narrator, Match Analyst and Question Suggester
(tests, CI, offline demos).

`FakeAgents` answers like a well-behaved model: the Selector picks the most salient
candidate; the Narrator writes a plain card from the payload's CARD_FACTS. It can also misbehave on
purpose, to exercise the verifier's retry and fallback paths:
- `bad_first_attempts=n`: the first n attempts per card contain a wrong number;
- `garbage=True`: every Narrator reply is not JSON.
"""

import json
import re
from dataclasses import dataclass, field

NUMBER = re.compile(r"\d+")


ROUTE_WORDS = (
    ("match_info", ("where", "venue", "stadium", "kick-off", "when", "season", "weather",
                    "attendance", "crowd", "referee", "どこ", "会場", "スタジアム", "今季", "天気",
                    "観客", "審判")),
    ("recent", ("last 10", "recently", "直近")),
    ("discipline", ("card", "foul", "booked", "カード", "ファウル")),
    ("chances", ("chance", "most shots", "best shot", "決定機", "チャンス")),
    ("team_stats", ("compare", "stats", "teams", "比較", "スタッツ")),
    ("score", ("score", "why is it", "スコア", "なぜ")),
    ("situation", ("happening", "so far", "going on", "流れ", "状況")),
)


def fake_route(p: dict) -> dict:
    """Retrieve like a careful model would: a named team or player, then topic words."""
    text = p["VIEWER_TEXT"].lower()
    sections, club, player = [], None, None
    for c in p["CLUBS"]:
        first = c["name"].split()[0].lower()
        if first in text or (c["short_name"] and c["short_name"].lower() in text.split()):
            sections, club = ["team_tonight"], c["id"]
            break
    about = ("info", "about", "who is", "profile", "season", "nationality", "nationity",
             "country", "birthday", "birth", "born", "国籍", "誕生日", "生年月日", "出身", "生まれ",
             "情報", "について", "プロフィール")
    full = [pl for pl in p["PLAYERS"] if pl["name"].lower() in text or pl["name_ja"] in text]
    matches = full or [pl for pl in p["PLAYERS"]
                       if any(re.search(rf"\b{re.escape(token.lower())}\b", text)
                              for token in pl["name"].split())
                       or any(token in text for token in pl["name_ja"].split("・"))]
    if len(matches) > 1 and club:
        club_name = next(c["name"] for c in p["CLUBS"] if c["id"] == club)
        matches = [pl for pl in matches if pl["club"] == club_name]
    if len(matches) > 1:
        return {"cannot_answer": True}
    if matches:
        pl = matches[0]
        shooting = pl.get("has_shot", True) and not any(w in text for w in about)
        sections = sections + ["player_tonight" if shooting else "player_info"]
        player = pl["id"]
    sections += [q for q, words in ROUTE_WORDS if any(w in text for w in words)
                 and not (player and q == "match_info")]
    sections = list(dict.fromkeys(sections))[:3]
    if not sections:
        return {"cannot_answer": True}
    return {"sections": sections, "club_id": club, "player_id": player}


@dataclass
class FakeAgents:
    bad_first_attempts: int = 0
    garbage: bool = False
    attempts: dict[str, int] = field(default_factory=dict)

    def __call__(self, texts: list[str]) -> str:
        payload = json.loads(texts[-1])
        if "VIEWER_TEXT" in payload:  # the Question Router: keyword routing
            return json.dumps(fake_route(payload))
        if "OPTIONS" in payload:  # the Question Suggester: the first options (best first)
            return json.dumps({"pick": list(payload["OPTIONS"])[:3]})
        if "VIEWER_QUESTION" in payload:  # the Match Analyst on a typed question
            from formline.analyst.facts import FactsPack
            from formline.analyst.templates import template_answer

            pack = FactsPack("free", None, payload["FACTS"], {r: r for r in payload["NAMES"]})
            return json.dumps({**template_answer(pack, payload["LANGUAGE"], payload["NAMES"]),
                               "coverage": "full"}, ensure_ascii=False)
        if "QUESTION_ID" in payload:  # the Match Analyst: answer like the template, from FACTS
            from formline.analyst.facts import FactsPack
            from formline.analyst.templates import template_answer

            pack = FactsPack(payload["QUESTION_ID"], None, payload["FACTS"],
                             {r: r for r in payload["NAMES"]})
            return json.dumps(template_answer(pack, payload["LANGUAGE"], payload["NAMES"]),
                              ensure_ascii=False)
        if "candidates" in payload:
            best = max(payload["candidates"], key=lambda c: (c["salience"], c["id"]))
            return json.dumps({"show": best["id"], "reason": "largest gap from his own norm"})
        return self._narrate(payload)

    def _narrate(self, p: dict) -> str:
        if self.garbage:
            return "Sorry, here is your card: Reyner was great!"
        c, player, lang = p["CARD_FACTS"], p["PLAYER"], p["language"]
        if lang == "ja":
            slots = {"tag": "本人比",
                     "headline": f"{player}、{c['THIS_SHOT']}（{c['SHOT']['result']}）",
                     "sub": f"本人の平均{c['HIS_NORM']}。{c['PERCENTILE']}"}
        else:
            slots = {"tag": "VS HIS OWN NORM",
                     "headline": f"{player}: {c['THIS_SHOT']}, {c['SHOT']['result']}",
                     "sub": f"His norm is {c['HIS_NORM']}; {c['PERCENTILE']}."}
        key = f"{player}|{c['WHAT']}|{c['THIS_SHOT']}|{lang}|{p['audience_mode']}"
        self.attempts[key] = self.attempts.get(key, 0) + 1
        if self.attempts[key] <= self.bad_first_attempts:
            # +37 makes the injected error unambiguous (+1 can land on another real fact).
            slots["sub"] = NUMBER.sub(lambda m: str(int(m.group(0)) + 37), slots["sub"], count=1)
        return json.dumps(slots, ensure_ascii=False)
