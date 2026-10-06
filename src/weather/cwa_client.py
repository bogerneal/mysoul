"""Bounded HTTP transport. A successful fetch is NOT a verified forecast contract."""

import math
import ssl
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import requests
import truststore

ENDPOINT = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-091"


class CwaError(ValueError):
    """Public code only; never expose a request URL or response body."""


class SystemTrustAdapter(requests.adapters.HTTPAdapter):
    """Use OS trust without globally modifying Python's SSL implementation."""

    def __init__(self):
        self.context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        super().__init__()

    def build_connection_pool_key_attributes(self, request, verify, cert=None):
        host, options = super().build_connection_pool_key_attributes(request, verify, cert)
        if verify is True:
            options["ssl_context"] = self.context
        return host, options


def retry_delay(header: str | None, attempt: int) -> float:
    if header is None:
        return float(2**attempt)
    try:
        delay = float(header)
    except ValueError:
        try:
            delay = (parsedate_to_datetime(header) - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return float(2**attempt)
    if not math.isfinite(delay):
        raise CwaError("retry_after_too_long")
    return max(0, delay)


def fetch_weekly(api_key: str, *, session=None, sleep=time.sleep) -> dict:
    return fetch_dataset(api_key, "F-D0047-091", session=session, sleep=sleep)


def fetch_dataset(api_key: str, dataset: str, *, session=None, sleep=time.sleep) -> dict:
    if dataset not in {"F-D0047-091", "O-A0003-001"}:
        raise CwaError("unsupported_dataset")
    if not api_key.strip():
        raise CwaError("api_key_required")
    owned = session is None
    session = session or requests.Session()
    if owned:
        session.mount("https://", SystemTrustAdapter())
    waited = 0.0
    try:
        for attempt in range(3):
            delay = float(2**attempt)
            try:
                response = session.get(
                    ENDPOINT.rsplit("/", 1)[0] + "/" + dataset,
                    params={"Authorization": api_key, "format": "JSON"},
                    timeout=(5, 20),
                    allow_redirects=False,
                )
            except requests.exceptions.SSLError:
                raise CwaError("tls_verification_failed") from None
            except requests.Timeout:
                code = "timeout"
            except requests.ConnectionError:
                code = "connection_failed"
            except requests.RequestException:
                raise CwaError("request_failed") from None
            else:
                try:
                    status = response.status_code
                    if status in {401, 403}:
                        raise CwaError("authorization_failed")
                    if status == 200:
                        try:
                            document = response.json()
                        except ValueError:
                            raise CwaError("invalid_json") from None
                        if not isinstance(document, dict) or not isinstance(
                            document.get("records"), dict
                        ):
                            raise CwaError("unexpected_response")
                        success = document.get("success")
                        if success is not True and success != "true":
                            raise CwaError("api_rejected")
                        return document
                    if status not in {429, 500, 502, 503, 504}:
                        raise CwaError("http_error")
                    code = "rate_limited" if status == 429 else "server_error"
                    delay = retry_delay(response.headers.get("Retry-After"), attempt)
                finally:
                    response.close()
            if attempt == 2:
                raise CwaError(code) from None
            if waited + delay > 30:
                # Do not retry earlier than the server permits.
                raise CwaError("retry_after_too_long")
            sleep(delay)
            waited += delay
    finally:
        if owned:
            session.close()
    raise CwaError("request_failed")
