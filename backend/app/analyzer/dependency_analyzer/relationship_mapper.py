"""
relationship_mapper.py
─────────────────────
Module 2 relationship layer.

Produces two kinds of semantic links without any LLM or vector DB:

1. CodeRequirementLink  — associates functions/classes with requirements
   via a keyword overlap heuristic.

2. CodeTestLink — detects test functions in test files and maps them to
   the production symbols they exercise using naming conventions:
       test_create_user  →  create_user
       test_UserService  →  UserService
"""

import re
from typing import List, Set
from app.schemas.project import (
    FileModel,
    RequirementModel,
    CodeRequirementLink,
    CodeTestLink,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STOP_WORDS: Set[str] = {
    "the", "a", "an", "is", "in", "of", "to", "and", "or", "for",
    "with", "that", "this", "it", "be", "by", "as", "on", "at",
    "must", "shall", "should", "will", "can", "not", "no", "have",
    "has", "are", "was", "were", "from", "its", "all", "any",
    # NOTE: "user" and "system" are intentionally NOT stop words here —
    # they are high-signal tokens in code symbol names (create_user, UserService…)
}

_MIN_SCORE = 0.6  # minimum keyword overlap ratio to record a link
                  # 0.6 requires ≥60% of symbol tokens to match the requirement,
                  # preventing weak single-token matches (e.g. "user" alone)


def _tokenise(text: str) -> Set[str]:
    """Lower-case, split on non-alphanumeric chars, remove stop words."""
    raw = re.findall(r'[a-zA-Z]+', text.lower())
    return {w for w in raw if w not in _STOP_WORDS and len(w) > 2}


def _tokens_match(a: str, b: str) -> bool:
    """
    True when two tokens are the same or share a common stem prefix.

    Stem matching: "create" and "creation" share prefix "creat" (len 5 >= 4).
    Both tokens must be at least 4 chars to avoid false positives.

    Examples:
        create   ↔  creation   (shared prefix "creat", len 5)
        create   ↔  creating   (shared prefix "creat", len 5)
        user     ↔  users      (shared prefix "user",  len 4)
        list     ↔  listing    (shared prefix "list",  len 4)
    """
    if a == b:
        return True
    if len(a) >= 4 and len(b) >= 4:
        # Find length of common prefix
        common = 0
        for ca, cb in zip(a, b):
            if ca == cb:
                common += 1
            else:
                break
        return common >= 4
    return False


def _overlap(sym_toks: Set[str], req_toks: Set[str]) -> Set[str]:
    """Return the subset of sym_toks that fuzzy-match any token in req_toks."""
    matched: Set[str] = set()
    for s in sym_toks:
        for r in req_toks:
            if _tokens_match(s, r):
                matched.add(s)
                break
    return matched


def _camel_to_tokens(name: str) -> Set[str]:
    """Split camelCase / snake_case / PascalCase into token set."""
    # Insert space before uppercase letters that follow lowercase letters
    spaced = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', name)
    # Split on underscores and spaces
    parts = re.split(r'[_\s]+', spaced)
    return {p.lower() for p in parts if p and p.lower() not in _STOP_WORDS and len(p) > 2}


def _symbol_tokens(symbol_name: str) -> Set[str]:
    return _camel_to_tokens(symbol_name)


def _req_title_tokens(req: RequirementModel) -> Set[str]:
    """Tokens from the requirement title only — used for single-token symbol matching."""
    return _tokenise(req.title)


def _req_tokens(req: RequirementModel) -> Set[str]:
    """Tokens from the full requirement text (title + description + AC)."""
    text = f"{req.title} {req.description} {' '.join(req.acceptance_criteria)}"
    return _tokenise(text)


# ---------------------------------------------------------------------------
# Code → Requirement mapping
# ---------------------------------------------------------------------------

def map_code_to_requirements(
    files: List[FileModel],
    requirements: List[RequirementModel],
) -> List[CodeRequirementLink]:
    """
    For each function, method, and class in every file, compute keyword overlap
    with each requirement and emit a link when the score meets the threshold.

    Score = |symbol_tokens ∩ req_tokens| / |symbol_tokens|
    (how much of the symbol name is "explained" by the requirement text)
    """
    links: List[CodeRequirementLink] = []
    req_token_cache = {r.requirement_id: _req_tokens(r) for r in requirements}
    req_title_cache = {r.requirement_id: _req_title_tokens(r) for r in requirements}

    if not requirements:
        return links

    for f in files:
        # Test files exercise requirements indirectly — they are NOT
        # first-class requirement implementations, so skip them entirely.
        if _is_test_file(f.file):
            continue

        # Build symbol list: class names + methods + top-level functions.
        # Use a set to deduplicate symbols that appear both as a class method
        # and as a top-level function (e.g. create_user in main.py AND UserService).
        seen_names: set = set()
        symbols: List[tuple] = []

        for cls in f.classes:
            if cls.name not in seen_names:
                symbols.append((cls.name, "class"))
                seen_names.add(cls.name)
            # Include each method as its own symbol
            for method in cls.methods:
                if method not in seen_names:
                    symbols.append((method, "function"))
                    seen_names.add(method)

        for func in f.functions:
            if func.name not in seen_names:
                symbols.append((func.name, "function"))
                seen_names.add(func.name)

        for symbol_name, symbol_type in symbols:
            sym_toks = _symbol_tokens(symbol_name)
            if not sym_toks:
                continue

            for req in requirements:
                req_toks = req_token_cache[req.requirement_id]
                overlap = _overlap(sym_toks, req_toks)
                if not overlap:
                    continue

                # Guard: single-token symbols (e.g. class User) are too generic.
                # Require the token to appear in the requirement TITLE, not just
                # anywhere in the AC body where "user" is mentioned casually.
                if len(sym_toks) == 1:
                    tok = next(iter(sym_toks))
                    if tok not in req_title_cache[req.requirement_id]:
                        continue

                score = round(len(overlap) / len(sym_toks), 3)
                if score >= _MIN_SCORE:
                    links.append(CodeRequirementLink(
                        file=f.file,
                        symbol=symbol_name,
                        symbol_type=symbol_type,
                        requirement_id=req.requirement_id,
                        match_score=score,
                    ))

    return links


# ---------------------------------------------------------------------------
# Code → Test mapping
# ---------------------------------------------------------------------------

_TEST_FILE_RE = re.compile(r'(^|[/\\])(test[s]?[_/\\]|[_/\\]test[s]?[/\\])', re.IGNORECASE)
_TEST_FUNC_RE = re.compile(r'^test[_\s]', re.IGNORECASE)


def _is_test_file(filepath: str) -> bool:
    base = filepath.replace("\\", "/").split("/")[-1]
    return bool(_TEST_FILE_RE.search(filepath)) or base.startswith("test_") or base.endswith("_test.py")


def _extract_target_from_test_name(test_name: str) -> str:
    """
    Strip leading 'test_' / 'test' prefix to get the target symbol name.
    e.g.  test_create_user → create_user
          testUserService  → UserService
    """
    name = re.sub(r'^test[_]?', '', test_name, flags=re.IGNORECASE)
    return name


def map_code_to_tests(files: List[FileModel]) -> List[CodeTestLink]:
    """
    Detect test files and correlate test functions with production symbols
    using naming conventions.  Also handles ``test_<ClassName>_<method>`` style.
    """
    links: List[CodeTestLink] = []

    # Build index: symbol_name_lower → (file, symbol_name, type)
    symbol_index: dict = {}
    for f in files:
        if _is_test_file(f.file):
            continue
        for cls in f.classes:
            symbol_index[cls.name.lower()] = (f.file, cls.name, "class")
            for method in cls.methods:
                compound = f"{cls.name}_{method}".lower()
                symbol_index[compound] = (f.file, f"{cls.name}.{method}", "class")
        for func in f.functions:
            symbol_index[func.name.lower()] = (f.file, func.name, "function")

    for f in files:
        if not _is_test_file(f.file):
            continue

        for func in f.functions:
            if not _TEST_FUNC_RE.match(func.name):
                continue

            target_raw = _extract_target_from_test_name(func.name).lower()
            if not target_raw:
                continue

            if target_raw in symbol_index:
                prod_file, prod_symbol, prod_type = symbol_index[target_raw]
                links.append(CodeTestLink(
                    test_file=f.file,
                    test_function=func.name,
                    target_file=prod_file,
                    target_symbol=prod_symbol,
                    target_type=prod_type,
                ))

    return links
