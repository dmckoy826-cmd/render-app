"""Name-based auto-matching of finishes to model layers/blocks.

DWG layers in casework/fixture drawings typically look like:
    LAM-WALNUT-FRONT, PET-CHARCOAL-ACCENT, MET-BRUSHED-TRIM, A1$0$M-DOOR

We tokenize names, detect a material category hint (laminate / PET / product finish)
and score every finish against every target by shared material tokens
(walnut, oak, charcoal, stainless, ...) plus category agreement.
"""
from __future__ import annotations

import re
from typing import Optional

# Tokens that describe *where* a material goes rather than *what* it is.
STOP_TOKENS = {
    "lam", "laminate", "hpl", "pet", "felt", "finish", "finishes", "mtl", "metal",
    "panel", "panels", "front", "fronts", "face", "faces", "top", "tops", "side",
    "sides", "body", "case", "carcass", "door", "doors", "drawer", "drawers",
    "trim", "edging", "edge", "band", "banding", "accent", "accents", "work",
    "worksurface", "counter", "modesty", "back", "shelf", "shelves", "base",
    "plinth", "leg", "legs", "pull", "pulls", "hardware", "assy", "assembly",
    "blk", "block", "det", "detail", "existing", "new", "note", "dims", "dim",
    "text", "grid", "anchor", "profile", "profiles", "sheet", "part", "parts",
    "finish", "fin", "mat", "material", "materials", "obj", "object", "objects",
}

# Token -> category hint
CATEGORY_TOKENS = {
    "laminate": {"lam", "laminate", "hpl", "veneer", "wood", "woodgrain", "grain"},
    "pet": {"pet", "felt", "acoustic", "fabric", "polyester"},
    "product_finish": {"metal", "met", "mtl", "steel", "stainless", "alum",
                       "aluminum", "brass", "bronze", "chrome", "hardware",
                       "pull", "hinge", "glass", "mirror", "stone", "quartz",
                       "solid", "surface", "acrylic", "powder", "coat", "anodized"},
}

# Words that carry real material/color meaning (the matching signal).
def _sig_tokens(name: str) -> set[str]:
    toks = set(re.findall(r"[a-z0-9]+", name.lower()))
    return {t for t in toks if len(t) >= 3 and t not in STOP_TOKENS and not t.isdigit()}


def category_hint(name: str) -> Optional[str]:
    toks = set(re.findall(r"[a-z0-9]+", name.lower()))
    for category, hints in CATEGORY_TOKENS.items():
        if toks & hints:
            return category
    return None


def score_pair(target_name: str, finish) -> float:
    """Score how well a finish matches a layer/block name. Returns 0..1."""
    lt = _sig_tokens(target_name)
    ft = _sig_tokens(finish.name) | _sig_tokens(finish.tags or "")
    if not lt or not ft:
        base = 0.0
    else:
        common = lt & ft
        # fraction of the layer's signal tokens explained by the finish
        base = 0.6 * min(1.0, len(common) / max(1, len(lt)))
        # substring bonus (e.g. "walnut" inside "Walnut Harvest")
        lname = target_name.lower()
        fname = (finish.name or "").lower()
        if any(t in fname for t in lt) or any(t in lname for t in ft):
            base += 0.15

    hint = category_hint(target_name)
    if hint and finish.category == hint:
        base += 0.25
    elif hint and finish.category != hint:
        base -= 0.15

    return max(0.0, min(1.0, round(base, 3)))


def suggest(target_names: list[str], finishes: list, min_score: float = 0.35) -> list[dict]:
    """Best finish per target name, sorted by score descending."""
    out = []
    for name in target_names:
        best, best_score = None, 0.0
        for f in finishes:
            s = score_pair(name, f)
            if s > best_score:
                best, best_score = f, s
        if best is not None and best_score >= min_score:
            out.append({"target_name": name, "finish": best, "score": best_score})
    out.sort(key=lambda d: d["score"], reverse=True)
    return out


def suggest_pattern(layer_name: str) -> str:
    """Pick the most distinctive token of a layer name for reusable preset rules."""
    sig = sorted(_sig_tokens(layer_name), key=len, reverse=True)
    return (sig[0] if sig else layer_name).upper()
