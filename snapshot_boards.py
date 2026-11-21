#!/usr/bin/env python3
"""Write the signed-out daily boards as static JSON (HQ dd-boards-snapshot).

Reads the 13 boards (Challenge 1-5 and Combined for today and yesterday, plus
Lifetime) with the PlayFab Server API and writes one small file each, so the app can
show boards to someone who is signed out without a login or an account. Run every 15
minutes by allumbra/decaddance-boards (a public repo) and deployed as a GitHub Pages
artifact; the files are never committed, so no earlier snapshot sits in git history.

Files under --out:
  index.json                       {generatedAt, dates: [today, yesterday, tomorrow]}
  <date>/challenge-<1..5>.json     {date, scope, slot, generatedAt, entries}
  <date>/combined.json
  <date>/lifetime.json             (the lifetime board is asked for by day)
for today and yesterday, plus tomorrow: the app asks for the new UTC day the moment it
starts, so tomorrow's files exist already (daily boards empty, lifetime unchanged) and the
first 15 minutes of a day never show an error.
Each entry is {rank, playerAlias, score}: nothing else leaves this script (no PlayFab
id, tag or display name). Names come from board_alias.py, the same rule as the signed-in
board. A player who turns the handle off or deletes the account drops out on the next run.

The title key comes from the PLAYFAB_SECRET_KEY environment variable (or --secret-file)
and is never printed. Any API failure other than "that version is gone" fails the run,
so Pages keeps the previous snapshot and the staleness check can alert.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from board_alias import TITLE_ID, alias  # noqa: E402

SLOT_STAT = "dec_daily_slot_"
COMBINED_STAT = "dec_daily_combined"
LIFETIME_STAT = "dec_lifetime"
LIMIT = 100
ENTRY_KEYS = {"rank", "playerAlias", "score"}
PROFILE = {"ShowLinkedAccounts": True, "ShowTags": True}


class SnapshotError(Exception):
    pass


def board_specs(today, yesterday):
    """(date, scope, slot, statistic, file) for the 13 boards PlayFab holds."""
    specs = []
    for date in (today, yesterday):
        for slot in range(1, 6):
            specs.append((date, "Challenge", slot, SLOT_STAT + str(slot), "%s/challenge-%d.json" % (date, slot)))
        specs.append((date, "Combined", 0, COMBINED_STAT, "%s/combined.json" % date))
    specs.append((today, "Lifetime", 0, LIFETIME_STAT, "%s/lifetime.json" % today))
    return specs


class PlayFab:
    def __init__(self, secret, title=TITLE_ID, opener=None):
        self._secret = secret
        self._host = "https://%s.playfabapi.com" % title
        self._open = opener or urllib.request.urlopen

    def call(self, endpoint, body):
        request = urllib.request.Request(
            self._host + "/Server/" + endpoint, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "X-SecretKey": self._secret}, method="POST")
        try:
            with self._open(request, timeout=30) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            try:
                payload = json.load(error)
            except Exception:
                payload = {}
            detail = payload.get("error", "") if isinstance(payload, dict) else ""
            raise SnapshotError("%s failed: HTTP %d %s" % (endpoint, error.code, detail)) from None
        except Exception as error:
            raise SnapshotError("%s failed: %s" % (endpoint, type(error).__name__)) from None
        if not isinstance(payload, dict) or payload.get("code") != 200 or not isinstance(payload.get("data"), dict):
            detail = payload.get("error", "bad response") if isinstance(payload, dict) else "bad response"
            raise SnapshotError("%s failed: %s" % (endpoint, detail))
        return payload["data"]


def _ms(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000
    except Exception:
        return None


def current_version(versions, date):
    """Same rule as CloudScript currentDailyVersion: the open version activated today."""
    start = _ms(date + "T00:00:00+00:00")
    selected = None
    for v in versions:
        activation = _ms(v.get("ActivationTime") or "")
        if isinstance(v.get("Version"), int) and v["Version"] >= 0 and not v.get("DeactivationTime") \
                and activation is not None and start <= activation < start + 86400000 \
                and (selected is None or v["Version"] > selected):
            selected = v["Version"]
    return selected


def historical_version(versions, date):
    """Same rule as CloudScript historicalVersion: the version covering the end of that day."""
    beginning = _ms(date + "T00:00:00+00:00")
    end = beginning + 86400000
    selected, latest = None, float("-inf")
    for v in versions:
        start, stop = _ms(v.get("ActivationTime") or ""), _ms(v.get("DeactivationTime") or "")
        if isinstance(v.get("Version"), int) and v["Version"] >= 0 and start is not None and stop is not None \
                and beginning <= start < end and stop >= end and start > latest:
            selected, latest = v["Version"], start
    return selected


def entries_from(rows):
    """Public rows: rank (ties share), alias, score. Nothing else."""
    entries, previous, rank = [], None, 0
    for i, row in enumerate(rows):
        if previous is None or row.get("StatValue") != previous:
            rank = i + 1
        previous = row.get("StatValue")
        entries.append({"rank": rank, "playerAlias": alias(row), "score": str(row.get("StatValue"))})
    return entries


def check_public(entries, rows):
    """Last line of defence: only the three fields, and no PlayFab id anywhere in the file."""
    text = json.dumps(entries)
    for entry in entries:
        if set(entry) != ENTRY_KEYS:
            raise SnapshotError("entry has unexpected fields")
    for row in rows:
        ident = row.get("PlayFabId")
        if isinstance(ident, str) and len(ident) >= 8 and ident in text:
            raise SnapshotError("a PlayFab id reached the snapshot")


def read_board(api, spec, today, versions_cache):
    date, scope, _slot, stat, _name = spec
    version = None
    if scope != "Lifetime":
        if stat not in versions_cache:
            versions_cache[stat] = api.call("GetPlayerStatisticVersions", {"StatisticName": stat}).get("StatisticVersions") or []
        versions = versions_cache[stat]
        version = current_version(versions, date) if date == today else historical_version(versions, date)
        if version is None:
            return []  # a day that has not reset yet, or whose scores PlayFab has dropped
    request = {"StatisticName": stat, "StartPosition": 0, "MaxResultsCount": LIMIT, "ProfileConstraints": PROFILE}
    if version is not None:
        request["Version"] = version
        request["UseSpecificVersion"] = True
    try:
        data = api.call("GetLeaderboard", request)
    except SnapshotError as error:
        if scope != "Lifetime" and date != today and ("LeaderboardVersionNotAvailable" in str(error) or "1277" in str(error)):
            return []
        raise
    rows = data.get("Leaderboard") or []
    entries = entries_from(rows)
    check_public(entries, rows)
    return entries


def build(api, now, out):
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    generated = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    out = Path(out)
    files = {}
    versions_cache = {}
    for spec in board_specs(today, yesterday):
        date, scope, slot, _stat, name = spec
        entries = read_board(api, spec, today, versions_cache)
        files[name] = {"date": date, "scope": scope, "slot": slot, "generatedAt": generated, "entries": entries}
    # Tomorrow's boards: nobody has played yet; lifetime carries over.
    for slot in range(1, 6):
        files["%s/challenge-%d.json" % (tomorrow, slot)] = {
            "date": tomorrow, "scope": "Challenge", "slot": slot, "generatedAt": generated, "entries": []}
    files[tomorrow + "/combined.json"] = {
        "date": tomorrow, "scope": "Combined", "slot": 0, "generatedAt": generated, "entries": []}
    files[tomorrow + "/lifetime.json"] = dict(files[today + "/lifetime.json"], date=tomorrow)
    # Write only after every board has been read, so a failed run leaves nothing half-new.
    for name, body in files.items():
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body, separators=(",", ":")) + "\n")
    (out / "index.json").write_text(json.dumps({"generatedAt": generated, "dates": [today, yesterday, tomorrow]}) + "\n")
    return len(files)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--secret-file", type=Path)
    args = parser.parse_args(argv)
    secret = args.secret_file.read_text().strip() if args.secret_file else os.environ.get("PLAYFAB_SECRET_KEY", "").strip()
    if not secret:
        print("error: set PLAYFAB_SECRET_KEY or pass --secret-file", file=sys.stderr)
        return 2
    try:
        count = build(PlayFab(secret), datetime.now(timezone.utc), args.out)
    except SnapshotError as error:
        print("error: " + str(error), file=sys.stderr)
        return 1
    print("wrote %d boards" % count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
