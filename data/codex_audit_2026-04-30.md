# AIvideo Audit (2026-04-30)
Files reviewed: 53

## Critical (bugs, security)
- [CONFIRMED] agents/llm.py:44 — Claude-only configuration crashes instead of falling back
  - What: `ask()` allows execution when `_claude` exists, but the Gemini loop still calls `_gemini.models.generate_content()` unconditionally at line 51.
  - Why bad: If Gemini is not configured or failed import but Anthropic is configured, agent pipelines crash with `AttributeError` before the advertised Claude fallback can run.
  - Fix sketch: Branch on `_gemini` before the Gemini loop and call `ask_claude()` when Gemini is unavailable or exhausted.

- [CONFIRMED] footage_downloader.py:204 — Pexels fallback loop can run forever after partial success
  - What: The fallback `while clips_saved < clips_per` only breaks when `clips_saved == 0` at line 223; if one clip was already saved and the second cannot be found, `clips_saved` stays 1 forever.
  - Why bad: Shorts mode needs 2 clips per scene, so a partial fill can hang the render process indefinitely and block scheduled production.
  - Fix sketch: Track progress per fallback iteration and break when no new clip was saved.

- [CONFIRMED] topic_manager.py:123 — topic reservation is a read-modify-write race
  - What: `save_today_reserved()` reads `today_topics.json`, mutates an in-memory list, then writes it back with no lock or atomic replace.
  - Why bad: Concurrent slot jobs can choose or reserve the same topic, or one process can overwrite another process's reservation.
  - Fix sketch: Use a file lock plus atomic temp-file replace for reservation and used-topic writes.

## Important (dead code, deprecated, error handling)
- [CONFIRMED] agents/llm.py:125 — invalid Anthropic model id
  - What: The code calls `model="claude-sonnet-4-6"`, while Anthropic's documented Claude 4 model ids use dated ids such as `claude-sonnet-4-20250514` or aliases such as `claude-sonnet-4-0`.
  - Why bad: Claude fallback calls can fail at request validation, turning the paid fallback path into a hard runtime failure.
  - Fix sketch: Replace with a documented model id or load the model id from config with validation.

- [CONFIRMED] script_generator.py:711 — invalid Anthropic model fallback list
  - What: `_call_claude()` tries `claude-sonnet-4-6` and `claude-opus-4-6`, neither of which matches Anthropic's documented dated Claude 4 ids/aliases.
  - Why bad: If Gemini fails, script generation can fail across both Anthropic attempts instead of providing a fallback.
  - Fix sketch: Use valid configured ids, e.g. `claude-sonnet-4-20250514` and `claude-opus-4-1-20250805` if available.

- [CONFIRMED] topic_manager.py:80 — invalid Anthropic model fallback list
  - What: Topic suggestion fallback uses `claude-sonnet-4-6` and `claude-opus-4-6`.
  - Why bad: Topic selection can fail when Gemini is down, pushing the pipeline into stale topic banks or hard errors.
  - Fix sketch: Centralize Anthropic model names and use documented ids/aliases.

- [CONFIRMED] scripts/competitor_analysis.py:28 — invalid default Anthropic analysis model
  - What: `COMPETITOR_ANALYSIS_MODEL` defaults to `claude-sonnet-4-6`.
  - Why bad: Competitor analysis can scrape successfully and then fail during the paid analysis step unless the env var overrides the bad default.
  - Fix sketch: Change the default to a valid Anthropic model id and keep env override support.

- [CONFIRMED] youtube_uploader.py:221 — resumable upload has no retry around flaky network/API calls
  - What: `request.next_chunk()` runs in a loop with no `try/except`, backoff, or resumable retry handling.
  - Why bad: Any transient 5xx, socket timeout, or quota hiccup aborts the whole upload after the video has already been rendered.
  - Fix sketch: Wrap `next_chunk()` in bounded exponential retry for retriable Google API/network errors.

