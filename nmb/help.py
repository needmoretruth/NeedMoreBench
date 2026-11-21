"""도움말: what the help page says, without GTK. English source strings, Korean in po/ko.po.

Roles come from the engine's role table, so a new role shows up by itself (with its in-game description until
an entry is written here, which the tests ask for). Powers come from nmb.engine.god in the popover's order.
"""
from __future__ import annotations

from .engine import god
from .engine.roles import GAME_ROLES, ROLES, SIMPLE
from .i18n import _

FIELDS = ("What it does", "When you can use it", "Who sees or learns it", "What the models are told", "In the record")


def watching() -> list[tuple[str, str]]:
    return [
        (_("Watching"), _("Models play while you watch. You see everything: every role, every thought, the night chats, "
                          "the whispers, and a model's own reasoning when its connection sends it. With god powers on, "
                          "you can also step into the game.")),
        (_("Taking a seat"), _("You take one seat and play with the models. You see only what your seat may know, and you "
                         "answer on the card under the timeline when it is your turn.")),
        (_("Cheats"), _("While you play, cheats show you everything a spectator sees and give you the god powers. "
                        "Nobody at the table is told who the god is.")),
        (_("Who the god is"), _("When powers are on, the rules every player reads say that a god may act in this game, "
                                "that the god could be watching or sitting at the table, and that nobody knows who. "
                                "Everything a power does reaches the players as the doing of 「신」, the god, and nothing "
                                "more. A power you use while playing takes effect at the game's next step, the same "
                                "as a spectator's, so its timing does not point to your seat. Only the record and your "
                                "own screen say who used it.")),
        (_("God intervened"), _("A game where any power other than Announce and Pause was used is marked God "
                                "intervened in the records and in the replay, and it is left out of the standings. "
                                "Bench games never offer the powers.")),
    ]


def flow() -> list[tuple[str, str]]:
    return [
        (_("Day and night"), _("A game starts by day. On the first day everyone introduces themselves in seat order "
                               "and talks, then night falls without a vote. After that every night is followed by a "
                               "morning, the talk, whisper time, the vote, the last defense and the guilty or not vote.")),
        (_("Introductions"), _("On the first day each player in turn tells the table who they are. Anyone may tell "
                               "their role truly, falsely, or not at all. That is true all game long.")),
        (_("Discussion"), _("Players speak in turn from a shared number of turns that everyone can see. First "
                            "everyone speaks once, then a player who was just named gets to answer, then whoever wants "
                            "to speak most. Staying silent is allowed. The talk ends when the turns run out or nobody "
                            "has anything left to say.")),
        (_("Longer and shorter"), _("Once a day each player may ask for a longer or a shorter talk. Everyone is told "
                                    "who asked. A longer talk adds two turns. When more than half of the living "
                                    "players have asked for a shorter talk, the talk ends at once.")),
        (_("Poll"), _("During the talk a player may point at the one it suspects most. Only the count for each "
                      "player shows, never who pointed. It changes nothing in the game.")),
        (_("Whisper time"), _("After the talk, players one by one may send one secret whisper to another living "
                              "player, and each player who got one may answer once. Only those two ever see it.")),
        (_("Vote"), _("Everyone votes for the player who should face the last defense, or skips. With a tie or no "
                      "votes, night falls at once.")),
        (_("Last defense"), _("The player with the most votes speaks alone, a little longer than usual.")),
        (_("Guilty or not"), _("The others vote to execute or to spare. Execution needs at least as many votes for as "
                               "against. A skipped vote counts as against.")),
        (_("Night"), _("The mafia meet in secret and pick a player to kill. Roles with a night ability use it. A "
                       "result reaches only the player who used the ability.")),
        (_("Morning"), _("Who died in the night is announced. If nobody died, the night was quiet.")),
        (_("Winning"), _("The citizen team wins when the whole mafia team is dead. The mafia team wins when it is as "
                         "many as everyone else, or when the last night passes without an end.")),
    ]


