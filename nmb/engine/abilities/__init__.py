"""Role abilities behind a registry. Importing this package registers every module."""
from . import doctor, helpers, mafia, police, town  # noqa: F401
from .base import REGISTRY, Ability, Attack, NightContext, ability_for, ability_of, in_mafia_team

__all__ = ["REGISTRY", "Ability", "Attack", "NightContext", "ability_for", "ability_of", "in_mafia_team"]
