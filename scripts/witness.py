#!/usr/bin/env python3
"""Witness the TradeBotAlpha Signal Ledger anchor.

Fetches the public anchor digest, stores it byte-for-byte as anchors/anchor-<AnchorDate>.txt, and checks it
against every anchor already witnessed here. Standard library only.

Exit codes: 0 = ok (changed or not), 1 = could not fetch or parse (nothing written),
2 = integrity alarm (the anchor IS written, so the evidence is kept, but the run must fail).

    python3 scripts/witness.py                          # latest anchor
    python3 scripts/witness.py --backfill 2026-06-15 2026-09-14
    python3 scripts/witness.py --check                  # re-check every stored anchor, fetch nothing
"""
import datetime as dt
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("ANCHOR_BASE_URL", "https://tradebotalpha.com/ledger/anchor")
ANCHORS = Path(__file__).resolve().parent.parent / "anchors"

FIELDS = [
    ("AnchorDate", r"\d{4}-\d{2}-\d{2}"),
    ("HeadSeqNo", r"\d+"),
    ("HeadHash", r"[0-9a-f]{64}"),
    ("EntryCount", r"\d+"),
    ("ScoringRuleVersion", r"v\d+"),
    ("AnchoredAtUtc", r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{7}Z"),
]


def parse(text):
    """The digest is exactly six key=value lines, LF endings, trailing newline, in this order."""
    if not text.endswith("\n"):
        raise ValueError("digest does not end with a newline")
    lines = text[:-1].split("\n")
    if len(lines) != len(FIELDS):
        raise ValueError(f"expected {len(FIELDS)} lines, got {len(lines)}")
    out = {}
    for line, (key, pattern) in zip(lines, FIELDS):
        m = re.fullmatch(rf"{key}=({pattern})", line)
        if not m:
            raise ValueError(f"malformed line: {line[:80]!r}")
        out[key] = m.group(1)
    out["HeadSeqNo"] = int(out["HeadSeqNo"])
    out["EntryCount"] = int(out["EntryCount"])
    return out


def fetch(url):
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tradebotalpha-ledger-witness"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            last = e
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"could not fetch {url}: {last}")


def read_exact(path):
    # Exactly as stored: no newline translation (Path.read_text only takes newline= from 3.13).
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def stored():
    result = {}
    for p in sorted(ANCHORS.glob("anchor-*.txt")):
        result[p.stem.removeprefix("anchor-")] = parse(read_exact(p))
    return result


def check(new, others):
    """Alarms for a new anchor against every other witnessed anchor."""
    alarms = []
    for date, old in others.items():
        if old["HeadSeqNo"] == new["HeadSeqNo"] and old["HeadSeqNo"] > 0 and old["HeadHash"] != new["HeadHash"]:
            alarms.append(f"head SeqNo {new['HeadSeqNo']} carried hash {old['HeadHash']} on {date} but {new['HeadHash']} on {new['AnchorDate']}")
        if date < new["AnchorDate"] and (old["HeadSeqNo"] > new["HeadSeqNo"] or old["EntryCount"] > new["EntryCount"]):
            alarms.append(f"{new['AnchorDate']} (head {new['HeadSeqNo']}, count {new['EntryCount']}) is behind the earlier anchor of {date} (head {old['HeadSeqNo']}, count {old['EntryCount']})")
        if date > new["AnchorDate"] and (old["HeadSeqNo"] < new["HeadSeqNo"] or old["EntryCount"] < new["EntryCount"]):
            alarms.append(f"{new['AnchorDate']} (head {new['HeadSeqNo']}) is ahead of the later anchor of {date} (head {old['HeadSeqNo']})")
    return alarms


def witness(text, report):
    anchor = parse(text)
    path = ANCHORS / f"anchor-{anchor['AnchorDate']}.txt"
    existing = stored()
    alarms = check(anchor, {d: a for d, a in existing.items() if d != anchor["AnchorDate"]})

    if anchor["AnchorDate"] in existing:
        previous = read_exact(path)
        if previous == text:
            report.append(f"{anchor['AnchorDate']}: already witnessed (head {anchor['HeadSeqNo']})")
            return alarms
        old = existing[anchor["AnchorDate"]]
        if old["HeadHash"] != anchor["HeadHash"] and old["HeadSeqNo"] >= anchor["HeadSeqNo"]:
            alarms.append(f"the anchor of {anchor['AnchorDate']} changed from head {old['HeadSeqNo']}/{old['HeadHash']} to head {anchor['HeadSeqNo']}/{anchor['HeadHash']}")
        report.append(f"{anchor['AnchorDate']}: re-issued (head {old['HeadSeqNo']} -> {anchor['HeadSeqNo']})")
    else:
        report.append(f"{anchor['AnchorDate']}: witnessed head {anchor['HeadSeqNo']} ({anchor['EntryCount']} entries) {anchor['HeadHash'][:12]}")

    ANCHORS.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return alarms


def main(argv):
    report, alarms = [], []
    try:
        if argv[:1] == ["--check"]:
            existing = stored()
            for date, a in existing.items():
                alarms += check(a, {d: o for d, o in existing.items() if d != date})
            report.append(f"checked {len(existing)} stored anchors")
        elif argv[:1] == ["--backfill"]:
            day, end = dt.date.fromisoformat(argv[1]), dt.date.fromisoformat(argv[2])
            while day <= end:
                text = fetch(f"{BASE}/{day.isoformat()}.txt")
                if text is not None:
                    alarms += witness(text, report)
                day += dt.timedelta(days=1)
        else:
            text = fetch(f"{BASE}/latest.txt")
            if text is None:
                raise RuntimeError("latest anchor returned 404")
            alarms += witness(text, report)
    except (RuntimeError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print("\n".join(report))
    summary = report[-1] if report else "no anchor"
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"summary={summary}\n")
    if alarms:
        # De-duplicate: the same pair can be reported from both sides.
        unique = list(dict.fromkeys(alarms))
        print("\nINTEGRITY ALARM:\n- " + "\n- ".join(unique), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
