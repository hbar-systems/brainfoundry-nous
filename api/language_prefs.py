"""
language_prefs.py — the two language lines appended to the chat system prompt.

Two per-brain settings (api/settings_store.get_language): `answer` fixes the
language of the reply ("auto" = the language the person writes in);
`learning`, when not "off", makes the brain answer in the language the person
is learning and then repeat the same answer, under a thin rule, in their own
language; `balance` (0..100) is how much of the answer is in the learning
language (0 = a sentence or two, 100 = everything). The setting wins over any
language instruction in the persona; the lines say so. Defaults produce no
lines, so a brain that never touched Settings is unchanged. (hbar 2026-10-25)
"""
from typing import Any, Dict

LANGUAGES: Dict[str, str] = {
    "en": "English", "ru": "Russian", "de": "German", "sk": "Slovak",
    "es": "Spanish", "fr": "French", "it": "Italian", "uk": "Ukrainian",
}
ANSWER_DEFAULT = "auto"
LEARNING_DEFAULT = "off"
BALANCE_DEFAULT = 50


def language_name(code: str) -> str:
    """'ru' -> 'Russian (ru)'; free text ("other") is returned as written."""
    c = (code or "").strip()
    return f"{LANGUAGES[c]} ({c})" if c in LANGUAGES else c


def prompt_lines(answer: str = ANSWER_DEFAULT, learning: str = LEARNING_DEFAULT,
                 balance: int = BALANCE_DEFAULT) -> str:
    """The lines appended after the persona. Empty string when both settings
    are at their defaults (auto / off)."""
    answer = (answer or ANSWER_DEFAULT).strip()
    learning = (learning or LEARNING_DEFAULT).strip()
    try:
        balance = max(0, min(100, int(balance)))
    except (TypeError, ValueError):
        balance = BALANCE_DEFAULT
    if answer == ANSWER_DEFAULT and learning == LEARNING_DEFAULT:
        return ""
    own = "the language the person writes in" if answer == ANSWER_DEFAULT else language_name(answer)
    override = "This setting wins over any language instruction in the persona above."
    if learning == LEARNING_DEFAULT:
        return f"Language: answer in {own}, whatever language the person writes in. {override}"
    learn = language_name(learning)
    if balance >= 100:
        share = f"Write the whole answer in {learn}"
    elif balance <= 0:
        share = f"Write only a sentence or two of the answer in {learn} and the rest in {own}"
    else:
        share = f"Write about {balance}% of the answer in {learn} and the rest in {own}"
    line1 = f"Language: the person's own language is {own}."
    line2 = (f"Learning: the person is learning {learn}. {share}; then, under a thin rule (---), "
             f"give the same answer entirely in {own}, so they learn by reading both. {override}")
    return line1 + "\n" + line2


def prompt_lines_from(cfg: Dict[str, Any]) -> str:
    cfg = cfg or {}
    return prompt_lines(cfg.get("answer", ANSWER_DEFAULT), cfg.get("learning", LEARNING_DEFAULT),
                        cfg.get("balance", BALANCE_DEFAULT))
