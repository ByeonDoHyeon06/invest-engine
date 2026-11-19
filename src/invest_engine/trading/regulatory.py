"""Offline dated US regulatory rate evidence (not brokerage invoice rules)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from invest_engine.domain.primitives import _decimal

D = Decimal


@dataclass(frozen=True, slots=True)
class USRegulatorySchedule:
    start: date
    end_exclusive: date
    sec_rate: Decimal
    taf_per_share: Decimal
    taf_cap_per_trade: Decimal
    source_urls: tuple[str, ...]
    version: str

    def __post_init__(self) -> None:
        if (type(self.start) is not date or type(self.end_exclusive) is not date
                or self.start >= self.end_exclusive or not self.version.strip()
                or not self.source_urls or any(not url.startswith("https://")
                                              for url in self.source_urls)):
            raise ValueError("INVALID_REGULATORY_SCHEDULE")
        for name in ("sec_rate", "taf_per_share", "taf_cap_per_trade"):
            if _decimal(getattr(self, name), field=name) < 0:
                raise ValueError("NEGATIVE_REGULATORY_RATE")
        if self.sec_rate >= 1:
            raise ValueError("INVALID_SEC_RATE")
        if self.taf_per_share > 0 and self.taf_cap_per_trade <= 0:
            raise ValueError("INVALID_TAF_CAP")

    def covers(self, charge_date: date) -> bool:
        return self.start <= charge_date < self.end_exclusive


# Intersection of SEC 2022 adjustment and 2022 FINRA equity TAF period.
# No extrapolation into January 2023 (the TAF rate changed).
US_2022 = USRegulatorySchedule(
    date(2022, 5, 14), date(2023, 1, 1), D("0.00002290"),
    D("0.000130"), D("6.49"),
    ("https://www.sec.gov/newsroom/press-releases/2022-60",
     "https://www.sec.gov/newsroom/press-releases/2023-15",
     "https://www.govinfo.gov/content/pkg/FR-2020-10-20/pdf/2020-23141.pdf"),
    "us-covered-equity-2022-v1",
)


