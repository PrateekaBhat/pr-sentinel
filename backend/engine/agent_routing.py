from __future__ import annotations

import re

from .models import ChangedFile

# Each agent only ever sees the files matching its own domain — this is what makes the
# multi-agent split meaningful rather than decorative: different domains get different
# context, not the same diff five times with a different system prompt.
DOMAIN_PATTERNS: dict[str, re.Pattern] = {
    "security": re.compile(
        r"(^|/)(auth|authn|authz|login|session|jwt|oauth|security|payment|billing|checkout|stripe)(/|\.)",
        re.I,
    ),
    "database": re.compile(r"(^|/)(migrations?|schema|models?|entity|repository)(/|\.)|\.sql$", re.I),
    "performance": re.compile(r"(^|/)(cache|redis|queue|worker|perf|benchmark|index)(/|\.)", re.I),
    "api": re.compile(r"(^|/)(routes?|controllers?|api|graphql|endpoints?)(/|\.)", re.I),
    "tests": re.compile(r"(^|/)(tests?|__tests__|spec)(/|\.)|\.(test|spec)\.", re.I),
}

DOMAIN_LABELS = {
    "security": "Security",
    "database": "Database",
    "performance": "Performance",
    "api": "API Compatibility",
    "tests": "Test Coverage",
}


def files_for_domain(files: list[ChangedFile], domain: str) -> list[ChangedFile]:
    pattern = DOMAIN_PATTERNS[domain]
    return [f for f in files if pattern.search(f.filename)]
