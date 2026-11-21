# decaddance-boards

Static snapshot of [Decaddance](https://github.com/allumbra/decaddance)'s daily boards, so the app can show them to someone who is signed out, with no login and no account. Public on purpose: Actions minutes are free in a public repo, and the files are public anyway.

- `snapshot_boards.py` reads the 13 boards (Challenge 1 to 5 and Combined for today and yesterday, plus Lifetime) with PlayFab's Server API every 15 minutes (`.github/workflows/snapshot-boards.yml`) and (plus empty files for tomorrow, so the first minutes after UTC midnight never 404) and deploys them as a GitHub Pages artifact at `https://allumbra.github.io/decaddance-boards/`.
- Each row is `{rank, playerAlias, score}`: the anonymous word-pair name unless the player chose to show their Play Games handle (`board_alias.py`, the same rule as the in-game board). No PlayFab id, display name or tag.
- Nothing is committed per run, so no earlier snapshot sits in git history. A player who turns their handle off or deletes their account drops out within one run (15 minutes).
- `index.json` carries `generatedAt`. dreamtime's site-watch alerts when it is more than two hours old (GitHub also pauses schedules in a repo with 60 days of no commits, so a stale snapshot is the signal).

The code here is copied from `deploy/boards-repo/` in allumbra/decaddance (with `tools/playfab/snapshot_boards.py` and `board_alias.py`); a test there checks the copies match. Change it there, not here.

Setup (once): Settings, Pages, Source = GitHub Actions; environment `snapshot-live` limited to `main`, holding the secret `PLAYFAB_SECRET_KEY` (`gh secret set PLAYFAB_SECRET_KEY -R allumbra/decaddance-boards --env snapshot-live` prompts for it).
