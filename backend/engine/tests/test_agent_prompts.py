from __future__ import annotations

from engine.agents.nodes import MAX_FILES_PER_AGENT, MAX_PATCH_CHARS, MAX_PATCH_LINES, _files_prompt
from engine.models import ChangedFile


def _file(name: str, lines: int, line_len: int = 10) -> ChangedFile:
    patch = "\n".join(f"+{'x' * line_len}_{i}" for i in range(lines))
    return ChangedFile(filename=name, status="modified", additions=lines, deletions=0, changes=lines, patch=patch)


def test_prompt_states_total_vs_shown_file_counts():
    files = [_file(f"src/file_{i}.py", 5) for i in range(MAX_FILES_PER_AGENT + 2)]
    prompt = _files_prompt(files)
    assert f"{len(files)} file(s) are in this agent's scope" in prompt
    assert f"{MAX_FILES_PER_AGENT} are shown below" in prompt
    assert "2 more file(s) in scope that are NOT shown at all" in prompt


def test_prompt_flags_line_truncation_per_file():
    files = [_file("src/big_file.py", MAX_PATCH_LINES + 10)]
    prompt = _files_prompt(files)
    assert "TRUNCATED" in prompt
    assert f"showing {MAX_PATCH_LINES} of {MAX_PATCH_LINES + 10} patch lines" in prompt


def test_prompt_does_not_claim_truncation_for_small_patch():
    files = [_file("src/small_file.py", 3, line_len=5)]
    prompt = _files_prompt(files)
    assert "(full patch shown)" in prompt
    assert "TRUNCATED" not in prompt


def test_prompt_flags_char_truncation_when_lines_fit_but_chars_dont():
    # Few lines, but each line is long enough that MAX_PATCH_CHARS is hit first.
    files = [_file("src/wide_file.py", 2, line_len=MAX_PATCH_CHARS)]
    prompt = _files_prompt(files)
    assert "TRUNCATED" in prompt


def test_prompt_includes_explicit_no_inference_instruction():
    files = [_file("src/file.py", 1)]
    prompt = _files_prompt(files)
    assert "Do not infer behavior from code that was not shown" in prompt
    assert "lower confidence" in prompt
