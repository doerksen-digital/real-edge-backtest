"""Download retries: a dropped connection is retried, not fatal."""

import http.client

from real_edge_backtest.data import download


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b"payload"


def test_dropped_connection_is_retried(monkeypatch):
    calls = []

    def urlopen(request, timeout):
        calls.append(request.full_url)
        if len(calls) < 3:
            raise http.client.RemoteDisconnected("Remote end closed connection without response")
        return _Response()

    monkeypatch.setattr(download.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(download.time, "sleep", lambda seconds: None)
    assert download._get("https://data.binance.vision/x") == b"payload"
    assert len(calls) == 3
