"""The skill's most common first-run failure reached the agent as a class name.

``_safe_error`` reduces unrecognised exceptions to ``"<Class>: operation
failed."`` so raw Log Insight response bodies and host:port pairs cannot leak.
Its allowlist was assembled from the exception types the *tool* layer raises —
``LogInsightApiError`` and the validation errors — and stopped there.

``config.get_password`` raises a bare ``OSError`` naming the environment
variable to set, and every tool in this skill reaches it: ``_get_connection`` →
``ConnectionManager.connect`` → ``get_password``. So the first thing a new
operator hits, before a single query runs, was::

    OSError: operation failed.

instead of ``Set environment variable: VMWARE_LOG_INSIGHT_PROD_PASSWORD``.

That is the case where the message *is* the remedy — there is nothing else to
work from, no hint that names the variable, and the variable is per-target so it
cannot be guessed. Nothing caught it because the CLI path prints the exception
in full and the connection tests assert on the raise site, never on what the MCP
wrapper leaves of it.

``RuntimeError`` is not on the list and must not be added. It is the generic
catch-all: allowing it would pass any library's raw text through as though this
package had authored it, which is the leak the wrapper exists to stop.
"""

from __future__ import annotations

import pytest

from vmware_log_insight.connection import LogInsightApiError
from vmware_log_insight.mcp_server._shared import _safe_error

TEACHING = (
    "Target 'prod' not found. Available: lab, staging. Copy an exact name from "
    "that list, or add the target to ~/.vmware-log-insight/config.yaml."
)


def test_missing_password_names_the_variable_to_set():
    """The defect this test exists for: a bare OSError from get_password."""
    out = _safe_error(
        OSError("Password not found. Set environment variable: VMWARE_LOG_INSIGHT_PROD_PASSWORD"),
        "log_search",
    )
    assert "VMWARE_LOG_INSIGHT_PROD_PASSWORD" in out


def test_api_error_keeps_its_message():
    """The connection layer authors these to carry a corrected next step."""
    assert _safe_error(LogInsightApiError(TEACHING), "log_search") == TEACHING


@pytest.mark.parametrize(
    "exc_type",
    [ValueError, KeyError, FileNotFoundError, PermissionError, ConnectionError, OSError],
)
def test_deliberate_errors_pass_through(exc_type):
    assert "prod" in _safe_error(exc_type(TEACHING), "log_search")


def test_unplanned_exceptions_are_still_reduced():
    """The redaction this allowlist exists for has to keep working."""
    out = _safe_error(RuntimeError("https://admin:hunter2@li.internal/api/x"), "log_search")
    assert out == "RuntimeError: operation failed."
    assert "hunter2" not in out


def test_runtime_error_is_not_a_teaching_error():
    """RuntimeError is the generic catch-all — allowlisting it reopens the leak."""
    assert _safe_error(RuntimeError(TEACHING), "log_search") == "RuntimeError: operation failed."


def test_message_is_still_truncated():
    """Length capping is the other half of the guard."""
    assert len(_safe_error(LogInsightApiError("x" * 900), "log_search")) <= 300
