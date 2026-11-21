"""마피아: the kill is chosen in the mafia meeting the engine runs (night.mafia_meeting), not here."""
from __future__ import annotations

from .base import Ability, register


@register
class Mafia(Ability):
    key = "mafia"
    kills = True  # takes part in choosing the night kill