def powers() -> dict[str, tuple[str, str, str, str, str]]:
    """Per power: what it does, when, who sees or learns what, what the models are told, how the record marks it."""
    marks = _("Kept as a god line with what changed and who learned what. Marks the game as God intervened.")
    return {
        "공지": (_("Sends a message from the god to everyone at the table."),
               _("Any time while the game runs."),
               _("Everyone reads it as a message from the god. Nobody learns who the god is."),
               _("It enters every player's history as 「신의 공지」 followed by your words."),
               _("Kept as a god line. An announcement alone does not mark the game.")),
        "계시": (_("Gives one player a standing instruction from the god. It may be true or false."),
               _("Any time, on a living player. Several can stand at once, in the order given. Lift each one from "
                 "the list under the powers."),
               _("Only that player. The others never see it."),
               _("It goes into that player's system prompt, next to the rules, as 「신의 계시」 with the same weight "
                 "as the rules. It is there on every call until you lift it, and the player is told when it is "
                 "lifted."),
               _("Kept with when it was given and when it was lifted. Marks the game as God intervened.")),
        "속삭임 위조": (_("Sends one player a whisper that seems to come from another player you pick."),
                   _("By day, while both are alive. Pick the receiver as Player and the seeming sender as Second "
                     "player."),
                   _("The receiver sees an ordinary whisper from the named sender. The named sender is not told and "
                     "may later get a reply it never asked for."),
                   _("The receiver's history shows it exactly like a real whisper from that sender."),
                   _("Marked as forged by the god. Marks the game as God intervened.")),
        "빙의": (_("Says one line in the talk in a player's name."),
               _("By day, on a living player who may speak today."),
               _("Everyone, that player too, sees it as that player's own words."),
               _("It enters every history as that player's line, with nothing to tell it apart."),
               _("Marked as the god's words. Marks the game as God intervened.")),
        "심문": (_("Asks one player a question that it answers to the god alone."),
               _("Any time, on a living player who is not already answering one."),
               _("Only that player sees the question. The answer shows only on your screen and in the record."),
               _("The player is asked at once. Its prompt shows 「신의 질문」 and asks it to answer the god only. "
                 "Its answer stays in its own history, so it remembers what it said."),
               _("Keeps the question and the answer. Marks the game as God intervened.")),
        "거짓 결과": (_("Makes the next result of a player's own ability say what you choose, such as a police check "
                     "that calls an innocent player mafia."),
                  _("On a living player whose role gets a result: police, spy or medium."),
                  _("Only that player, who cannot tell it from a true result."),
                  _("The result comes at the same moment and in the same words as a real one. Only the answer is "
                    "changed."),
                  _("Marked as false with the true result beside it. Marks the game as God intervened.")),
        "역할 공개": (_("Tells everyone one player's true role."),
                  _("On a player whose role is not public yet."),
                  _("Everyone."),
                  _("Every history gets a line from the god with that role, and the player is listed as revealed."),
                  marks),
        "정체 공개": (_("In a blind game, tells everyone which model plays one seat."),
                  _("Only in a blind game, once for each seat."),
                  _("Everyone."),
                  _("Every history gets a line from the god with the model's name."),
                  marks),
        "천벌": (_("Kills a living player at once with lightning."),
               _("Any time, on a living player."),
               _("Everyone sees the lightning and the death."),
               _("The lightning and the death enter every history. Whether the role is shown follows the game's rule "
                 "for deaths."),
               marks),
        "부활": (_("Brings a dead player back to life."),
               _("Any time, on a dead player."),
               _("Everyone."),
               _("A line from the god says that the player came back."),
               marks),
        "보호": (_("Blocks every attack on one player for one night."),
               _("Any time, on a living player. It lasts to the end of the current or the coming night."),
               _("Nobody is told. If an attack is blocked, the players only see that nobody died."),
               _("Nothing, unless they notice that nobody died."),
               marks),
        "역할 바꾸기": (_("Gives one player a different role."),
                   _("On a living player, to any role of this game. Pick it under Role."),
                   _("Only that player, who is told its new role."),
                   _("A line from the god tells that player its new role. From then on its prompts describe the new "
                     "role."),
                   _("Keeps the old and the new role. Marks the game as God intervened.")),
        "역할 맞바꾸기": (_("Two players trade roles, and with them what each role has already used up."),
                    _("On two players with different roles."),
                    _("Each of the two is told only its own new role, not with whom it traded."),
                    _("A line from the god tells each of them its new role."),
                    marks),
        "침묵": (_("One player cannot speak for a day."),
               _("On a living player. By day it is today, at night the next day."),
               _("That player is told. The others only notice that it says nothing."),
               _("A line from the god tells that player which day it cannot speak. It is not asked to speak that "
                 "day."),
               marks),
        "투표권 박탈": (_("One player cannot vote in the next vote, nor in the guilty or not vote after it."),
                   _("On a living player."),
                   _("That player is told."),
                   _("A line from the god tells that player which day it cannot vote. It is not asked to vote that "
                     "day."),
                   marks),
        "사면": (_("Calls off the execution being decided."),
               _("During the last defense or the guilty or not vote."),
               _("Everyone hears the pardon."),
               _("A line from the god says the player is pardoned. Whatever the count, nobody is executed."),
               marks),
        "재투표": (_("Throws away the current vote and holds it again."),
                _("From the vote to the end of the guilty or not vote."),
                _("Everyone."),
                _("A line from the god says the vote starts over, then everyone is asked to vote again."),
                marks),
        "발언 시키기": (_("The player you pick speaks next in the talk."),
                   _("During the discussion, on a player who may speak."),
                   _("Nobody is told. The player simply gets the next turn."),
                   _("An ordinary turn to speak."),
                   marks),
        "토론 시간 조절": (_("Adds turns to the talk or takes them away."),
                     _("During the discussion. Pick the number under Turns: more than zero adds, less takes away."),
                     _("Everyone sees the new number of turns."),
                     _("A line from the god gives the new number of turns."),
                     marks),
        "다음 단계로": (_("Ends the current part of the day or night and moves on."),
                   _("Any time while the game runs."),
                   _("Everyone sees the next part begin."),
                   _("Nothing more than the next part beginning."),
                   marks),
        "일시정지": (_("Stops the game until you press it again."),
                 _("Any time while the game runs."),
                 _("Nobody at the table."),
                 _("Nothing. A model that is already answering finishes its answer."),
                 _("Pause and resume lines. Pausing does not mark the game.")),
    }


