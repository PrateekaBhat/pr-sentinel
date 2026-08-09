"""Deterministic validation/normalization layer between specialist-agent model output
and final report rendering.

The LLM can produce findings that are structurally incomplete -- most commonly a
sentence fragment cut off mid-clause (e.g. "function exists with different return type
than"). This module never uses NLP or another model call to judge quality; it only
checks obvious, deterministic structural signals: is there a title, does it end
mid-sentence, is there evidence for a file-specific claim, is severity/confidence a
recognized value. Anything that fails is excluded rather than guessed at or patched
with fabricated content -- PR Sentinel would rather show fewer findings than show a
confident-looking claim that isn't actually finished.
"""

from __future__ import annotations

import re

from .models import Finding

# Words a genuine, complete sentence essentially never ends on. If a title or evidence
# string ends on one of these, it is almost certainly a truncated model output rather
# than a real short-but-complete finding.
_DANGLING_ENDINGS_RE = re.compile(
    r"\b(than|with|and|or|but|to|of|for|in|on|at|is|the|a|an|that|which|as|by|from|"
    r"than the|different|new)\s*$",
    re.I,
)

MIN_TITLE_WORDS = 3
MAX_TITLE_CHARS = 200
MAX_EVIDENCE_CHARS = 500

VALID_SEVERITIES = {"P0", "P1", "P2", "P3"}
VALID_CONFIDENCES = {"HIGH", "MEDIUM", "LOW"}


def _looks_truncated(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    return bool(_DANGLING_ENDINGS_RE.search(text))


def validate_finding(raw: dict) -> tuple[bool, str]:
    """Structural completeness check. Returns (is_valid, reason_if_invalid).

    Deliberately simple and deterministic -- no sophisticated NLP. This focuses on
    obvious incompleteness (empty/short/truncated title, missing evidence for a
    file-specific claim) rather than judging the *quality* of an otherwise complete,
    legitimately short finding.
    """
    title = str(raw.get("title") or "").strip()
    evidence = str(raw.get("evidence") or "").strip()
    file = str(raw.get("file") or "").strip()

    if not title:
        return False, "empty title"
    if len(title.split()) < MIN_TITLE_WORDS:
        return False, "title too short to be a complete finding"
    if len(title) > MAX_TITLE_CHARS:
        return False, "title exceeds length limit (likely unstructured model dump)"
    if _looks_truncated(title):
        return False, "title ends mid-sentence (truncated model output)"
    if not evidence:
        return False, "missing evidence"
    if _looks_truncated(evidence):
        return False, "evidence ends mid-sentence (truncated model output)"
    if len(evidence) > MAX_EVIDENCE_CHARS:
        return False, "evidence exceeds length limit"
    if file and not evidence:
        # Redundant with the missing-evidence check above, but kept explicit per the
        # requirement that file-specific claims always carry evidence.
        return False, "file-specific claim with no supporting evidence"

    return True, ""


def normalize_finding(raw: dict) -> Finding | None:
    """Validate a raw specialist finding dict and, if valid, build a Finding.

    Never fabricates missing fields. If the finding fails validation, returns None so
    the caller excludes it from the user-facing concern list rather than presenting an
    incomplete claim as finished.
    """
    if not isinstance(raw, dict):
        return None

    ok, _reason = validate_finding(raw)
    if not ok:
        return None

    severity = str(raw.get("severity", "P3")).upper().strip()
    if severity not in VALID_SEVERITIES:
        severity = "P3"

    confidence = str(raw.get("confidence", "MEDIUM")).upper().strip()
    if confidence not in VALID_CONFIDENCES:
        confidence = "MEDIUM"

    return Finding(
        title=str(raw.get("title") or "").strip(),
        evidence=str(raw.get("evidence") or "").strip(),
        impact=str(raw.get("impact") or "").strip(),
        recommendation=str(raw.get("recommendation") or "").strip(),
        file=(str(raw.get("file")).strip() or None) if raw.get("file") else None,
        severity=severity,
        confidence=confidence,
    )


def normalize_findings(raw_list: list) -> tuple[list[Finding], list[Finding], int]:
    """Normalize a raw list of specialist findings (dicts, or legacy free-form
    strings) into (actionable, needs_verification, rejected_count).

    - actionable: HIGH/MEDIUM confidence findings that passed validation.
    - needs_verification: LOW confidence findings that passed validation -- these
      should never appear as confident "Concerns raised" but can be shown under a
      clearly labeled needs-verification section.
    - rejected_count: findings that failed structural validation and were discarded
      entirely, per the safest existing reporting convention (never silently upgrade
      malformed model output into a confident claim).
    """
    actionable: list[Finding] = []
    needs_verification: list[Finding] = []
    rejected = 0

    for raw in raw_list:
        if isinstance(raw, str):
            # Legacy/degenerate shape: the model returned a bare string instead of a
            # structured object. There is no evidence field to validate against, so
            # this is treated the same as any other incomplete finding -- it fails
            # validation (missing evidence) and is discarded rather than guessed at.
            raw = {"title": raw}
        finding = normalize_finding(raw)
        if finding is None:
            rejected += 1
            continue
        if finding.confidence == "LOW":
            needs_verification.append(finding)
        else:
            actionable.append(finding)

    return actionable, needs_verification, rejected
