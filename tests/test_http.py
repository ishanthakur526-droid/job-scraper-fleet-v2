import pytest

from jobfleet import http as http_module
from jobfleet.http import FetchError, HttpClient, HttpResponse, OfflineHttpClient, redact


class Scripted(HttpClient):
    def __init__(self, script, **kw):
        super().__init__(min_interval=0, **kw)
        self.script = list(script)
        self.sent = 0

    def _send(self, *args, **kwargs):
        self.sent += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    sleeps = []
    monkeypatch.setattr(http_module.time, "sleep", lambda s: sleeps.append(s))
    return sleeps


def ok(text='{"a": 1}'):
    return HttpResponse(200, "https://x", text, {})


def test_404_is_not_retried_and_is_hard():
    client = Scripted([HttpResponse(404, "https://x", "", {})])
    with pytest.raises(FetchError) as info:
        client.get_json("https://x")
    assert client.sent == 1 and info.value.hard and info.value.status == 404


def test_503_and_connection_reset_are_retried():
    client = Scripted([HttpResponse(503, "https://x", "", {}), FetchError("reset", retryable=True), ok()])
    assert client.get_json("https://x") == {"a": 1}
    assert client.sent == 3


def test_retry_after_is_honoured(no_sleep):
    client = Scripted([HttpResponse(429, "https://x", "", {"retry-after": "7"}), ok()])
    client.get_json("https://x")
    assert 7.0 in no_sleep


def test_raise_for_status_false_returns_response():
    client = Scripted([HttpResponse(404, "https://x", "nope", {})])
    assert client.request("GET", "https://x", raise_for_status=False).status == 404


def test_invalid_json_is_a_fetch_error():
    client = Scripted([ok("<html>")])
    with pytest.raises(FetchError):
        client.get_json("https://x")


def test_secrets_are_redacted():
    message = str(FetchError("Unable to fetch https://serpapi.com/search.json?q=x&api_key=SECRET123&num=5"))
    assert "SECRET123" not in message and "api_key=REDACTED" in message
    assert redact("https://a.com/?token=abc") == "https://a.com/?token=REDACTED"


def test_offline_client_refuses_network():
    with pytest.raises(FetchError):
        OfflineHttpClient().get_json("https://example.com")
