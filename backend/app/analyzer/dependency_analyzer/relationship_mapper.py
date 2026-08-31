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

_MIN_SCORE = 0.15  # minimum keyword overlap ratio to record a link
                   # We now use strict rule-based guards (e.g. Action + Entity)
                   # so we don't rely purely on a high threshold.

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
    # Split on underscores, spaces, and dots
    parts = re.split(r'[_\s\.]+', spaced)
    return {p.lower() for p in parts if p and p.lower() not in _STOP_WORDS and len(p) > 2}


def _symbol_tokens(symbol_name: str) -> Set[str]:
    raw_toks = _camel_to_tokens(symbol_name)
    final: Set[str] = set()
    for t in raw_toks:
        matched = False
        for f in list(final):
            if _tokens_match(t, f):
                matched = True
                # Keep the shorter token as the stem
                if len(t) < len(f):
                    final.remove(f)
                    final.add(t)
                break
        if not matched:
            final.add(t)
    return final


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
    For each function, method, and class in every file, compute a match score
    with each requirement using multiple sources of evidence (name, route, etc)
    and emit a link when the score meets the threshold.
    """
    links: List[CodeRequirementLink] = []
    req_token_cache = {r.requirement_id: _req_tokens(r) for r in requirements}
    req_title_cache = {r.requirement_id: _req_title_tokens(r) for r in requirements}

    if not requirements:
        return links

    for f in files:
        if _is_test_file(f.file):
            continue
            
        file_base = f.file.replace("\\", "/").split("/")[-1].split(".")[0]
        file_toks = _symbol_tokens(file_base)

        func_routes = {route.function_name: route for route in f.api_routes}
        seen_names: set = set()
        symbols: List[tuple] = []

        for cls in f.classes:
            if cls.name not in seen_names:
                symbols.append((cls.name, "class"))
                seen_names.add(cls.name)
            for method in cls.methods:
                compound = f"{cls.name}.{method}"
                if compound not in seen_names:
                    symbols.append((compound, "function"))
                    seen_names.add(compound)

        for func in f.functions:
            if func.name not in seen_names:
                symbols.append((func.name, "function"))
                seen_names.add(func.name)

        for symbol_name, symbol_type in symbols:
            sym_toks = _symbol_tokens(symbol_name)
            if not sym_toks:
                continue

            route = func_routes.get(symbol_name)

            for req in requirements:
                req_toks = req_token_cache[req.requirement_id]
                req_title_toks = req_title_cache[req.requirement_id]
                
                # Guard: single-token symbols (e.g. class User) must match title.
                # Guard: single-token symbols (e.g. class User) must match title exactly.
                if len(sym_toks) == 1:
                    tok = next(iter(sym_toks))
                    if not _overlap({tok}, req_title_toks):
                        continue
                        
                # 1. Symbol vs Body
                body_overlap = _overlap(sym_toks, req_toks)
                
                # Guard: multi-token symbols (e.g. create_user) MUST have at least
                # 2 overlapping tokens to ensure we match Action + Entity, not just a generic noun.
                if len(sym_toks) > 1 and len(body_overlap) < 2:
                    continue
                        
                score = 0.0
                evidence = []

                # 2. Symbol vs Title (High weight: 0.4)
                title_overlap = _overlap(sym_toks, req_title_toks)
                if title_overlap:
                    ratio = len(title_overlap) / len(sym_toks)
                    score += ratio * 0.4
                    evidence.append(f"Symbol '{symbol_name}' shares {len(title_overlap)} token(s) with requirement title")

                if body_overlap:
                    ratio = len(body_overlap) / len(sym_toks)
                    score += ratio * 0.4
                    evidence.append(f"Symbol '{symbol_name}' shares {len(body_overlap)} token(s) with requirement text")

                # 3. File Context (0.1)
                file_overlap = _overlap(file_toks, req_toks)
                if file_overlap:
                    score += 0.1
                    evidence.append(f"File context '{file_base}' matches requirement text")

                # 4. API Route Context (0.4 max)
                if route:
                    path_toks = _tokenise(route.path)
                    path_overlap = _overlap(path_toks, req_toks)
                    if path_overlap:
                        score += 0.2
                        evidence.append(f"API path '{route.path}' matches requirement text")
                        
                    method = route.method.upper()
                    if method in ("POST", "PUT", "PATCH") and any(w in req_toks for w in ["create", "add", "update", "insert", "creation"]):
                        score += 0.2
                        evidence.append(f"HTTP {method} aligns with creation/update intent")
                    elif method == "GET" and any(w in req_toks for w in ["list", "fetch", "get", "retrieve", "read", "listing"]):
                        score += 0.2
                        evidence.append(f"HTTP GET aligns with listing/fetching intent")
                    elif method == "DELETE" and any(w in req_toks for w in ["delete", "remove"]):
                        score += 0.2
                        evidence.append(f"HTTP DELETE aligns with deletion intent")

                final_score = min(round(score, 3), 1.0)
                if final_score >= _MIN_SCORE:
                    links.append(CodeRequirementLink(
                        file=f.file,
                        symbol=symbol_name,
                        symbol_type=symbol_type,
                        requirement_id=req.requirement_id,
                        match_score=final_score,
                        evidence=evidence
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
    using semantic naming matches (e.g. test_user_creation → create_user).
    """
    links: List[CodeTestLink] = []

    # Build flat list of all production symbols with their tokens
    prod_symbols = []
    for f in files:
        if _is_test_file(f.file):
            continue
        for cls in f.classes:
            prod_symbols.append((f.file, cls.name, "class", _symbol_tokens(cls.name)))
            for method in cls.methods:
                # For matching, we match against the method name tokens
                prod_symbols.append((f.file, method, "function", _symbol_tokens(method)))
        for func in f.functions:
            prod_symbols.append((f.file, func.name, "function", _symbol_tokens(func.name)))

    for f in files:
        if not _is_test_file(f.file):
            continue
            
        test_file_base = f.file.replace("\\", "/").split("/")[-1].split(".")[0]
        test_file_toks = _symbol_tokens(test_file_base)
        test_file_toks.discard("test")

        for func in f.functions:
            if not _TEST_FUNC_RE.match(func.name):
                continue

            test_toks = _symbol_tokens(func.name)
            test_toks.discard("test")
            if not test_toks:
                continue

            best_score = 0.0
            best_match = None

            best_evidence = []

            for prod_file, prod_name, prod_type, prod_toks in prod_symbols:
                if not prod_toks:
                    continue
                
                score = 0.0
                overlap = _overlap(test_toks, prod_toks)
                current_evidence = []
                
                if overlap:
                    # Dice coefficient style scoring
                    score = (2.0 * len(overlap)) / (len(test_toks) + len(prod_toks))
                    current_evidence.append(f"Semantic match between '{func.name}' and '{prod_name}'")
                    
                # Bonus if the prod symbol is in a file that matches the test file's name
                prod_file_base = prod_file.replace("\\", "/").split("/")[-1].split(".")[0]
                prod_file_toks = _symbol_tokens(prod_file_base)
                if _overlap(test_file_toks, prod_file_toks):
                    score += 0.2
                    current_evidence.append(f"File context match: test file '{test_file_base}' matches production file '{prod_file_base}'")
                    
                # Exact match bonus (test_create_user == create_user)
                if len(overlap) == len(test_toks) == len(prod_toks):
                    score += 0.5
                    current_evidence.append(f"Exact naming convention match")
                    
                if score > best_score:
                    best_score = score
                    best_match = (prod_file, prod_name, prod_type)
                    best_evidence = current_evidence

            if best_match and best_score >= 0.5:
                links.append(CodeTestLink(
                    test_file=f.file,
                    test_function=func.name,
                    target_file=best_match[0],
                    target_symbol=best_match[1],
                    target_type=best_match[2],
                    evidence=best_evidence
                ))

    return links
