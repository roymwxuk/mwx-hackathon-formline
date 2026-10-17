"""Fake model behaviour for the Selector and Narrator (tests, CI, offline demos).

`FakeAgents` answers like a well-behaved model: the Selector picks the most salient
candidate; the Narrator returns the template narration. It can also misbehave on
purpose, to exercise the verifier's retry and fallback paths:
- `bad_first_attempts=n`: the first n attempts per card contain a wrong number;
- `garbage=True`: every Narrator reply is not JSON.
"""

import json
import re
from dataclasses import dataclass, field
from types import SimpleNamespace

from formline.agents.template_narrator import Names, narrate

NUMBER = re.compile(r"\d+")


@dataclass
class FakeAgents:
    bad_first_attempts: int = 0
    garbage: bool = False
    attempts: dict[str, int] = field(default_factory=dict)

    def __call__(self, texts: list[str]) -> str:
        payload = json.loads(texts[-1])
        if "candidates" in payload:
            best = max(payload["candidates"], key=lambda c: (c["salience"], c["id"]))
            return json.dumps({"show": best["id"], "reason": "largest gap from his own norm"})
        return self._narrate(payload)

    def _narrate(self, p: dict) -> str:
        if self.garbage:
            return "Sorry, here is your card: Reyner was great!"
        ins = SimpleNamespace(type=p["insight_type"], direction=p["direction"],
                              facts={**p["FACTS"], "comparison_level": p["COMPARISON"]})
        slots = vars(narrate(ins, p["language"], p["audience_mode"],
                             Names(p["player"], p["player"])))
        key = f"{p['player']}|{p['insight_type']}|{p['FACTS']['value']}|{p['language']}|" \
              f"{p['audience_mode']}"
        self.attempts[key] = self.attempts.get(key, 0) + 1
        if self.attempts[key] <= self.bad_first_attempts:
            slots["sub"] = NUMBER.sub(lambda m: str(int(m.group(0)) + 1), slots["sub"], count=1)
        return json.dumps(slots, ensure_ascii=False)
