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
    # Database agent: only files with clear persistence-layer signals.
    # A plain models.py in engine/, app/, or backend/ is a Pydantic/domain model,
    # NOT a database model — it must not route to this agent.
    "database": re.compile(
        r"""
        (^|/)alembic(/|\.)            # Alembic migration directories
        | (^|/)migrations?(/|\.)      # Django / SQLAlchemy migrations
        | (^|/)flyway(/|\.)           # Flyway migrations
        | (^|/)liquibase(/|\.)        # Liquibase migrations
        | (^|/)prisma(/|\.)           # Prisma schema directory
        | schema\.prisma$             # Prisma schema file
        | \.sql$                      # Raw SQL files
        | (^|/)db/models?(/|\.)       # models under explicit db/ prefix
        | (^|/)database/models?(/|\.) # models under explicit database/ prefix
        | (^|/)entity(/|\.)           # JPA / TypeORM entity classes
        | (^|/)repository(/|\.)       # Repository / DAO pattern
        """,
        re.I | re.VERBOSE,
    ),
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


# Keyword lists used only to RANK files that already matched a domain above — never to
# decide domain membership. A file basename hit is a stronger signal than a hit that
# only occurs somewhere in the directory path.
_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "security": ("auth", "authn", "authz", "login", "session", "jwt", "oauth", "security",
                 "payment", "billing", "checkout", "stripe"),
    "database": ("migration", "alembic", "schema", "prisma", "entity", "repository", "model"),
    "performance": ("cache", "redis", "queue", "worker", "perf", "benchmark", "index"),
    "api": ("route", "controller", "api", "graphql", "endpoint"),
    "tests": ("test", "spec"),
}


def _basename(filename: str) -> str:
    return filename.rsplit("/", 1)[-1].lower()


def _match_strength(filename: str, domain: str) -> int:
    """Deterministic score of how strongly a file matches a domain: keyword hits in
    the filename count double, keyword hits anywhere else in the path count once."""
    lower = filename.lower()
    base = _basename(filename)
    score = 0
    for kw in _DOMAIN_KEYWORDS.get(domain, ()):
        if kw in base:
            score += 2
        elif kw in lower:
            score += 1
    return score


def rank_files_for_domain(files: list[ChangedFile], domain: str) -> list[ChangedFile]:
    """Rank files that have ALREADY been matched to `domain` (via files_for_domain) so
    the most useful evidence is selected first when a downstream cap is applied. This
    does not change domain membership — it only orders already-matched files.

    Ranking, highest priority first:
      1. strength of domain/path match (keyword hits, filename beats directory)
      2. exact filename keyword match (basename hit)
      3. change relevance (total lines changed)
      4. patch size — tie-breaker only
    Fully deterministic; no LLM involved.
    """

    def sort_key(f: ChangedFile) -> tuple:
        strength = _match_strength(f.filename, domain)
        basename_hit = 1 if any(kw in _basename(f.filename) for kw in _DOMAIN_KEYWORDS.get(domain, ())) else 0
        change_relevance = f.additions + f.deletions
        patch_size = len(f.patch or "")
        return (-strength, -basename_hit, -change_relevance, -patch_size)

    return sorted(files, key=sort_key)
