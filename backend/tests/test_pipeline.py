from formline.models import EventType
from formline.pipeline.ingest import generate_match
from formline.pipeline.interpret import Interpreter


def test_match_is_deterministic_and_complete():
    events = list(generate_match(seed=1))
    assert events[0].type == EventType.KICKOFF
    assert events[-1].type == EventType.FULL_TIME
    assert [e.id for e in events] == [e.id for e in generate_match(seed=1)]


def test_interpreter_possession_sums_to_100():
    interp = Interpreter()
    for ev in generate_match(seed=2):
        state = interp.update(ev)
    assert abs(sum(state.possession_pct.values()) - 100) < 0.5
