"""Synthetic E3 order and partial-fill example. Never calls a broker."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from invest_engine.domain.primitives import InstrumentId, Market, Money
from invest_engine.trading.models import OrderIntent, Side, TradingConfig
from invest_engine.trading.money import InstrumentRules, MonetaryRules
from invest_engine.trading.runtime import TradingRuntime


if __name__ == "__main__":
    instrument = InstrumentId(Market.KR, "KRX", "KR7005930003", "005930", "KRW")
    cfg = TradingConfig(
        "sim-account", (MonetaryRules("KRW", D("1")),),
        ((instrument.key, InstrumentRules(D("1"), D("1"))),),
    )
    runtime = TradingRuntime(cfg, (Money(D("1000000"), "KRW"),))
    t = datetime(2026, 11, 16, tzinfo=timezone.utc)
    intent = OrderIntent("example-1", "sim-account", "fixture", instrument,
                         Side.BUY, D("10"), D("7000"), t, D("6800"))
    outcome = runtime.submit(intent)
    runtime.accept_simulated(intent.intent_id, t + timedelta(seconds=1))
    runtime.fill_simulated(intent.intent_id, price=D("7000"), quantity=D("4"),
                           execution_id="fill-1", at=t + timedelta(seconds=2))
    runtime.request_cancel(intent.intent_id, t + timedelta(seconds=3))
    runtime.confirm_cancel(intent.intent_id, t + timedelta(seconds=4))
    print({
        "decision": outcome.decision.decision.value,
        "reservation": str(outcome.decision.reservation),
        "cash": str(runtime.state.account("KRW").settled),
        "reserved": str(runtime.state.account("KRW").reserved),
        "shares": str(runtime.state.position(instrument).quantity),
        "state_hash": runtime.state.digest,
    })
