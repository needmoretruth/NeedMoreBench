"""the rating counts a player with the team it ended on. A citizen converted by the 교주 that loses with
the cult is a cult loss, not a citizen win; records written before the end sides were kept read the conversions."""
from __future__ import annotations

from pathlib import Path

from nmb.rating import CITIZEN, CULT, MAFIA, row_from_saved
from nmb.runner import seat_record
from nmb.store import Recorder, load

from .test_complex import play


def teams(row) -> dict[str, list[str]]:  # noqa: ANN001
    return {side: sorted(e.key.split("#")[0] for e in players) for side, players in row.teams}


def test_a_convert_is_rated_with_the_cult_it_ended_in(tmp_path: Path) -> None:
    g = play(["교주", "마피아", "경찰", "의사", "시민", "시민"], {(1, "night", 0): {"target": 2}})
    rec = Recorder(g, seat_record(g), tmp_path)
    for e in g.events:  # the game ran before the recorder was attached
        rec.event(e)
    g.result = g.make_result(MAFIA, "끝")
    rec.close()
    saved = load(rec.path)
    assert saved.result is not None and saved.result["sides"]["2"] == CULT and saved.result["roles"]["2"] == "경찰"
    row = row_from_saved(saved.header, saved.events, saved.result)
    assert row is not None
    keys = {s["seat"]: (s.get("model") or "").split("#")[0] for s in saved.header["seats"]}
    by_side = teams(row)
    assert keys[2] in by_side[CULT] and keys[2] not in by_side[CITIZEN]
    assert row.teams[row.winner][0] == MAFIA

    # an older record: no 「sides」, the conversion event says who changed team
    old = {k: v for k, v in saved.result.items() if k != "sides"}
    convert = [e for e in saved.events if e.get("kind") == "convert"]
    assert convert and convert[0]["about_seat"] == 2
    assert teams(row_from_saved(saved.header, convert, old)) == by_side
    # and without either, the first team is all there is
    assert keys[2] in teams(row_from_saved(saved.header, [], old))[CITIZEN]
