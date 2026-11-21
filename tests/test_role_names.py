"""NMB's own role names: no role keeps a name from another game, old names load as the new ones."""
from __future__ import annotations

import json
import re
from pathlib import Path

from nmb import store
from nmb.engine.roles import EN, OLD_NAMES, ROLES, canon_role
from nmb.engine.setup import GameSetup
from nmb.presets import from_saved

ROOT = Path(__file__).resolve().parent.parent
KEPT = {"시민", "마피아", "경찰", "의사", "영매", "연인", "대부", "스파이", "마녀", "교주", "광신도", "사냥꾼", "복수자", "자경단원"}


def test_every_role_is_kept_or_new():
    assert not set(ROLES) & set(OLD_NAMES)
    assert set(OLD_NAMES.values()) <= set(ROLES)
    assert set(ROLES) == KEPT | set(OLD_NAMES.values())
    assert len(set(EN.values())) == len(EN)  # one English name per role


def test_old_names_appear_only_in_the_conversion_table():
    pat = re.compile("|".join(map(re.escape, OLD_NAMES)))
    table = (ROOT / "nmb/engine/roles.py").read_text(encoding="utf-8")
    start = table.index("OLD_NAMES = {")
    end = table.index("}", start)
    hits = []
    files = [p for d in ("nmb", "tools") for p in (ROOT / d).rglob("*.py")] + [ROOT / "po/ko.po"]
    for f in files:
        text = f.read_text(encoding="utf-8")
        if f.name == "roles.py":
            text = text[:start] + text[end:]
        for line in text.splitlines():
            m = pat.search(line)
            if m:
                hits.append(f"{f.relative_to(ROOT)}: {m.group(0)}")
    assert not hits


def test_saved_game_with_old_names_loads_new(tmp_path):
    path = tmp_path / "old.nmb.jsonl"
    rows = [{"record": "header", "game": "complex", "seats": [{"seat": 0, "name": "A", "role": "군인"},
                                                            {"seat": 1, "name": "B", "role": "마피아"}],
             "settings": {"kind": "complex", "seats": [{"role": "정치인"}, {"role": None}], "enabled_roles": ["기자", "의사"]}},
            {"record": "event", "n": 1, "kind": "role", "day": 1, "phase": "day", "text": "군인이 버텼다",
             "details": {"role": "테러리스트"}},
            {"record": "result", "team": "시민", "roles": {"0": "군인", "1": "마피아"}}]
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    s = store.load(path)
    assert [x["role"] for x in s.header["seats"]] == ["방패병", "마피아"]
    assert s.settings["enabled_roles"] == ["폭로자", "의사"]
    assert s.events[0]["details"]["role"] == "폭탄마"
    assert s.events[0]["text"] == "군인이 버텼다"  # what was written then stays as written
    assert s.result is not None and s.result["roles"] == {"0": "방패병", "1": "마피아"}
    setup = GameSetup.from_json(s.settings)
    assert setup.seats[0].role == "시장" and setup.enabled_roles == ["폭로자", "의사"]


def test_preset_and_bench_seat_with_old_name():
    assert from_saved({"seats": [{"model_key": "x", "role": "성직자"}]})[0].role == "부활술사"
    assert canon_role("짐승인간") == "야수" and canon_role("마피아") == "마피아" and canon_role(None) is None
