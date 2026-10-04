import ssl
from unittest.mock import Mock

import pytest
import requests

from weather.cwa_client import CwaError, SystemTrustAdapter, fetch_weekly


def test_system_trust_retains_certificate_and_hostname_verification():
    adapter = SystemTrustAdapter()
    request = requests.Request("GET", "https://opendata.cwa.gov.tw/").prepare()
    _, options = adapter.build_connection_pool_key_attributes(request, True)
    context = options["ssl_context"]
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    adapter.close()


def test_tls_failure_is_classified_without_retry():
    session = Mock()
    session.get.side_effect = requests.exceptions.SSLError("secret")
    with pytest.raises(CwaError, match="^tls_verification_failed$"):
        fetch_weekly("secret", session=session)
    assert session.get.call_count == 1


def response(status=200, body=None, headers=None):
    result = Mock(status_code=status, headers=headers or {})
    result.json.return_value = body if body is not None else {"success": "true", "records": {}}
    return result


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "authorization_failed"),
        (403, "authorization_failed"),
        (302, "http_error"),
        (404, "http_error"),
    ],
)
def test_permanent_failures_do_not_retry_or_leak_key(status, code):
    session = Mock()
    session.get.return_value = response(status)
    with pytest.raises(CwaError, match=f"^{code}$"):
        fetch_weekly("secret", session=session)
    assert session.get.call_count == 1
    assert session.get.call_args.kwargs["timeout"] == (5, 20)
    assert session.get.call_args.kwargs["allow_redirects"] is False


def test_transient_failure_then_success():
    session, sleep = Mock(), Mock()
    session.get.side_effect = [response(429, headers={"Retry-After": "3"}), response()]
    assert fetch_weekly("secret", session=session, sleep=sleep)["success"] == "true"
    sleep.assert_called_once_with(3)


@pytest.mark.parametrize(
    "exc,code", [(requests.Timeout, "timeout"), (requests.ConnectionError, "connection_failed")]
)
def test_network_retries_bounded_and_errors_redacted(exc, code):
    session, sleep = Mock(), Mock()
    session.get.side_effect = exc("https://example.invalid/?Authorization=secret")
    with pytest.raises(CwaError, match=f"^{code}$"):
        fetch_weekly("secret", session=session, sleep=sleep)
    assert session.get.call_count == 3
    assert sleep.call_count == 2


def test_long_retry_after_is_not_ignored():
    session, sleep = Mock(), Mock()
    session.get.return_value = response(429, headers={"Retry-After": "300"})
    with pytest.raises(CwaError, match="retry_after_too_long"):
        fetch_weekly("secret", session=session, sleep=sleep)
    sleep.assert_not_called()
    assert session.get.call_count == 1


def test_bad_json_not_retried():
    session = Mock()
    session.get.return_value = response()
    session.get.return_value.json.side_effect = ValueError("secret")
    with pytest.raises(CwaError, match="^invalid_json$"):
        fetch_weekly("secret", session=session)
    assert session.get.call_count == 1


def test_missing_key_does_not_connect():
    session = Mock()
    with pytest.raises(CwaError, match="api_key_required"):
        fetch_weekly(" ", session=session)
    session.get.assert_not_called()


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"success": "false", "records": {}},
        {"success": "true"},
        {"success": [], "records": {}},
        {"success": 1, "records": {}},
    ],
)
def test_unexpected_api_envelope(body):
    session = Mock()
    session.get.return_value = response(body=body)
    with pytest.raises(CwaError):
        fetch_weekly("secret", session=session)