def power_intro() -> str:
    return _("God powers are how a spectator, or a player with cheats, steps into the game to see how the models "
             "take pressure, lies and luck. Pick a player, type the words or pick the role a power needs, then tap "
             "it. A power that makes no sense right now stays grey and says why. Every use leaves a line in the god "
             "colour on your screen.")


def role_texts() -> dict[str, str]:
    """By ability key. Names of other roles are left out where they may change."""
    return {
        "none": _("Has no special ability. Finds the mafia by talking and voting."),
        "mafia": _("Each night the mafia agree together on one player to kill."),
        "police": _("Each night checks one player and learns whether that player is mafia. Only the police see the "
                    "result."),
        "doctor": _("Each night picks one player to save from the mafia's attack. It may pick itself."),
        "spy": _("Helps the mafia without knowing who they are at first. Each night learns one player's role. Finding "
                 "a mafia member brings it into the mafia meeting, and it checks once more that night."),
        "beast": _("Helps the mafia without knowing them. Each night marks one player. If the mafia kill that player, "
                   "it is tamed and joins the mafia meeting. The mafia's attack cannot kill it."),
        "seducer": _("Helps the mafia without knowing them. The player it votes for by day is seduced: no ability "
                     "that night and no speaking the next day. Seducing a mafia member brings it to the mafia."),
        "copycat": _("Helps the mafia without knowing them. At the vote it picks a player and uses that player's "
                     "ability that night. Copying the mafia brings it to the mafia."),
        "shieldbearer": _("Survives the mafia's attack once, and everyone is told. If the mafia team checks it, it "
                          "learns who checked."),
        "mayor": _("Cannot be executed by vote, and its vote counts twice."),
        "medium": _("Hears the dead and talks with them at night. Each night learns a dead player's role and lays "
                    "that player to rest, so it speaks no more."),
        "lover": _("There are two lovers, and they talk alone at night. While both live, if the mafia pick one, the "
                   "other dies in its place."),
        "blackmailer": _("At night picks a player who cannot vote the next day."),
        "exposer": _("Once a game, from the second night, learns one player's role and exposes it to everyone the "
                     "next morning."),
        "shadow": _("At night follows a player and learns whom that player used an ability on that night."),
        "heir": _("Takes over the role of the player the mafia killed on the first night."),
        "bomber": _("At night marks a player. If the mafia kill it that night and the marked player is mafia, both "
                    "die. If it is executed by vote, it takes the marked player along when that one is an enemy."),
        "avenger": _("If the mafia team kill it at night, its last shot takes along the player who first picked it in "
                     "the mafia meeting. There is nothing to choose beforehand. If it is saved, nothing happens."),
        "hunter": _("If executed by vote, it picks any living player to take along after the guilty or not vote. "
                    "Everyone is told. Dying any other way, it cannot shoot."),
        "reviver": _("Once a game, at night, brings one dead player back to life, announced in the morning. A player "
                     "laid to rest cannot come back. The cult cannot convert it."),
        "witch": _("Helps the mafia without knowing them. Each night turns a player into a frog, who has no role "
                   "ability until the next night. Picking a mafia member brings it to the mafia instead."),
        "undying": _("Helps the mafia without knowing them. When it dies it joins the mafia and comes back to life "
                     "once at the end of the next night, in front of everyone."),
        "masquerader": _("Helps the mafia without knowing them. At the start it learns one citizen's role and poses "
                         "as that role. It survives one execution by vote and then joins the mafia. It also joins if "
                         "that citizen is executed."),
        "assassin": _("Helps the mafia without knowing them. From the second night, each night it names two players "
                      "and their roles. If both are right, both die. Naming a mafia member brings it to the mafia."),
        "godfather": _("Helps the mafia without knowing them. It joins the mafia on the third night, then picks the "
                       "kill with them, and from then on the mafia's attack cannot be saved or blocked."),
        "vigilante": _("Once a game, at the day vote, learns whether one player is mafia. If so, it may kill that "
                       "player on a later night."),
        "informant": _("At the end of each night learns the role of one citizen team player it did not know yet."),
        "liaison": _("At night picks a player. If they are on the same team, the two learn each other's role."),
        "flagbearer": _("If it is alive on the fourth day, the citizen team wins."),
        "foreman": _("If the guilty or not result differs from its own pick, it shows itself and turns the result its "
                     "way. From then on it alone decides the guilty or not vote."),
        "assistant": _("At night picks a player. Picking the doctor lets the two know each other. Once the doctor is "
                       "dead, each night it saves the player it picks from the mafia's attack."),
        "illusionist": _("At night plays a trick on a player. If it is attacked that night, the tricked player dies "
                         "in its place."),
        "wiretapper": _("Picks a player at the day vote and learns that player's role when night falls."),
        "face_reader": _("Picks two players at the day vote and learns whether they are on the same team."),
        "fixer": _("At the start one citizen becomes its client. If the client dies at night, from then on it may "
                   "kill one player each night."),
        "archivist": _("At night names a role and learns who has it."),
        "gossip": _("Each morning gets one of the role facts the citizen team has found."),
        "enchanter": _("At night casts a spell on a player. At the day vote it may wake one spelled player and, if "
                       "that player is not on the citizen team, learns its role."),
        "astrologer": _("At night picks a player and gets two roles mixed together: that player's and the role of "
                        "someone on another team."),
        "cult_leader": _("Every odd night converts one player to the cult team and learns its role; the mafia team "
                         "cannot be converted. A bell rings for everyone when it works. Each night it may send one "
                         "line to the cult team, who cannot answer."),
        "fanatic": _("On the cult team without knowing the cult leader. At night checks a player to find the leader "
                     "and join it. If the leader dies, it carries on converting."),
    }


