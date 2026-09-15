# TradeBotAlpha signal-ledger witness

An independent, public copy of the daily **Signal Ledger anchor** that TradeBotAlpha publishes at
<https://tradebotalpha.com/ledger/anchor/latest.txt>.

The Signal Ledger is an append-only, hash-chained record of every signal the bot publishes. Each
entry's hash commits to the entry before it. The daily anchor states how long that chain was and
the hash of its newest entry:

```
AnchorDate=2026-09-14
HeadSeqNo=32
HeadHash=2c94a4ca2784178497231ddc2959ebb7c831d9c6cb1f02fbfd8019b5e4ac079e
EntryCount=32
ScoringRuleVersion=v1
AnchoredAtUtc=2026-09-14T10:08:26.8266667Z
```

An anchor contains no signal content. It is a commitment: once a head hash is recorded here, the
ledger up to that entry cannot later be rewritten into a different history without disagreeing with
this repository.

## How it works

- `.github/workflows/witness.yml` runs twice a day. It fetches the latest anchor and commits it,
  byte-for-byte, as `anchors/<AnchorDate>.txt` whenever it is new or changed.
- `scripts/witness.py` checks every anchor against every anchor already witnessed. The run
  **fails** if:
  - the head moves backwards, or the entry count drops;
  - the same head SeqNo appears with a different hash;
  - a date already witnessed is re-issued with a different head.

  A failing anchor is still committed, so the evidence is kept.
- Re-check everything locally with `python3 scripts/witness.py --check` (standard library only).

## Limits

- **Late start.** The anchors dated 2026-06-15 through 2026-09-14 were first committed here on
  2026-09-14. This repository witnesses them *as of that day*, not as of the dates they carry.
  Daily witnessing starts from 2026-09-15.
- **What proves the timing.** Git commit dates are set by whoever commits. The timing evidence is
  this repository's public history and GitHub's record of each scheduled run.
- **Verifying the chain itself needs more than this repo.** It needs the ledger rows and the
  verification method, which will be published with the public track record. That includes the
  timestamp correction list for entries written before a September 2026 fix to how the ledger
  stored timestamps.
