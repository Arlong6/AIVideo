"""List the social accounts connected to your Publer workspace, read-only.

Answers "where do I find the account id" without hunting through Publer's UI.
Never writes anything and never prints the API key.

The id you want is the one whose provider is tiktok and whose name matches the
pixel_battle channel. Put it in the environment as PIXEL_BATTLE_PUBLER_ACCOUNT_ID
(NOT PUBLER_TIKTOK_ACCOUNT_ID, which points at a different channel).

Usage:
  python3 tools/publer_accounts.py                     # reads AIvideo/.env
  python3 tools/publer_accounts.py --env PATH/.env     # load credentials from a .env
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def _load_env(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"no such env file: {path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    if "--env" in sys.argv:
        _load_env(Path(sys.argv[sys.argv.index("--env") + 1]).expanduser())
    elif (ROOT / ".env").exists():
        _load_env(ROOT / ".env")

    api_key = os.environ.get("PUBLER_API_KEY")
    if not api_key:
        raise SystemExit("PUBLER_API_KEY not set. Put it in AIvideo/.env, or pass --env <path>")

    from publer_client import list_accounts, list_workspaces

    ws = list_workspaces(api_key)
    if not ws:
        raise SystemExit("no workspaces returned")
    print(f"workspaces ({len(ws)}):")
    for w in ws:
        print(f"  {w.get('name','?')}  id={w.get('id')}")

    wid = os.environ.get("PUBLER_WORKSPACE_ID") or ws[0].get("id")
    print(f"\nlisting accounts in workspace {wid}\n")
    accounts = list_accounts(api_key, wid)
    if not accounts:
        print("no connected accounts")
        return 0

    print(f"{'provider':12}{'name':28}{'id'}")
    for a in accounts:
        prov = a.get("provider") or a.get("type") or "?"
        name = a.get("name") or a.get("username") or "?"
        print(f"{prov:12}{str(name):28}{a.get('id')}")

    tiktoks = [a for a in accounts
               if (a.get("provider") or a.get("type") or "").lower() == "tiktok"]
    print(f"\ntiktok accounts connected: {len(tiktoks)}")
    if len(tiktoks) < 2:
        print("  Only one TikTok account is connected. Connect the pixel_battle\n"
              "  channel in Publer first (Accounts -> Add -> TikTok), then re-run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
