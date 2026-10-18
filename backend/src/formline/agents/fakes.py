"""Fake model behaviour for the Selector and Narrator (tests, CI, offline demos).

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


@dataclass
class FakeAgents:
    bad_first_attempts: int = 0
    garbage: bool = False
    attempts: dict[str, int] = field(default_factory=dict)

    def __call__(self, texts: list[str]) -> str:
        payload = json.loads(texts[-1])
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
