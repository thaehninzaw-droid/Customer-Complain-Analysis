"""
Lightweight, dependency-free sentiment + urgency scoring.

WHY THIS FILE EXISTS INSTEAD OF USING NLTK/VADER/TextBlob:
Those libraries either need an internet download at runtime (NLTK's
`vader_lexicon` corpus) or an extra dependency the team may not have
installed. This is a small, self-contained lexicon in plain Python -
zero downloads, zero extra dependencies, and every weight is visible
and editable in one place. It's deliberately simple: this is the
"how a signal gets computed today" half of the Strategy Pattern used
throughout this codebase (see classify.py) - `app/priority.py` is the
only thing that calls into this file, so the scoring approach here
can be swapped for a real VADER/transformer model later without
touching anything else.

Two scores are produced per complaint:
  - polarity   : -1 (very negative) .. +1 (very positive)
  - urgency    :  0 (no urgency signal) .. 1 (very urgent)

These feed into app/priority.py's rule-based priority baseline, AND
are used as engineered features for the trained priority model in
app/ml/train_priority.py (see docs/ALGORITHMS.md for the full writeup
of why - this is a "distant supervision" setup: a documented, hand-
built heuristic bootstraps labels for a supervised model, which is a
real, citable ML technique for when hand-labeled data doesn't exist).
"""
import re

# ---------------------------------------------------------------------------
# Lexicon. Scores are on a simple -3..+3 scale per word (loosely modeled on
# the AFINN wordlist idea, but hand-curated and much smaller - tuned for the
# vocabulary that actually shows up in telecom/customer-service complaints
# rather than general text).
# ---------------------------------------------------------------------------

NEGATIVE_WORDS = {
    # strong negative / anger
    "furious": -3, "outrageous": -3, "unacceptable": -3, "disgusting": -3,
    "horrible": -3, "terrible": -3, "awful": -3, "worst": -3, "scam": -3,
    "fraud": -3, "cheated": -3, "ridiculous": -3, "disgusted": -3,
    "appalling": -3, "livid": -3, "furiously": -3, "sue": -3, "lawsuit": -3,
    # moderate negative
    "rude": -2, "annoyed": -2, "annoying": -2, "frustrated": -2,
    "frustrating": -2, "disappointed": -2, "disappointing": -2,
    "unhappy": -2, "poor": -2, "broken": -2, "useless": -2, "slow": -2,
    "overcharged": -2, "overcharge": -2, "incompetent": -2, "ignored": -2,
    "unresolved": -2, "failed": -2, "failing": -2, "unreliable": -2,
    "problem": -2, "problems": -2, "issue": -2, "issues": -2, "complaint": -2,
    "wrong": -2, "error": -2, "errors": -2, "delay": -2, "delayed": -2,
    "cancel": -2, "cancelled": -2, "cancelling": -2, "refuse": -2, "refused": -2,
    # mild negative
    "confusing": -1, "confused": -1,
    "difficult": -1, "hard": -1, "inconvenient": -1, "concerned": -1,
    "unfortunately": -1, "unfortunate": -1, "not working": -1,
    "down": -1, "disconnect": -1, "disconnected": -1, "disconnecting": -1,
    # Banking-specific negative words (Decision 34)
    "unauthorized": -3, "theft": -3, "stolen": -3, "garnished": -3,
    "garnishment": -3, "foreclosed": -3, "repossessed": -3,
    "deceptive": -3, "predatory": -3, "harassing": -3, "harassment": -3,
    "threatening": -2, "threat": -2, "inaccurate": -2, "incorrect": -2,
    "wrongful": -2, "misleading": -2, "overcharged": -2,
    "excessive": -2, "hidden fee": -2, "hidden fees": -2,
    "never received": -2, "not received": -2, "denied": -2,
}

POSITIVE_WORDS = {
    "excellent": 3, "amazing": 3, "wonderful": 3, "fantastic": 3,
    "great": 2, "good": 2, "helpful": 2, "fixed": 2,
    "satisfied": 2, "pleased": 2, "appreciate": 2, "appreciated": 2,
    "thanks": 1, "thank": 1, "thankful": 1, "quick": 1, "fast": 1,
    "friendly": 1, "polite": 1, "professional": 1, "nice": 1, "happy": 1,
    # deliberately low weight: "resolved" shows up almost as often in
    # NOT-yet-resolved requests ("I need this resolved") as in genuine
    # positive feedback ("my issue was resolved") - a known limitation
    # of word-level lexicons with no real context understanding.
    "resolved": 1,
}

