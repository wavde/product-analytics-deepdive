"""Data-diff two query results: the mechanical half of the reconcile-results skill."""

from __future__ import annotations

from dataclasses import dataclass, field

from analyst_eval.sqlexec import QueryResult, to_number


@dataclass
class DiffReport:
    match: bool
    summary: str
    details: dict = field(default_factory=dict)


def _is_numeric_col(rows: list[tuple], i: int) -> bool:
    vals = [r[i] for r in rows if r[i] is not None]
    return bool(vals) and all(to_number(v) is not None and not isinstance(v, str) for v in vals)


def diff_results(left: QueryResult, right: QueryResult, tolerance: float = 1e-9) -> DiffReport:
    """Compare two results. Non-numeric columns are join keys; numeric columns are compared
    within ``tolerance`` (absolute). Columns are aligned by position, not name, because two
    independent queries rarely agree on aliases."""
    if not left.ok or not right.ok:
        side = "primary" if not left.ok else "independent"
        return DiffReport(False, f"Cannot diff: the {side} query failed.",
                          {"left_error": left.error, "right_error": right.error})
    if len(left.columns) != len(right.columns):
        return DiffReport(
            False,
            f"Column count differs: {len(left.columns)} vs {len(right.columns)}.",
            {"left_columns": left.columns, "right_columns": right.columns},
        )
    ncol = len(left.columns)
    both = left.rows + right.rows
    numeric = [i for i in range(ncol) if both and _is_numeric_col(both, i)]
    keys = [i for i in range(ncol) if i not in numeric]

    def keyed(rows: list[tuple]) -> dict[tuple, list[tuple]]:
        out: dict[tuple, list[tuple]] = {}
        for r in rows:
            out.setdefault(tuple(str(r[i]) for i in keys), []).append(r)
        return out

    lk, rk = keyed(left.rows), keyed(right.rows)
    only_left = sorted(set(lk) - set(rk))
    only_right = sorted(set(rk) - set(lk))
    mismatches = []
    max_abs = 0.0
    for k in sorted(set(lk) & set(rk)):
        lrows, rrows = lk[k], rk[k]
        if len(lrows) != len(rrows):
            mismatches.append({"key": k, "issue": f"{len(lrows)} vs {len(rrows)} rows"})
            continue
        for lr, rr in zip(sorted(lrows, key=str), sorted(rrows, key=str), strict=True):
            for i in numeric:
                a, b = to_number(lr[i]), to_number(rr[i])
                if a is None or b is None:
                    if (a is None) != (b is None):
                        mismatches.append({"key": k, "column": i, "left": a, "right": b})
                    continue
                d = abs(a - b)
                max_abs = max(max_abs, d)
                if d > tolerance:
                    mismatches.append({"key": k, "column": i, "left": a, "right": b,
                                       "abs_diff": d})

    match = not only_left and not only_right and not mismatches
    parts = [
        f"rows: {len(left.rows)} vs {len(right.rows)}",
        f"keys only in primary: {len(only_left)}",
        f"keys only in independent: {len(only_right)}",
        f"numeric mismatches beyond {tolerance:g}: {len(mismatches)}",
        f"max abs diff: {max_abs:g}",
    ]
    for m in mismatches[:5]:
        parts.append(f"  e.g. {m}")
    verdict = "MATCH" if match else "MISMATCH"
    return DiffReport(
        match,
        f"{verdict} ({'; '.join(parts[:5])})" + ("\n" + "\n".join(parts[5:]) if parts[5:] else ""),
        {"only_left": len(only_left), "only_right": len(only_right),
         "mismatches": len(mismatches), "max_abs_diff": round(max_abs, 6)},
    )
