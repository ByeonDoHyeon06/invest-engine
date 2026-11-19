"""Offline market-panel acquisition and coverage audit (no broker orders).

Public probe produces aggregate diagnostics only. Authorized providers store
private research data under datasets/; no key, response body or OHLCV in logs.
Historical data is NOT evidence of original receipt time or execution.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "research/market_panel_v1.json"
D = Decimal
US_TZ = ZoneInfo("America/New_York")
YEARS = tuple(range(2020, 2026))
FIELDS = ("date", "open", "high", "low", "close", "volume")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(url, headers=None, attempts=4, limit=30_000_000):
    for i in range(attempts):
        try:
            with build_opener(NoRedirect()).open(Request(url, headers={"User-Agent": "invest-engine-research/1.0",
                                               **(headers or {})}), timeout=60) as response:
                raw = response.read(limit+1)
                if len(raw) > limit:
                    raise ValueError("RESPONSE_SIZE_LIMIT")
                return raw
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or i == attempts-1:
                # HTTP error reasons, URLs and bodies can contain sensitive content.
                raise RuntimeError(f"HTTP_{exc.code}") from None
        except (URLError, TimeoutError):
            if i == attempts-1:
                raise RuntimeError("NETWORK_UNAVAILABLE") from None
        time.sleep(2**i)
    raise RuntimeError("REQUEST_FAILED")


def load_plan():
    raw = PLAN_FILE.read_bytes()
    plan = json.loads(raw)
    rows = plan["instruments"]
    if len(rows) != 80 or len({(x["market"], x["symbol"]) for x in rows}) != 80:
        raise ValueError("PLAN_UNIVERSE_MISMATCH")
    return plan, digest(raw)


def session_dates(market, year):
    # Pinned library is a provisional calendar, not exchange certification.
    import exchange_calendars as xcals

    cal = xcals.get_calendar("XNYS" if market == "US" else "XKRX",
                            start=f"{year}-01-01", end=f"{year}-12-31")
    return {x.date().isoformat() for x in cal.sessions}


def parse_price(value):
    v = D(str(value).replace(",", ""))
    if not v.is_finite() or v <= 0:
        raise ValueError("INVALID_PRICE")
    return v


def normalize(day, o, h, low, c, v):
    day = date.fromisoformat(day).isoformat()
    op, hi, lo, cl = map(parse_price, (o, h, low, c))
    vol = D(str(v).replace(",", ""))
    if not vol.is_finite() or vol < 0 or vol != vol.to_integral_value():
        raise ValueError("INVALID_VOLUME")
    if not lo <= min(op, cl) <= max(op, cl) <= hi:
        raise ValueError("INVALID_OHLC")
    return (day, *(format(x, "f") for x in (op, hi, lo, cl, vol)))


def parse_public(raw, year):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if not reader.fieldnames or not set(FIELDS) <= set(reader.fieldnames):
        raise ValueError("PUBLIC_SCHEMA_MISMATCH")
    rows, invalid = [], 0
    for row in reader:
        try:
            item = normalize(*(row[k] for k in FIELDS))
            if not item[0].startswith(str(year)+"-"):
                raise ValueError("OUTSIDE_REQUEST_YEAR")
            rows.append(item)
        except (ValueError, InvalidOperation, KeyError, TypeError):
            invalid += 1
    return rows, invalid


def coverage(rows, expected, invalid=0):
    seen = {x[0] for x in rows}
    duplicate = len(rows)-len(seen)
    missing = sorted(expected-seen)
    extra = sorted(seen-expected)
    zero = sum(D(x[-1]) == 0 for x in rows)
    return {"expected_sessions": len(expected), "observed_rows": len(rows),
            "distinct_sessions": len(seen), "missing_sessions": len(missing),
            "missing_dates": missing, "extra_sessions": len(extra), "extra_dates": extra,
            "duplicates": duplicate, "invalid_rows": invalid, "zero_volume_rows": zero,
            "status": "STRUCTURAL_COMPLETE" if not (missing or extra or duplicate or invalid or zero)
            else "BLOCKED_COVERAGE"}


def audit_row(symbol, market, year, rows, hashes, invalid, provider):
    return {"symbol": symbol, "market": market, "year": year, "provider": provider,
            "source_sha256": hashes, **coverage(rows, session_dates(market, year), invalid),
            "identity_verified": False, "corporate_actions_verified": False,
            "receipt_provenance_verified": False, "execution_eligible": False}


def write_private(base, market, symbol, year, rows):
    dest = base / "daily" / market / symbol / f"{year}.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(FIELDS)
        writer.writerows(sorted(rows))
    # Never silently overwrite a prior collection (versioning is explicit).
    if dest.exists():
        if dest.read_bytes() != tmp.read_bytes():
            tmp.unlink()
            raise ValueError("PRIVATE_DATASET_CHANGED_USE_NEW_VERSION")
        tmp.unlink()
    else:
        tmp.replace(dest)
    return digest(dest.read_bytes())


def public_probe(plan):
    ref = plan["providers"]["public_probe"]["commit"]
    output = []
    for inst in plan["instruments"]:
        if not inst["public_probe"]:
            continue
        symbol = inst["symbol"]
        for year in YEARS:
            try:
                raw = request(f"https://raw.githubusercontent.com/Pubmarks/datasets/{ref}/"
                              f"data/stocks/{symbol}/{year}/ohlcv.csv", limit=2_000_000)
                rows, invalid = parse_public(raw, year)
                output.append(audit_row(symbol, "US", year, rows, [digest(raw)], invalid, "pubmarks"))
            except (ValueError, RuntimeError, UnicodeError, InvalidOperation) as exc:
                output.append({"symbol": symbol, "market": "US", "year": year,
                               "provider": "pubmarks", "status": "SOURCE_ERROR",
                               "error_type": type(exc).__name__, "execution_eligible": False})
    return output


def alpaca_daily(symbol, year, key, secret):
    # Explicit raw SIP. No fallback to IEX; symbol mapping disabled to expose
    # rename/delisting gaps. A security master must reconcile identities later.
    start = f"{year}-01-01T00:00:00-05:00"
    end = f"{year+1}-01-01T00:00:00-05:00"
    params = {"symbols": symbol, "timeframe": "1Day", "start": start, "end": end,
              "adjustment": "raw", "feed": "sip", "asof": "-", "limit": 10000, "sort": "asc"}
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    rows, hashes, invalid, tokens = [], [], 0, set()
    while True:
        raw = request("https://data.alpaca.markets/v2/stocks/bars?"+urlencode(params), headers)
        hashes.append(digest(raw))
        data = json.loads(raw, parse_float=D)
        bars = data["bars"]
        if not isinstance(bars, dict) or set(bars)-{symbol}:
            raise ValueError("ALPACA_SCHEMA_MISMATCH")
        for bar in bars.get(symbol, []):
            try:
                stamp = datetime.fromisoformat(bar["t"])
                if stamp.tzinfo is None:
                    raise ValueError("NAIVE_TIMESTAMP")
                day = stamp.astimezone(US_TZ).date()
                # API end is inclusive; explicitly drop the next year's boundary.
                if day == date(year+1, 1, 1):
                    continue
                if day.year != year:
                    raise ValueError("OUTSIDE_REQUEST_YEAR")
                rows.append(normalize(day.isoformat(), *(bar[k] for k in ("o","h","l","c","v"))))
            except (ValueError, InvalidOperation, TypeError, KeyError):
                invalid += 1
        token = data.get("next_page_token")
        if not token:
            return rows, hashes, invalid
        if token in tokens or len(tokens) >= 1000:
            raise ValueError("PAGINATION_LOOP_OR_LIMIT")
        tokens.add(token)
        params["page_token"] = token
        time.sleep(.65)


def collect_us(plan, base, key, secret, years=YEARS):
    result = []
    for inst in plan["instruments"]:
        if inst["market"] != "US":
            continue
        symbol = inst["symbol"]
        for year in years:
            try:
                rows, hashes, invalid = alpaca_daily(symbol, year, key, secret)
                report = audit_row(symbol, "US", year, rows, hashes, invalid, "alpaca-sip-raw")
                report["normalized_sha256"] = write_private(base, "US", symbol, year, rows)
                result.append(report)
            except (ValueError, RuntimeError, KeyError, TypeError, InvalidOperation) as exc:
                result.append({"symbol": symbol, "market": "US", "year": year,
                               "status": "SOURCE_ERROR", "error_type": type(exc).__name__,
                               "execution_eligible": False})
            time.sleep(.65)
    return result


def collect_us_minute(plan, base, key, secret, years=YEARS):
    """Requested monthly SIP minute partitions, regular-session bars only.

    Missing regular minutes remain unknown (including potential no-trade
    intervals). Extended hours are not used to fill the grid. No synthetic bar.
    """
    import exchange_calendars as xcals

    utc = ZoneInfo("UTC")
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    results = []
    for instrument in plan["instruments"]:
        if instrument["market"] != "US":
            continue
        symbol = instrument["symbol"]
        for year in years:
            cal = xcals.get_calendar("XNYS", start=f"{year}-01-01", end=f"{year}-12-31")
            for month in range(1, 13):
                sessions = [x for x in cal.sessions if x.month == month]
                expected = set()
                for session in sessions:
                    start = cal.session_open(session).to_pydatetime().astimezone(utc)
                    end = cal.session_close(session).to_pydatetime().astimezone(utc)
                    while start < end:
                        expected.add(start.isoformat())
                        start += timedelta(minutes=1)
                first = date(year, month, 1)
                last = date(year+1, 1, 1) if month == 12 else date(year, month+1, 1)
                params = {"symbols": symbol, "timeframe": "1Min",
                          "start": datetime.combine(first, datetime.min.time(), US_TZ).isoformat(),
                          "end": datetime.combine(last, datetime.min.time(), US_TZ).isoformat(),
                          "adjustment": "raw", "feed": "sip", "asof": "-", "limit": 10000, "sort": "asc"}
                rows, hashes, seen_tokens = [], [], set()
                invalid = 0
                report = {"symbol": symbol, "market": "US", "year": year, "month": month,
                          "provider": "alpaca-sip-raw-minute", "expected_minutes": len(expected),
                          "execution_eligible": False}
                try:
                    while True:
                        raw = request("https://data.alpaca.markets/v2/stocks/bars?"+urlencode(params), headers)
                        hashes.append(digest(raw))
                        data = json.loads(raw, parse_float=D)
                        bars = data["bars"]
                        if not isinstance(bars, dict) or set(bars)-{symbol}:
                            raise ValueError("ALPACA_SCHEMA_MISMATCH")
                        for bar in bars.get(symbol, []):
                            try:
                                stamp = datetime.fromisoformat(bar["t"])
                                if stamp.tzinfo is None or stamp.second or stamp.microsecond:
                                    raise ValueError("INVALID_BAR_TIME")
                                stamp = stamp.astimezone(utc)
                                at = stamp.isoformat()
                                if at not in expected:
                                    continue  # outside preregistered regular session grid
                                row = normalize(stamp.astimezone(US_TZ).date().isoformat(),
                                                *(bar[k] for k in ("o","h","l","c","v")))
                                rows.append((at, *row[1:]))
                            except (ValueError, InvalidOperation, KeyError, TypeError):
                                invalid += 1
                        token = data.get("next_page_token")
                        if not token:
                            break
                        if token in seen_tokens or len(seen_tokens) >= 100:
                            raise ValueError("PAGINATION_LOOP_OR_LIMIT")
                        seen_tokens.add(token)
                        params["page_token"] = token
                        time.sleep(.65)
                    seen = {x[0] for x in rows}
                    missing = expected-seen
                    duplicates = len(rows)-len(seen)
                    zero = sum(D(x[-1]) == 0 for x in rows)
                    report.update({"observed_rows": len(rows), "missing_minutes": len(missing),
                                   "duplicates": duplicates, "invalid_rows": invalid,
                                   "zero_volume_rows": zero, "source_sha256": hashes,
                                   "status": "STRUCTURAL_COMPLETE" if not (
                                       missing or duplicates or invalid or zero) else "BLOCKED_COVERAGE"})
                    path = base / "minute" / "US" / symbol / f"{year}-{month:02d}.csv"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    content = io.StringIO()
                    writer = csv.writer(content)
                    writer.writerow(("start_utc", *FIELDS[1:]))
                    writer.writerows(sorted(rows))
                    normalized = content.getvalue().encode("utf-8")
                    if path.exists() and path.read_bytes() != normalized:
                        raise ValueError("PRIVATE_DATASET_CHANGED_USE_NEW_VERSION")
                    if not path.exists():
                        temp = path.with_suffix(".csv.tmp")
                        temp.write_bytes(normalized)
                        temp.replace(path)
                    report["normalized_sha256"] = digest(normalized)
                except (ValueError, RuntimeError, KeyError, TypeError, InvalidOperation) as exc:
                    report.update({"status": "SOURCE_ERROR", "error_type": type(exc).__name__})
                results.append(report)
                # Log only counts; never market observations or credentials.
                print("MINUTE_PARTITION "+json.dumps({k: report.get(k) for k in (
                    "symbol","year","month","status","expected_minutes","observed_rows",
                    "missing_minutes","duplicates","invalid_rows")}), flush=True)
                time.sleep(.65)
    return results


def krx_day(board, day, key):
    endpoint = {"KOSPI": "stk_bydd_trd", "KOSDAQ": "ksq_bydd_trd"}[board]
    raw = request("https://data-dbg.krx.co.kr/svc/apis/sto/"+endpoint+"?"+
                  urlencode({"basDd": day.replace("-", "")}), {"AUTH_KEY": key})
    data = json.loads(raw, parse_float=D)
    rows = data["OutBlock_1"]
    if not isinstance(rows, list):
        raise ValueError("KRX_SCHEMA_MISMATCH")
    return rows, digest(raw)


def collect_kr(plan, base, key):
    result = []
    for year in YEARS:
        dates = session_dates("KR", year)
        for board in ("KOSPI", "KOSDAQ"):
            symbols = {x["symbol"] for x in plan["instruments"] if x["board"] == board}
            by_symbol = {s: [] for s in symbols}
            invalid = dict.fromkeys(symbols, 0)
            hashes = []
            failed_days = []
            for day in sorted(dates):
                try:
                    raw_rows, raw_hash = krx_day(board, day, key)
                    hashes.append(raw_hash)
                    for row in raw_rows:
                        symbol = str(row.get("ISU_CD", "")).strip()
                        if symbol not in symbols:
                            continue
                        try:
                            raw_date = str(row["BAS_DD"]).replace("-", "")
                            if raw_date != day.replace("-", ""):
                                raise ValueError("KRX_DATE_MISMATCH")
                            by_symbol[symbol].append(normalize(day, *(row[k] for k in
                                ("TDD_OPNPRC","TDD_HGPRC","TDD_LWPRC","TDD_CLSPRC","ACC_TRDVOL"))))
                        except (ValueError, TypeError, KeyError, InvalidOperation):
                            invalid[symbol] += 1
                except (ValueError, RuntimeError, KeyError, TypeError):
                    failed_days.append(day)
                time.sleep(.65)
            for symbol in sorted(symbols):
                report = audit_row(symbol, "KR", year, by_symbol[symbol], hashes,
                                   invalid[symbol], "krx-raw-daily")
                report["source_error_days"] = failed_days
                if failed_days:
                    report["status"] = "SOURCE_ERROR"
                report["normalized_sha256"] = write_private(base, "KR", symbol, year, by_symbol[symbol])
                result.append(report)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("public-probe", "alpaca-daily", "alpaca-minute", "krx-daily"))
    parser.add_argument("--acknowledge-data-rights", action="store_true")
    parser.add_argument("--version", default="v1")
    parser.add_argument("--year", type=int, choices=YEARS, help="authorized US acquisition shard")
    args = parser.parse_args()
    if not args.version.isascii() or not args.version.isalnum() or len(args.version) > 32:
        parser.error("--version must be alphanumeric")
    if args.year is not None and args.mode not in ("alpaca-daily", "alpaca-minute"):
        parser.error("--year only applies to US acquisition")
    years = YEARS if args.year is None else (args.year,)
    plan, plan_hash = load_plan()
    if args.mode == "public-probe":
        rows = public_probe(plan)
        base = Path("research-output")
    else:
        if not args.acknowledge_data_rights:
            parser.error("authorized data access and permitted research use required")
        base = ROOT / "datasets" / (plan["dataset_id"]+"-"+args.version)
        if args.mode in ("alpaca-daily", "alpaca-minute"):
            key, secret = os.environ.get("ALPACA_DATA_KEY"), os.environ.get("ALPACA_DATA_SECRET")
            if not key or not secret:
                parser.error("local market-data credentials required")
            rows = (collect_us(plan, base, key, secret, years) if args.mode == "alpaca-daily"
                    else collect_us_minute(plan, base, key, secret, years))
        else:
            key = os.environ.get("KRX_DATA_KEY")
            if not key:
                parser.error("local approved KRX data key required")
            rows = collect_kr(plan, base, key)
    base.mkdir(parents=True, exist_ok=True)
    result = {"plan_sha256": plan_hash, "mode": args.mode,
              "retrieved_at": datetime.now(ZoneInfo("UTC")).isoformat(),
              "requested_years": years,
              "data_rights_verified": False, "production_authorized": False, "rows": rows}
    suffix = "" if args.year is None else f"-{args.year}"
    path = base / f"{args.mode}{suffix}-audit.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    for row in rows:
        print("PANEL_AUDIT "+json.dumps({k: row.get(k) for k in (
            "symbol","market","year","month","status","expected_sessions","observed_rows","missing_sessions",
            "extra_sessions","expected_minutes","missing_minutes","duplicates","invalid_rows",
            "zero_volume_rows","error_type")}), flush=True)
    counts = {status: sum(r["status"] == status for r in rows) for status in
              ("STRUCTURAL_COMPLETE", "BLOCKED_COVERAGE", "SOURCE_ERROR")}
    print("PANEL_SUMMARY "+json.dumps({"mode": args.mode, "planned_partitions": len(rows),
                                      "counts": counts, "execution_eligible": 0}), flush=True)
    if counts["SOURCE_ERROR"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
