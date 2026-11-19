# ADR-0030 — Regime exposure denominator and entry cohort quantity allocation

Status: Proposed; CI pending.

Measure opportunity using all strict evaluation minutes including unknown/no-trade. Measure position exposure at the opening of each minute, not invented intrabar execution timestamps. Reconstruct FIFO quantity cohorts for regime labelling but allocate the actual E5 average-cost realized PnL proportionally across closed quantities, with deterministic residual conservation. No alternate accounting or tax basis and no strategy changes. Explicitly preregister optional diagnostic version; reconcile counts/inventory/PnL. See [E6.4b](../E6_4B_REGIME_EXPOSURE.md).
