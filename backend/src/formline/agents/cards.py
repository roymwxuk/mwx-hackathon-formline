"""One selected insight → four verified overlays (EN/JA × casual/analyst).

A plain-async version of the Narrator → Verifier → Composer handoff, used by tests
and by the Agent Framework workflow (task 7), which runs the same steps as a graph.
"""

import asyncio
from dataclasses import dataclass

from formline.agents.composer import compose
from formline.agents.llm import LLMRunner
from formline.agents.narrator import Narration, narrate_verified
from formline.agents.selector import Selection
from formline.agents.template_narrator import Names
from formline.agents.verifier import LeagueNames
from formline.schema.overlay import Overlay

VARIANTS = (("en", "casual"), ("en", "analyst"), ("ja", "casual"), ("ja", "analyst"))


@dataclass(frozen=True)
class Card:
    overlay: Overlay
    narration: Narration  # how the text was produced (llm/template, attempts, failures)


async def build_cards(selection: Selection, names: Names, runner: LLMRunner,
                      league: LeagueNames) -> list[Card]:
    narrations = await asyncio.gather(*(
        narrate_verified(selection.insight, lang, mode, names, runner, league)
        for lang, mode in VARIANTS))
    return [Card(compose(selection, lang, mode, n.slots), n)
            for (lang, mode), n in zip(VARIANTS, narrations, strict=True)]