# Words/phrases that signal time-pressure or escalation, independent of
# sentiment polarity - these push priority UP even when phrased calmly
# ("this has been unresolved for three weeks").
# Decision 34: added banking-specific urgency signals (overdraft, foreclosure,
# unauthorized charge, collections call, etc.) alongside the original set.
URGENCY_TERMS = {
    "immediately": 3, "urgent": 3, "urgently": 3, "asap": 3, "emergency": 3,
    "right now": 3, "escalate": 2, "escalation": 2, "supervisor": 2,
    "manager": 2, "again": 2, "still not": 2, "still no": 2, "never": 2,
    "no one": 2, "nobody": 2, "third time": 3, "multiple times": 2,
    "repeatedly": 2, "for weeks": 3, "for days": 2, "for months": 3,
    "no response": 2, "no reply": 2, "unresponsive": 2, "unresolved": 2,
    "keeps happening": 2, "every time": 2,
    "cannot work": 2, "can't work": 2, "losing money": 3, "lost money": 2,
    "deadline": 2, "today": 1, "hours": 1, "on hold": 1, "on hold for": 2,
    "cannot wait any longer": 3, "can't wait any longer": 3,
    "can not wait": 2, "won't wait": 2, "keep waiting": 2,
    "still waiting": 2, "long hold": 2,
    # Banking-specific urgency signals
    "overdraft": 3, "foreclosure": 3, "repo": 2, "repossession": 3,
    "unauthorized charge": 3, "unauthorized transaction": 3,
    "identity theft": 3, "fraud": 3, "fraudulent": 3,
    "collections call": 2, "collections notice": 2, "wage garnishment": 3,
    "garnished": 3, "lawsuit": 3, "judgment": 3, "legal action": 3,
    "account closed": 2, "account frozen": 3, "account blocked": 3,
    "funds held": 2, "hold on funds": 2, "cannot access": 2,
    "eviction": 3, "three times": 3, "twice": 2, "second time": 2,
}

NEGATION_WORDS = {
    "not", "no", "never", "without", "hardly", "barely", "cannot",
    "can't", "don't", "doesn't", "didn't", "isn't", "aren't", "wasn't",
    "weren't", "won't", "wouldn't", "shouldn't", "couldn't", "ain't",
}


def _is_negator(token: str) -> bool:
    return token in NEGATION_WORDS or token.endswith("n't")

# Phrases that explicitly de-escalate urgency even though they contain
# an urgency-looking word ("not urgent", "no rush") - checked before the
# URGENCY_TERMS scan so they cancel out rather than double-count.
DEESCALATION_PHRASES = {
    "not urgent", "no rush", "no hurry", "not a big deal", "no urgency",
    "whenever you can", "whenever you get a chance", "not an emergency",
    "no need to rush",
}

_WORD_RE = re.compile(r"[a-zA-Z']+")


def _tokenize(text: str):
    return _WORD_RE.findall(text.lower())


def score_polarity(text: str) -> float:
    """Returns a polarity score roughly in [-1, 1]. Negative = unhappy
    customer. Applies simple negation handling (a negative word within
    two tokens after "not"/"no"/etc. flips its sign, so "not happy"
    doesn't get scored as positive)."""
    tokens = _tokenize(text)
    if not tokens:
        return 0.0

    total = 0.0
    hits = 0
    for i, tok in enumerate(tokens):
        score = NEGATIVE_WORDS.get(tok, POSITIVE_WORDS.get(tok))
        if score is None:
            continue
        negated = any(_is_negator(t) for t in tokens[max(0, i - 2):i])
        if negated:
            score = -score
        total += score
        hits += 1

    if hits == 0:
        return 0.0
    # Normalize: average per matched word, scaled down to roughly [-1, 1]
    # (average matched-word score maxes out around +/-3).
    return max(-1.0, min(1.0, (total / hits) / 3.0))


def _phrase_pattern(phrase: str) -> re.Pattern:
    return re.compile(r"\b" + re.escape(phrase) + r"\b")


# Precompiled once at import time - naive `phrase in text` substring
# checks have a real false-positive problem for short phrases (e.g.
# "never" matching inside "whenever", which happened in practice and
# is exactly why this exists instead - see docs/ALGORITHMS.md).
_URGENCY_PATTERNS = {phrase: _phrase_pattern(phrase) for phrase in URGENCY_TERMS}
_DEESCALATION_PATTERNS = [_phrase_pattern(phrase) for phrase in DEESCALATION_PHRASES]


def score_urgency(text: str) -> float:
    """Returns an urgency score in [0, 1]. Looks for both single-word
    and short-phrase urgency markers, plus surface-level shouting
    signals (ALL CAPS words, repeated exclamation marks)."""
    lowered = text.lower()
    raw = 0.0

    deescalated = any(pattern.search(lowered) for pattern in _DEESCALATION_PATTERNS)

    for phrase, weight in URGENCY_TERMS.items():
        if _URGENCY_PATTERNS[phrase].search(lowered):
            raw += weight
    if deescalated:
        raw -= 3.0

    # Shouting signals
    exclamations = text.count("!")
    raw += min(exclamations, 3) * 0.7

    words = re.findall(r"[A-Za-z']+", text)
    if words:
        caps_words = [w for w in words if len(w) >= 3 and w.isupper()]
        caps_ratio = len(caps_words) / len(words)
        if caps_ratio > 0.15:
            raw += 2.0

    question_marks = text.count("?")
    raw += min(question_marks, 2) * 0.3

    # Squash into [0, 1] with a soft cap - most real complaints won't
    # exceed a raw score of ~10.
    return max(0.0, min(1.0, raw / 10.0))


def analyze(text: str) -> dict:
    """Convenience wrapper returning both scores plus a couple of raw
    text-shape features that app/ml/train_priority.py also uses as
    engineered features for the trained model."""
    tokens = _tokenize(text)
    return {
        "polarity": score_polarity(text),
        "urgency": score_urgency(text),
        "length": len(text),
        "word_count": len(tokens),
        "exclamation_count": text.count("!"),
    }