# the role keys before renamed them; the same abilities
ALIASES = {"madam": "seducer", "thief": "copycat", "soldier": "shieldbearer", "politician": "mayor", "thug": "blackmailer",
           "reporter": "exposer", "detective": "shadow", "graverobber": "heir", "terrorist": "bomber", "priest": "reviver",
           "scientist": "undying", "fraud": "masquerader", "hitman": "assassin", "agent": "informant",
           "inspector": "liaison", "prophet": "flagbearer", "judge": "foreman", "nurse": "assistant",
           "magician": "illusionist", "hacker": "wiretapper", "psychologist": "face_reader", "mercenary": "fixer",
           "official": "archivist", "paparazzi": "gossip", "hypnotist": "enchanter", "fortune": "astrologer"}


def role_key(role: str) -> str:
    key = ROLES[role].ability
    return ALIASES.get(key, key)


def role_text(role: str) -> str:
    """The help text of a role; a role with no entry yet shows its in-game description."""
    return role_texts().get(role_key(role)) or ROLES[role].text


def roles_by_game() -> list[tuple[str, list[str]]]:
    """(game key, its roles) with the simple game's roles first, each role once."""
    simple = list(GAME_ROLES[SIMPLE])
    rest = [r for r in ROLES if r not in simple]
    return [(SIMPLE, simple), ("complex", rest)]


def power_entries() -> list[tuple[str, list[tuple[str, tuple[str, str, str, str, str]]]]]:
    texts = powers()
    return [(group, [(p, texts[p]) for p in ps]) for group, ps in god.GROUPS]


__all__ = ["FIELDS", "flow", "power_entries", "power_intro", "powers", "role_text", "roles_by_game",
           "watching"]
