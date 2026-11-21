"""Who made a model and where, which models train on prompts, and which are not chat models.

Makers come, in this order, from the route's author slug ('meta/muse-...' on OpenRouter), from the maker part the
route writes before the name ('Z.ai: GLM 5.3 Flash'), and only then from the family word that starts the id or the
name ('glm-5.3', 'Qwen3.8 Flash'). A family word inside a tuned model's name ('dolphin-mistral-24b-venice-edition',
'l3.1-euryale') says nothing about who made it, so it is not guessed.
Names the spec lists as unknown (Beam, Big Pickle, Iceman, Flint) stay unknown.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib import resources

US, CN, FR, IL, KR, JP, CA = "미국", "중국", "프랑스", "이스라엘", "한국", "일본", "캐나다"
# family word at the start of an id or name → (maker, country)
FAMILIES: list[tuple[str, str, str]] = [
    ("claude", "Anthropic", US), ("gpt", "OpenAI", US), ("openai", "OpenAI", US), ("o3", "OpenAI", US),
    ("gemini", "Google", US), ("gemma", "Google", US), ("grok", "xAI", US), ("muse", "Meta", US), ("llama", "Meta", US),
    ("nemotron", "NVIDIA", US), ("inkling", "Thinking Machines", US), ("lfm", "Liquid AI", US),
    ("venice", "Venice", US), ("mistral", "Mistral AI", FR), ("ministral", "Mistral AI", FR), ("deepseek", "DeepSeek", CN),
    ("glm", "Z.ai", CN), ("qwen", "Alibaba", CN), ("kimi", "Moonshot AI", CN), ("minimax", "MiniMax", CN),
    ("mimo", "Xiaomi", CN), ("hy3", "Tencent", CN), ("hy4", "Tencent", CN), ("longcat", "Meituan", CN),
    ("step", "StepFun", CN), ("seed", "ByteDance", CN), ("ernie", "Baidu", CN), ("ling", "Ant Group", CN),
    ("aion", "Aion Labs", IL), ("exaone", "LG AI Research", KR), ("google", "Google", US), ("nvidia", "NVIDIA", US),
]
# a route's author slug → maker
PREFIX: dict[str, str] = {
    "anthropic": "Anthropic", "openai": "OpenAI", "google": "Google", "x-ai": "xAI", "meta": "Meta",
    "meta-llama": "Meta", "nvidia": "NVIDIA", "thinkingmachines": "Thinking Machines", "reflection": "Reflection AI",
    "liquid": "Liquid AI", "mistralai": "Mistral AI", "deepseek": "DeepSeek", "z-ai": "Z.ai", "qwen": "Alibaba",
    "moonshotai": "Moonshot AI", "minimax": "MiniMax", "xiaomi": "Xiaomi", "tencent": "Tencent", "meituan": "Meituan",
    "stepfun-ai": "StepFun", "stepfun": "StepFun", "bytedance": "ByteDance", "bytedance-seed": "ByteDance",
    "baidu": "Baidu", "aion-labs": "Aion Labs", "cohere": "Cohere", "amazon": "Amazon", "microsoft": "Microsoft",
    "ibm-granite": "IBM", "lgai-exaone": "LG AI Research", "upstage": "Upstage", "inclusionai": "Ant Group",
    "sakana": "Sakana AI", "perplexity": "Perplexity", "cognitivecomputations": "Cognitive Computations",
    "nousresearch": "Nous Research", "kt": "KT", "rekaai": "Reka AI",
}
# the maker part a route writes before the name, where it differs from the maker's own name
MAKER_TEXT = {"aionlabs": "Aion Labs", "liquidai": "Liquid AI", "moonshotai": "Moonshot AI", "qwen": "Alibaba",
              "mistral": "Mistral AI", "z.ai": "Z.ai", "inclusionai": "Ant Group", "sakana": "Sakana AI",
              "nous": "Nous Research", "spacexsi": "xAI", "bytedance seed": "ByteDance", "reflection": "Reflection AI"}
COUNTRY: dict[str, str] = {
    "Anthropic": US, "OpenAI": US, "Google": US, "xAI": US, "Meta": US, "NVIDIA": US, "Thinking Machines": US,
    "Reflection AI": US, "Liquid AI": US, "Venice": US, "Amazon": US, "Microsoft": US, "IBM": US, "Perplexity": US,
    "Cognitive Computations": US, "Nous Research": US, "Reka AI": US, "Mistral AI": FR, "DeepSeek": CN, "Z.ai": CN, "Alibaba": CN,
    "Moonshot AI": CN, "MiniMax": CN, "Xiaomi": CN, "Tencent": CN, "Meituan": CN, "StepFun": CN, "ByteDance": CN,
    "Baidu": CN, "Ant Group": CN, "Aion Labs": IL, "Cohere": CA, "LG AI Research": KR, "Upstage": KR, "KT": KR,
    "Sakana AI": JP,
}
UNKNOWN_WORDS = ("beam", "big pickle", "big-pickle", "iceman", "flint", "tidepool", "pareto")


def split_maker(name: str) -> tuple[str | None, str]:
    """'Z.ai: GLM 5.3 Flash' → ('Z.ai', 'GLM 5.3 Flash'); a name without a maker part comes back whole. A name of
    one plain word keeps the maker in front ('Perplexity: Sonar' → 'Perplexity Sonar'), since 'Sonar' or
    'Uncensored' alone says too little."""
    name = " ".join(name.split())
    if ": " in name:
        maker, rest = (p.strip() for p in name.split(": ", 1))
        if maker and rest and len(maker) <= 40:
            return maker, rest if len(rest.split()) > 1 or any(c.isdigit() for c in rest) else f"{maker} {rest}"
    return None, name


def _known(maker: str) -> tuple[str, str | None]:
    m = MAKER_TEXT.get(maker.lower(), maker)
    return m, COUNTRY.get(m)


def maker_of(model_id: str, name: str, maker_text: str | None = None) -> tuple[str | None, str | None]:
    low_id, low = model_id.lower(), name.lower()
    if "/" in low_id:
        pre = low_id.split("/", 1)[0].lstrip("~")
        if pre in PREFIX:
            return _known(PREFIX[pre])
    if maker_text and maker_text.lower() not in ("openrouter",):
        return _known(maker_text)
    if any(w in low or w in low_id for w in UNKNOWN_WORDS):
        return None, None
    last = re.sub(r"^(e2ee-|[a-z0-9]+-(?:ai|org|labs)-)", "", low_id.split("/")[-1])
    for word, maker, country in FAMILIES:
        if re.match(rf"{word}(?![a-z])", last) or re.match(rf"{word}(?![a-z])", low):
            return maker, country
    return None, None


# words of a name or the start of a description that mark a model built for something other than conversation
_SPECIAL = re.compile(r"\b(content safety|guard|safeguard|sonar|search|ui-tars|hy-mt\d*|translat\w*|extract|summarize|"
                      r"relace|morph|embed\w*|rerank\w*|moderation|schematron)\b", re.I)


def special_purpose(name: str, description: str = "") -> bool:
    """Not a chat model: a safety classifier, a search engine, a translator, a screen agent, a code-apply model.
   They answer chat calls but do not play a conversation game."""
    return bool(_SPECIAL.search(name)) or bool(re.match(r"^\W*(a |an )?(safety classifier|translation model|"
                                                         r"gui agent|code apply)", description.lower()))


LADDER = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]


def efforts(levels: list[str] | None) -> list[str]:
    """A route's effort list in the app's order, low to high; unknown words go last."""
    got = [str(v) for v in levels or [] if v]
    return sorted(dict.fromkeys(got), key=lambda v: (LADDER.index(v) if v in LADDER else len(LADDER), v))


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\bfree\b", "", name.lower())).strip()


@lru_cache(maxsize=1)
def _training() -> tuple[frozenset[str], frozenset[str]]:
    data = json.loads(resources.files("nmb.data").joinpath("training_models.json").read_text("utf-8"))
    return frozenset(_norm(n) for n in data["names"]), frozenset(_norm(n) for n in data["zen_free_documented"])


def trains(name: str, zen_free: bool = False) -> bool:
    """The route may train on prompts. A Zen free model the docs do not list either way is unknown, and unknown
    counts as training, so it stays hidden while the switch is off."""
    names, documented = _training()
    n = _norm(name)
    return n in names or "contributor" in n or zen_free and n not in documented
