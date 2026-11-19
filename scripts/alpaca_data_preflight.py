"""Credential-safe, market-data-only access smoke check."""
import json
import os
import sys
from urllib.parse import urlencode

from prepare_market_panel import D, normalize, request


def main():
    key = os.environ.get("ALPACA_DATA_KEY")
    secret = os.environ.get("ALPACA_DATA_SECRET")
    if not key or not secret:
        print("ALPACA_PREFLIGHT MISSING_SECRET")
        return 2
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    for timeframe in ("1Day", "1Min"):
        params = {"symbols": "AAPL", "timeframe": timeframe,
                  "start": "2024-01-03T14:30:00Z" if timeframe == "1Min" else "2024-01-03T00:00:00-05:00",
                  "end": "2024-01-03T20:59:59Z" if timeframe == "1Min" else "2024-01-03T23:59:59-05:00",
                  "feed": "sip", "adjustment": "raw", "asof": "-", "limit": 10000}
        try:
            raw = request("https://data.alpaca.markets/v2/stocks/bars?"+urlencode(params), headers)
            result = json.loads(raw, parse_float=D)
            bars = result["bars"]["AAPL"]
            for bar in bars:
                normalize("2024-01-03", *(bar[k] for k in ("o","h","l","c","v")))
            if not bars or result.get("next_page_token"):
                raise ValueError("UNEXPECTED_EMPTY_OR_PAGINATED_SMOKE")
            print("ALPACA_PREFLIGHT "+json.dumps({"timeframe": timeframe, "status": "PASS",
                                                  "source": "sip", "rows": len(bars)}), flush=True)
        except Exception as exc:
            # A fixed allowlist only; no URL, raw response, token, or stack trace.
            code = str(exc) if str(exc) in {"HTTP_400", "HTTP_401", "HTTP_403", "HTTP_429",
                                            "HTTP_500", "HTTP_503", "NETWORK_UNAVAILABLE"} else type(exc).__name__
            print("ALPACA_PREFLIGHT "+json.dumps({"timeframe": timeframe, "status": "FAILED",
                                                  "error_code": code}), flush=True)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
