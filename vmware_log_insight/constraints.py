"""Build Log Insight query constraints (the path-encoded part of
``GET /api/v2/events/{constraints}`` and ``/aggregated-events/{constraints}``).

Log Insight encodes filters as ``/``-joined ``field/OPERATOR/value`` segments.
Time windows use the ``LAST`` operator (milliseconds) or numeric comparisons on
``timestamp`` (epoch ms). These are pure functions so they unit-test without a
live appliance.

NOTE: the exact wire grammar can only be confirmed against a real instance's
``/rest-api`` reference (tracked in BACKLOG, same status as VKS /wcp/login).
The encoding here follows the published v1/v2 docs; if a future real-hardware
test shows a different separator, only this module changes.
"""

from __future__ import annotations

from urllib.parse import quote

# Operators accepted in field constraints (mirrors tests/eval/spec/api_index.py).
VALID_OPERATORS = frozenset({"CONTAINS", "=", "!=", "<", ">", "EXISTS", "LAST"})

# Duration suffix -> seconds, for human windows like "30m", "24h", "7d".
_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_duration_ms(value: str | int) -> int:
    """Parse a duration into milliseconds.

    Accepts an int (seconds), a bare numeric string (seconds), or a shorthand
    string with a unit suffix: ``s`` ``m`` ``h`` ``d`` (e.g. "30m", "24h", "7d").
    Raises ValueError on anything else (踩坑 #23: accept human shorthand at the
    boundary, fail loudly otherwise).
    """
    if isinstance(value, bool):
        raise ValueError(f"invalid duration: {value!r}")
    if isinstance(value, int):
        if value <= 0:
            raise ValueError(f"duration must be positive: {value!r}")
        return value * 1000
    text = str(value).strip().lower()
    if not text:
        raise ValueError("empty duration")
    if text[-1] in _DURATION_UNITS:
        try:
            qty = float(text[:-1])
        except ValueError as exc:
            raise ValueError(f"invalid duration: {value!r}") from exc
        seconds = qty * _DURATION_UNITS[text[-1]]
    else:
        try:
            seconds = float(text)
        except ValueError as exc:
            raise ValueError(f"invalid duration: {value!r}") from exc
    if seconds <= 0:
        raise ValueError(f"duration must be positive: {value!r}")
    return int(seconds * 1000)


def _segment(field: str, operator: str, value: str) -> str:
    """Encode one ``field/OPERATOR/value`` constraint, URL-escaping the value."""
    if operator not in VALID_OPERATORS:
        raise ValueError(
            f"unknown operator {operator!r}; valid: {sorted(VALID_OPERATORS)}"
        )
    if not field:
        raise ValueError("constraint field must not be empty")
    # safe="" so '/', spaces, and special chars in the value are escaped and
    # don't break the path grammar.
    return f"{quote(field, safe='')}/{operator}/{quote(value, safe='')}"


def build_constraints(
    *,
    text: str | None = None,
    last: str | int | None = None,
    begin_ms: int | None = None,
    end_ms: int | None = None,
    filters: list[tuple[str, str, str]] | None = None,
) -> str:
    """Build the constraints path segment for an events/aggregated-events query.

    Args:
        text: Free-text search; becomes ``text/CONTAINS/<text>``.
        last: Relative time window (e.g. "1h", "30m", int seconds); becomes
            ``timestamp/LAST/<ms>``. Mutually exclusive with begin_ms/end_ms.
        begin_ms / end_ms: Absolute epoch-ms window; become
            ``timestamp/>/<begin>`` and ``timestamp/</<end>``.
        filters: Extra ``(field, operator, value)`` constraints.

    Returns:
        The ``/``-joined constraints string. Defaults to the last hour when no
        time window is supplied, so a query is never unbounded.
    """
    segments: list[str] = []

    if last is not None and (begin_ms is not None or end_ms is not None):
        raise ValueError("pass either `last` or begin_ms/end_ms, not both")

    if last is not None:
        segments.append(f"timestamp/LAST/{parse_duration_ms(last)}")
    elif begin_ms is not None or end_ms is not None:
        if begin_ms is not None:
            segments.append(f"timestamp/>/{int(begin_ms)}")
        if end_ms is not None:
            segments.append(f"timestamp/</{int(end_ms)}")
    else:
        # Never issue an unbounded query — default to the last hour.
        segments.append(f"timestamp/LAST/{parse_duration_ms('1h')}")

    if text:
        segments.append(_segment("text", "CONTAINS", text))

    for field, operator, value in filters or []:
        segments.append(_segment(field, operator, value))

    return "/".join(segments)
