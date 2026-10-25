"""Download and verify spot klines from the Binance public data archive.

The URL layout and the "skip files that already exist" approach follow the official downloader
in binance/binance-public-data (python/utility.py and python/download-kline.py, MIT license,
Copyright (c) Binance). This module adds SHA-256 verification against each .CHECKSUM file,
retries with backoff, and a refresh mode for archive files that Binance replaced.

Every zip is checked on every run. A zip whose hash does not match is deleted and reported,
never parsed.
"""

import hashlib
import http.client
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from real_edge_backtest.data.intervals import interval_seconds
from real_edge_backtest.data.paths import BASE_URL, archive_dir, file_name, raw_dir

PAUSE_SECONDS = 0.5
MAX_RETRIES = 5
BACKOFF_START_SECONDS = 2.0
TIMEOUT_SECONDS = 60
USER_AGENT = "real-edge-backtest (+https://github.com/doerksen-digital/real-edge-backtest)"


class ArchiveError(RuntimeError):
    """The archive kept failing after all retries."""


@dataclass
class DownloadResult:
    downloaded: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)
    verified_local: list[str] = field(default_factory=list)
    corrupt_local: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    not_available: list[str] = field(default_factory=list)


def _get(url: str) -> bytes | None:
    """GET a URL. Returns None on 404. Retries 429, 5xx and network errors (including dropped
    connections) with backoff."""
    delay = BACKOFF_START_SECONDS
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        time.sleep(PAUSE_SECONDS)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            if error.code != 429 and error.code < 500:
                raise ArchiveError(f"HTTP {error.code} for {url}") from error
            last_error = error
            wait = _retry_after(error) or delay
        except (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            http.client.HTTPException,
        ) as error:
            last_error = error
            wait = delay
        if attempt < MAX_RETRIES:
            time.sleep(wait)
            delay *= 2
    raise ArchiveError(f"giving up on {url} after {MAX_RETRIES} retries") from last_error


def _retry_after(error: urllib.error.HTTPError) -> float | None:
    value = error.headers.get("Retry-After") if error.headers else None
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _url(period: str, symbol: str, interval: str, name: str) -> str:
    return BASE_URL + quote(archive_dir(period, symbol, interval) + name, safe="/")


def _parse_checksum(text: bytes, name: str) -> str:
    """Return the SHA-256 hex digest from a .CHECKSUM file ("<sha256>  <file name>")."""
    parts = text.decode("ascii").split()
    if len(parts) != 2 or parts[1] != name or len(parts[0]) != 64:
        raise ArchiveError(f"unexpected CHECKSUM content for {name}: {text[:200]!r}")
    return parts[0].lower()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_local(zip_path: Path) -> bool:
    """True if the zip exists and matches the SHA-256 in its stored .CHECKSUM file."""
    checksum_path = zip_path.with_name(zip_path.name + ".CHECKSUM")
    if not zip_path.exists() or not checksum_path.exists():
        return False
    expected = _parse_checksum(checksum_path.read_bytes(), zip_path.name)
    return _sha256(zip_path) == expected


def _delete(zip_path: Path) -> None:
    zip_path.unlink(missing_ok=True)
    zip_path.with_name(zip_path.name + ".CHECKSUM").unlink(missing_ok=True)


def _fetch_file(
    period: str,
    symbol: str,
    interval: str,
    label: str,
    target_dir: Path,
    refresh: bool,
    result: DownloadResult,
) -> bool:
    """Make sure one verified zip is present locally. Returns False if it is not in the archive."""
    name = file_name(symbol, interval, label)
    zip_path = target_dir / name
    checksum_path = target_dir / (name + ".CHECKSUM")

    replaced = False
    if zip_path.exists() or checksum_path.exists():
        if verify_local(zip_path):
            if not refresh:
                result.verified_local.append(name)
                return True
            remote = _get(_url(period, symbol, interval, name + ".CHECKSUM"))
            if remote is not None and _parse_checksum(remote, name) == _parse_checksum(
                checksum_path.read_bytes(), name
            ):
                result.verified_local.append(name)
                return True
            replaced = True
        else:
            result.corrupt_local.append(f"{name}: local file failed SHA-256 check, deleted")
        _delete(zip_path)

    checksum_bytes = _get(_url(period, symbol, interval, name + ".CHECKSUM"))
    if checksum_bytes is None:
        return False
    expected = _parse_checksum(checksum_bytes, name)
    zip_bytes = _get(_url(period, symbol, interval, name))
    if zip_bytes is None:
        result.failed.append(f"{name}: CHECKSUM exists but zip is missing")
        return True
    actual = hashlib.sha256(zip_bytes).hexdigest()
    if actual != expected:
        result.failed.append(f"{name}: SHA-256 mismatch (expected {expected}, got {actual})")
        return True

    target_dir.mkdir(parents=True, exist_ok=True)
    part = zip_path.with_name(name + ".part")
    part.write_bytes(zip_bytes)
    part.replace(zip_path)
    checksum_path.write_bytes(checksum_bytes)
    (result.replaced if replaced else result.downloaded).append(name)
    return True


def _months(start: date, end: date) -> list[date]:
    months = []
    current = start.replace(day=1)
    while current <= end:
        months.append(current)
        current = (current + timedelta(days=32)).replace(day=1)
    return months


def download_klines(
    data_dir: Path,
    symbol: str,
    interval: str,
    start: date,
    refresh: bool = False,
    today: date | None = None,
) -> DownloadResult:
    """Download all monthly files from start up to last month, daily files where needed.

    A month uses its monthly file if the archive has one. Otherwise, for the current month and
    the month before (monthly files appear on the first Monday of the next month), daily files
    up to yesterday UTC are used. Older months without a monthly file are reported as not
    available, without probing every day.
    """
    symbol = symbol.upper()
    interval_seconds(interval)
    today = today or datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)
    current_month = today.replace(day=1)
    previous_month = (current_month - timedelta(days=1)).replace(day=1)

    monthly_dir = raw_dir(data_dir, "monthly", symbol, interval)
    daily_dir = raw_dir(data_dir, "daily", symbol, interval)
    result = DownloadResult()

    for month in _months(start, yesterday):
        label = month.strftime("%Y-%m")
        if month < current_month and _fetch_file(
            "monthly", symbol, interval, label, monthly_dir, refresh, result
        ):
            continue
        if month < previous_month:
            result.not_available.append(f"{symbol}-{interval}-{label} (monthly)")
            continue
        day = month
        while day <= yesterday and day.month == month.month:
            day_label = day.strftime("%Y-%m-%d")
            if not _fetch_file("daily", symbol, interval, day_label, daily_dir, refresh, result):
                result.not_available.append(f"{symbol}-{interval}-{day_label} (daily)")
            day += timedelta(days=1)
    return result
