"""Lint a cited memo: every number must cite evidence that reproduces it.

Only the regions between ``<!-- cited:start -->`` and ``<!-- cited:end -->`` are linted,
so narrative and how-to sections can mention versions or commands freely. Within a region
each non-heading line is a claim. A claim containing numbers must carry at least one
``[E:key]`` citation, every key must exist, and every number must equal one of the cited
values rounded to the precision written ("7.1%" matches 7.13; "7.2%" does not).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

START, END = "<!-- cited:start -->", "<!-- cited:end -->"
_CITE = re.compile(r"\[E:([\w.\-]+)\]")
_CODE = re.compile(r"`[^`]*`")
_LINK = re.compile(r"\]\([^)]*\)")
_LIST_MARKER = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")
_NUM = re.compile(r"(?<![\w.:/\-])([-\u2212])?\$?(\d[\d,]*)(?:\.(\d+))?(?:%|x)?(?![\w:/\-])")


@dataclass
class LintIssue:
    line_no: int
    line: str
    problem: str

    def __str__(self) -> str:
        return f"line {self.line_no}: {self.problem}\n    {self.line.strip()}"


def numbers_in(text: str) -> list[tuple[float, int]]:
    """(value, decimals written) for every number token in a claim, citations removed."""
    text = _CITE.sub(" ", text)
    text = _CODE.sub(" ", text)
    text = _LINK.sub("]", text)
    text = _LIST_MARKER.sub("", text)
    out = []
    for m in _NUM.finditer(text):
        sign, whole, frac = m.group(1), m.group(2).replace(",", ""), m.group(3)
        if not whole.isdigit():
            continue
        value = float(f"{whole}.{frac}" if frac else whole)
        out.append((-value if sign else value, len(frac or "")))
    return out


def _matches(written: float, decimals: int, value: float) -> bool:
    """Signed numbers must match exactly; unsigned ones may state a magnitude
    ("41% lower") of a negative value."""
    candidates = [value] if written < 0 else [value, abs(value)]
    return any(abs(round(v, decimals) - written) < 10 ** (-decimals) / 2 for v in candidates)


def lint_memo(text: str, evidence: dict[str, dict]) -> list[LintIssue]:
    issues: list[LintIssue] = []
    inside = False
    regions = 0
    for i, line in enumerate(text.splitlines(), start=1):
        if START in line:
            inside, regions = True, regions + 1
            continue
        if END in line:
            inside = False
            continue
        if not inside or line.lstrip().startswith("#"):
            continue
        nums = numbers_in(line)
        cites = _CITE.findall(line)
        missing = [c for c in cites if c not in evidence]
        if missing:
            issues.append(LintIssue(i, line, f"unknown evidence keys {missing}"))
            continue
        if nums and not cites:
            issues.append(LintIssue(i, line, "numeric claim without an [E:...] citation"))
            continue
        values = [evidence[c]["value"] for c in cites]
        for written, dec in nums:
            if not any(_matches(written, dec, v) for v in values):
                issues.append(LintIssue(
                    i, line, f"{written:g} does not match cited evidence {values}"))
        for c in cites:
            if not evidence[c].get("checks"):
                issues.append(LintIssue(i, line, f"evidence {c} lists no checks"))
    if inside:
        issues.append(LintIssue(0, "", "unterminated cited region"))
    if regions == 0:
        issues.append(LintIssue(0, "", "no cited regions found"))
    return issues
