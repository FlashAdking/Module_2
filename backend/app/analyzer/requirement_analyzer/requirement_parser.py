import re
from typing import List
from app.schemas.project import RequirementModel

def parse_requirements_text(text: str) -> List[RequirementModel]:
    """
    Parses raw requirements text (extracted by Module 1) into structured
    RequirementModel objects.

    Requirement ID Ownership
    ────────────────────────
    Module 2 is solely responsible for creating Requirement IDs.
    Any IDs present in the upstream document are stripped and discarded.
    IDs are always assigned sequentially: REQ-001, REQ-002, REQ-003, ...
    This guarantees uniqueness and consistency across all projects.
    """
    requirements = []
    req_counter = 1

    # Split into logical blocks on blank lines
    blocks = re.split(r'\n\s*\n', text.strip())

    for block in blocks:
        if not block.strip():
            continue

        lines = [line.strip() for line in block.split('\n') if line.strip()]
        if not lines:
            continue

        # Always assign a fresh sequential ID — Module 2 owns all REQ IDs
        req_id = f"REQ-{req_counter:03d}"
        req_counter += 1

        # Strip any pre-existing REQ-XXX token from the title (upstream artifact)
        title = re.sub(r'REQ-\d+\s*', '', lines[0], flags=re.IGNORECASE).strip(':- ')
        if not title:
            title = f"Requirement {req_id}"

        description_lines = []
        acceptance_criteria = []

        in_ac = False
        for line in lines[1:]:
            if re.search(r'acceptance criteria', line, re.IGNORECASE):
                in_ac = True
                continue

            if in_ac:
                # Strip bullet prefixes: -, *, •, 1.
                ac_line = re.sub(r'^[-*•\d\.]+\s*', '', line)
                if ac_line:
                    acceptance_criteria.append(ac_line)
            else:
                description_lines.append(line)

        description = ' '.join(description_lines)
        if not description:
            description = "No description provided."

        requirements.append(RequirementModel(
            requirement_id=req_id,
            title=title,
            description=description,
            acceptance_criteria=acceptance_criteria
        ))

    return requirements
