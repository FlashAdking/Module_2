import re
from typing import List
from app.schemas.project import RequirementModel

# Regex that matches an explicit upstream requirement ID at the start of a line.
# Supports: REQ-001, REQ001, UC-01, US-42, FEAT-003, etc.
_EXPLICIT_ID_RE = re.compile(
    r'^(?P<id>(?:REQ|UC|US|FEAT|FR)-?\d+)\s*',
    re.IGNORECASE,
)

# A line is an "Acceptance Criteria header" if it matches this pattern.
_AC_HEADER_RE = re.compile(r'^\s*acceptance\s+criteria\s*:?\s*$', re.IGNORECASE)

# Bullet prefix patterns that should be stripped from AC items.
# Handles: "- item", "* item", "• item", "1. item", "1) item"
_BULLET_RE = re.compile(r'^(?:[-*•✓✗]\s+|\d+[.)]\s*)')


def _split_into_blocks(text: str) -> List[str]:
    """
    Split raw text into requirement blocks.
    A block ends at a blank line OR when a new explicit REQ-ID header is seen.
    """
    lines = text.splitlines()
    blocks: List[List[str]] = []
    current: List[str] = []

    for line in lines:
        # Blank line → flush current block, start a new one
        if not line.strip():
            if current:
                blocks.append(current)
                current = []
            continue

        # If this line starts an explicit ID and we already have content,
        # flush so each requirement becomes its own block.
        if _EXPLICIT_ID_RE.match(line.strip()) and current:
            blocks.append(current)
            current = []

        current.append(line)

    if current:
        blocks.append(current)

    return [b for b in blocks if any(l.strip() for l in b)]


def parse_requirements_text(
    text: str,
    *,
    preserve_upstream_ids: bool = False,
) -> List[RequirementModel]:
    """
    Parse raw requirements text into structured RequirementModel objects.

    Requirement ID Ownership
    ────────────────────────
    By default Module 2 owns all IDs: upstream REQ-XXX tokens are stripped and
    fresh sequential IDs (REQ-001, REQ-002, …) are assigned.

    Pass ``preserve_upstream_ids=True`` only when the upstream document uses
    explicit, unique IDs that downstream consumers (e.g. test suites) need to
    reference verbatim.

    Acceptance Criteria Parsing
    ────────────────────────────
    Each block is scanned line-by-line.  Once an "Acceptance Criteria:" header
    is found (on any line within the block), every subsequent non-empty line is
    treated as an AC item regardless of whether the block contains a blank line
    between the header and the bullets.
    """
    requirements: List[RequirementModel] = []
    seq = 1

    blocks = _split_into_blocks(text)

    for block in blocks:
        lines = [l.strip() for l in block if l.strip()]
        if not lines:
            continue

        first_line = lines[0]

        # --- Determine requirement ID ---
        id_match = _EXPLICIT_ID_RE.match(first_line)
        if preserve_upstream_ids and id_match:
            req_id = id_match.group("id").upper()
            # Normalise: REQ001 → REQ-001 (insert hyphen if missing)
            req_id = re.sub(r'^([A-Z]+)(\d+)$', r'\1-\2', req_id)
            # Strip the ID token from the title
            title_raw = first_line[id_match.end():].strip().strip(':- ')
        else:
            req_id = f"REQ-{seq:03d}"
            seq += 1
            # Strip any upstream ID token so it doesn't pollute the title
            if id_match:
                title_raw = first_line[id_match.end():].strip().strip(':- ')
            else:
                title_raw = first_line.strip(':- ')

        title = title_raw if title_raw else f"Requirement {req_id}"

        # --- Parse description and acceptance criteria ---
        description_lines: List[str] = []
        acceptance_criteria: List[str] = []
        in_ac = False

        for line in lines[1:]:
            if _AC_HEADER_RE.match(line):
                in_ac = True
                continue

            if in_ac:
                cleaned = _BULLET_RE.sub('', line).strip()
                if cleaned:
                    acceptance_criteria.append(cleaned)
            else:
                description_lines.append(line)

        description = ' '.join(description_lines).strip() or "No description provided."

        requirements.append(RequirementModel(
            requirement_id=req_id,
            title=title,
            description=description,
            acceptance_criteria=acceptance_criteria,
        ))

    return requirements
