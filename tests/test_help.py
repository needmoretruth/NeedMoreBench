"""도움말: every power and every role of both games has its own entry, in English and in Korean."""
from __future__ import annotations

from pathlib import Path

from nmb import help as h
from nmb.engine import god
from nmb.engine.roles import GAME_ROLES, ROLES
from nmb.i18n import read_po

KO = read_po(Path(__file__).resolve().parent.parent / "po" / "ko.po")


def test_every_power_has_five_parts():
    texts = h.powers()
    assert set(texts) == set(god.POWERS)
    for p, fields in texts.items():
        assert len(fields) == len(h.FIELDS) == 5, p
        assert all(f.strip() for f in fields), p
    assert [p for _g, ps in h.power_entries() for p, _f in ps] == god.POWERS


def test_every_role_has_its_own_entry():
    texts = h.role_texts()
    for role in ROLES:
        assert h.role_key(role) in texts, f"{role} ({ROLES[role].ability}) has no help entry"
    listed = [r for _g, rs in h.roles_by_game() for r in rs]
    assert sorted(listed) == sorted(ROLES) and len(listed) == len(set(listed))
    assert all(r in listed for game in GAME_ROLES.values() for r in game)


def test_help_is_in_korean_without_dashes():
    strings = [s for fields in h.powers().values() for s in fields] + list(h.role_texts().values())
    strings += [s for pair in h.flow() + h.watching() for s in pair] + [h.power_intro(), *h.FIELDS]
    for s in strings:
        ko = KO.get(s)
        assert ko, f"no Korean: {s[:60]}"
        assert "·" not in ko and " - " not in ko and "—" not in ko, ko


def test_flow_covers_the_steps_of_a_day():
    titles = " ".join(t for t, _b in h.flow())
    for step in ("Introductions", "Discussion", "Longer and shorter", "Whisper time", "Vote", "Last defense",
                 "Guilty or not", "Night"):
        assert step in titles