- [CONFIRMED] telegram_notify.py:22 — Telegram send failures are silent
  - What: `_send_raw()` returns without status when credentials are missing and swallows all request exceptions at lines 24-34.
  - Why bad: Callers print "notification sent" even when nothing reached Telegram, hiding failures in the alerting path itself.
  - Fix sketch: Return a boolean or raise on failure, and make callers log/report failed sends accurately.

- [CONFIRMED] generate.py:217 — upload failure returns are not notified
  - What: `upload_video()` can return `None` for missing files/credentials or API failures, but `generate.py` only notifies when `youtube_url` is truthy and otherwise completes silently.
  - Why bad: A scheduled render can finish locally but never upload, with no Telegram failure alert.
  - Fix sketch: Add an `else` branch after upload that calls `notify_failure("upload", ...)`.

- [CONFIRMED] youtube_uploader.py:269 — pinned-comment queue write errors are swallowed
  - What: `_post_pinned_comment()` catches all exceptions, queues only 403s, and only prints other failures.
  - Why bad: Comment failures are lost to logs and never propagate to the upload caller or Telegram, so engagement automation silently stops.
  - Fix sketch: Return a status from `_post_pinned_comment()` and surface non-403 failures to the caller.

- [CONFIRMED] topic_manager.py:227 — removed archive topic generator is still live dead code
  - What: `suggest_topics_from_archive()` remains defined, while `pick_topic()` explicitly says the archive path was removed at lines 334-337.
  - Why bad: The dead path preserves a known fabricated-topic source and can be accidentally reintroduced.
  - Fix sketch: Delete the function or move it to a clearly quarantined reference note outside runtime code.

- [CONFIRMED] agents/llm.py:88 — unused Claude budget guard
  - What: `_check_claude_budget()` is defined but never called before `ask_claude()` spends Anthropic tokens.
  - Why bad: The intended daily Claude cap is unenforced, so fallback cost control does not work.
  - Fix sketch: Call `_check_claude_budget()` inside `ask_claude()` before `messages.create()`.

## Worth knowing (performance, observability)
- [CONFIRMED] generate_books.py:443 — rejected QA still sends a completion-style Telegram message
  - What: The summary labels `REJECT` at lines 443-448, but the Telegram message at lines 460-468 is still a generic "Books generation complete" notification.
  - Why bad: A failed quality gate should produce a failure alert, otherwise the operator can mistake a rejected video for a ready local render.
  - Fix sketch: Call a failure notification path when `qa_verdict == "REJECT"` and use success wording only for `PASS`.

- [CONFIRMED] illustration_generator.py:131 — quota reset alert text contradicts PT-based quota tracking
  - What: Quota tracking correctly uses Pacific Time, but Telegram messages still say "UTC 0:00 (Taiwan 08:00)" at lines 138, 154, 457, and 489.
  - Why bad: The operator may resume Imagen jobs hours before the actual reset and hit the same quota failure again.
  - Fix sketch: Update all quota-alert text to Pacific midnight and the current Taiwan equivalent.

- [CONFIRMED] footage_downloader.py:181 — dark-scene sorting repeatedly downloads thumbnails without caching
  - What: Every dark Pexels page sorts candidates with `_score_video_darkness()`, which fetches each thumbnail over HTTP at line 114.
  - Why bad: Long-form searches can add many extra serial network calls, increasing runtime and making Pexels/PIL thumbnail failures affect selection quality.
  - Fix sketch: Cache luminance by video id or thumbnail URL for the run.

- [CONFIRMED] daily_audit.py:45 — stale git state is silently accepted
  - What: `_git_pull_quiet()` suppresses all pull exceptions at lines 45-51.
  - Why bad: The audit can report zero or stale uploads from old local `video_log.json` without any warning that sync failed.
  - Fix sketch: Return pull status and include a warning in the audit Telegram if sync fails.

- [CONFIRMED] agents/visual_agent.py:221 — section index lookup is quadratic
  - What: The Imagen loop calls `script_sections.index(sec)` for each section.
  - Why bad: Current section counts are small, but this is unnecessary O(n^2) work in a path that may expand as visual beats grow.
  - Fix sketch: Iterate with `for sec_idx, sec in enumerate(script_sections):`.

3 critical / 11 important / 5 worth-knowing
