"""Post the next scheduled pixel_battle short to TikTok via Publer.

Mirrors the nihongo-reels pipeline, which has posted to TikTok daily via Publer
since April 2026, so this path is proven rather than theoretical. Publer holds an
audited TikTok API client and posts on our behalf; we never talk to TikTok's
Content Posting API directly, which no self-built client can be approved for.

ACCOUNT ISOLATION — the reason this file does not just call
publer_client.post_video_to_tiktok():
    That helper reads PUBLER_TIKTOK_ACCOUNT_ID, which in this user's shell is the
    JAPANESE LEARNING account. Reusing it would publish stick-figure fight videos
    to a Japanese-study audience. This module requires its own variable,
    PIXEL_BATTLE_PUBLER_ACCOUNT_ID, and refuses to run if the two match.

Order and captions come from tools/plan_posting.py and tools/gen_captions.py, so
consecutive posts differ in winning side, arena, matchup and opening line.

Usage:
  python3 tools/publish_tiktok.py                  # dry run: show what WOULD post
  python3 tools/publish_tiktok.py --post           # actually schedule the next one
  python3 tools/publish_tiktok.py --status         # queue progress
  python3 tools/publish_tiktok.py --post --at 2026-09-20T19:00:00+08:00
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

QUEUE = ROOT / "pixel_battle/output/upload_queue.json"
CAPTIONS = ROOT / "pixel_battle/output/captions"
SHORTS = ROOT / "pixel_battle/output/shorts"
COVERS = ROOT / "pixel_battle/output/covers"

ACCOUNT_ENV = "PIXEL_BATTLE_PUBLER_ACCOUNT_ID"


def _notify(msg: str, ok: bool = True) -> None:
    """Telegram on success AND failure — the phone is the primary channel."""
    try:
        import telegram_notify as tn
        send = getattr(tn, "_send_raw", None)
        if send:
            send(("✅ " if ok else "🔴 ") + msg)
    except Exception as e:                       # never let notification break the post
        print(f"[notify] skipped: {type(e).__name__}: {e}")


def _plan() -> list[dict]:
    r = subprocess.run([sys.executable, str(ROOT / "tools/plan_posting.py"), "--json"],
                       capture_output=True, text=True, cwd=str(ROOT))
    if r.returncode != 0:
        raise SystemExit(f"plan_posting failed:\n{r.stderr}")
    return json.loads(r.stdout)


def _build_queue() -> list[dict]:
    """Queue = posting plan + caption + file paths. Existing statuses are kept."""
    prior = {}
    if QUEUE.exists():
        prior = {e["stem"]: e for e in json.loads(QUEUE.read_text(encoding="utf-8"))}
    out = []
    for p in _plan():
        stem = p["stem"]
        e = prior.get(stem, {"stem": stem, "status": "pending"})
        cap = CAPTIONS / f"{stem}.txt"
        e.update({
            "post_no": p["post_no"],
            "video": str((SHORTS / f"{stem}.mp4").relative_to(ROOT)),
            "cover": str((COVERS / f"{stem}.png").relative_to(ROOT)),
            "caption": cap.read_text(encoding="utf-8") if cap.exists() else None,
            "title": f"{p['left']} VS {p['right']}",
        })
        out.append(e)
    out.sort(key=lambda e: e["post_no"])
    QUEUE.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def _next_pending(q: list[dict]) -> dict | None:
    return next((e for e in q if e.get("status") == "pending"), None)


def _resolve_account() -> tuple[str, str, str]:
    api_key = os.environ.get("PUBLER_API_KEY")
    workspace = os.environ.get("PUBLER_WORKSPACE_ID")
    account = os.environ.get(ACCOUNT_ENV)
    missing = [n for n, v in (("PUBLER_API_KEY", api_key),
                              ("PUBLER_WORKSPACE_ID", workspace),
                              (ACCOUNT_ENV, account)) if not v]
    if missing:
        raise SystemExit(
            "missing env: " + ", ".join(missing) + "\n"
            f"  {ACCOUNT_ENV} must be the TikTok account id for the pixel_battle\n"
            "  channel, taken from Publer after connecting it. It is deliberately\n"
            "  NOT PUBLER_TIKTOK_ACCOUNT_ID, which points at another channel.")
    shared = os.environ.get("PUBLER_TIKTOK_ACCOUNT_ID")
    if shared and shared == account:
        raise SystemExit(
            f"refusing to post: {ACCOUNT_ENV} equals PUBLER_TIKTOK_ACCOUNT_ID.\n"
            "  That id belongs to a different channel; posting fight videos there\n"
            "  would send them to the wrong audience.")
    return api_key, workspace, account


def main() -> int:
    q = _build_queue()
    done = sum(1 for e in q if e.get("status") == "uploaded")

    if "--status" in sys.argv:
        for e in q:
            print(f"{e['post_no']:>3} {e['stem']:24} {e.get('status'):9} "
                  f"{e.get('uploaded_at') or ''}")
        print(f"\n{done}/{len(q)} uploaded")
        return 0

    nxt = _next_pending(q)
    if nxt is None:
        print(f"queue empty — all {len(q)} posted")
        return 0

    missing_caption = nxt.get("caption") is None
    video = ROOT / nxt["video"]
    problems = []
    if missing_caption:
        problems.append(f"no caption file for {nxt['stem']} "
                        f"(run: python3 tools/gen_captions.py --write pixel_battle/output/captions)")
    if not video.exists():
        problems.append(f"missing video {nxt['video']}")

    print(f"next up: #{nxt['post_no']} {nxt['stem']} — {nxt['title']}")
    print(f"  video   {nxt['video']}  ({video.stat().st_size/1e6:.1f} MB)"
          if video.exists() else f"  video   {nxt['video']}  MISSING")
    print(f"  cover   {nxt['cover']}")
    print("  caption:")
    for line in (nxt.get("caption") or "(none)").splitlines():
        print(f"    {line}")
    if problems:
        for p in problems:
            print(f"  PROBLEM: {p}")
        return 1

    if "--post" not in sys.argv:
        print("\ndry run — nothing sent. Add --post to schedule it.")
        return 0

    api_key, workspace, account = _resolve_account()
    at = None
    if "--at" in sys.argv:
        at = datetime.fromisoformat(sys.argv[sys.argv.index("--at") + 1])
    else:
        at = datetime.now(timezone.utc) + timedelta(seconds=90)

    import publer_client as pc
    try:
        up = pc.upload_video(api_key, workspace, video)
        media_id = up.get("id")
        if not media_id:
            raise RuntimeError(f"Publer upload returned no id: {up}")
        thumb = up.get("thumbnail") or up.get("path")
        resp = pc.schedule_tiktok_video(api_key, workspace, account, media_id,
                                        nxt["caption"], thumbnail_url=thumb,
                                        scheduled_at=at)
    except Exception as e:
        msg = f"pixel_battle #{nxt['post_no']} {nxt['stem']} 發布失敗: {type(e).__name__}: {e}"
        print(msg)
        _notify(msg, ok=False)
        return 1

    job = (resp or {}).get("job_id")
    nxt["status"] = "uploaded"
    nxt["uploaded_at"] = datetime.now().astimezone().isoformat()
    nxt["publer_job"] = job
    QUEUE.write_text(json.dumps(q, indent=2, ensure_ascii=False), encoding="utf-8")

    msg = (f"pixel_battle #{nxt['post_no']} {nxt['title']} 已排入 TikTok\n"
           f"排定 {at.isoformat(timespec='seconds')}  job={job}\n"
           f"進度 {done+1}/{len(q)}")
    print(msg)
    _notify(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
