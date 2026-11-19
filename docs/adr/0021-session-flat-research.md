# ADR-0021 — Explicit retry and session-flat execution hypotheses

**Status:** Accepted (offline-only, CI verified in PR #40), 2026-11-19. Extends ADR-0010/0011/0020 without changing legacy defaults.

## Context
E5.13 entry-only ORB retained positions overnight; the one-shot hold comparator sometimes never entered. Cash-only return did not measure buy-and-hold, and overnight inventory made intraday interpretation misleading.

## Decision
Add explicitly opted-in single-strategy fixed-window policies: session-retry hold v2 with first confirmed entry latch and no rebalancing; session-flat mode with existing standing protection and precommitted adverse last-minute-open liquidation. All modeled fills use E3 risk/fees and E4 attribution. Unknown order ordering, late inventory or incomplete liquidation fail closed. No-fill comparator return is undefined. Pin policy versions in config hashes. Retain E5.13 controls and separately label new historical experiments.

## Alternatives
Do not assume unconditional market entry at sampled close/open, fake orders at past timestamps, infer intrabar path, or force fills beyond volume. A quote/tick execution model or actual broker order semantics require independently validated input and belong to later research.

## Consequences
Comparison coverage improves but is not guaranteed. Last-minute-open model trades an assumed price and volume bound, not a verified venue fill. No endpoint schema or Live support. Existing default behavior stays intact.

## Revisit
When a licensed timestamped quote/trade feed, broker execution evidence or wider independent evaluation supports a revised model; never retune on final holdout.
