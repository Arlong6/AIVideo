# AIvideo 實驗日誌

每個 experiment = 一個假設 + 改動 + 預期 + 實際 + 學到 + Follow-up.
目的: 3 個月後不忘記什麼有用 / 沒用 / 為什麼.

決策框架: `STRATEGY_2026Q2.md` (90 天三階段)
檢核工具: `scripts/verify_strategy_checkpoint.py`

---

## Baseline (4/26 之前)

- 訂閱 ~10
- 影片產出 ~3 部/天 (2 Shorts + 1 Long-form)
- 平均 views: 不詳, 估 < 50
- 已知: 真實案件 fact-check 失敗導致 5 部 fabricated + 3 部 wrong 已下架

---

## EXP-01 (2026-04-29 ~ 05-01) — Phase 1 視覺 cinematic 升級

- **假設:** Imagen Ultra/Fast 9 張用於 hook/twist/resolution 3 個關鍵場景 + ffmpeg 色調 grading → CTR 提升
- **改動:** `agents/visual_agent.py` Imagen 整合 / `thumbnail_generator.py` AI bg / color grade pipeline
- **成本:** +$0.30/部 (3 Ultra + 6 Fast)
- **預期:** thumbnail 質感跳級, 影片視覺接近 @mystery2018
- **實際:** 4/30 c8T4-bbIgAU 第一部 imagen long-form (新北國三生), data 待觀察
- **學到:** Imagen Fast 配額 70/天足夠每日 1 long-form, Pollinations Flux 質感不夠
- **Follow-up:** ✅ 5/7 改 Imagen Ultra 為 thumbnail primary

---

## EXP-02 (2026-05-01) — Competitor analysis v2 (yt-dlp + 5 channels)

- **假設:** 抓 5 個真 crime channel (@mystery2018 / 光暗雜學館 / UCzut / 鄭南奎 / @laogao) 找 outlier 共同 DNA
- **改動:** `scripts/competitor_analysis.py` 用 yt-dlp 抓 30 部 / 頻道 + Anthropic Claude 分析
- **預期:** 找到 3-5 個可複製的標題模式
- **實際:** 3/5 頻道有效 data (老高 + 鄭南奎 view=null). 3 個 outlier 共同 DNA: 荒誕小因 + 保護者反轉 + 第三方情緒佐證
- **學到:** yt-dlp flat-playlist 取不到部分頻道 viewcount, 但夠用. @mystery2018 367k median (台灣本土 niche 流量大)
- **Follow-up:** ✅ EXP-03 把 5 個 rec 寫進 prompt

---

## EXP-03 (2026-05-02) — 5 競品 rec 進 prompt

- **假設:** 加「荒誕對比體」+ 「為了/就剛剛/崩潰」trigger → LLM 採用 → views 上升
- **改動:** `title_dna.py` 新增 pattern + 3 個 trigger words / `script_agent.py` description 三段式
- **預期:** 採用率 50%+, 平均 views 56 → 100+
- **實際:** 9 天後 (5/10) 採用率仍低 — 為了 1/20, 就剛剛 0/20, 崩潰 0/20
- **學到:** **LLM 把「建議採用」當「可選」, 必須升 HARD requirement**
- **Follow-up:** ✅ EXP-08 升級為 HARD ≥2 trigger

---

## EXP-04 (2026-05-02) — 同案 paraphrase dedup

- **假設:** stem-based 3-char window + 17 種 generic suffix 剝離 → 抓 paraphrase
- **改動:** `topic_manager.py:_is_too_similar` rewrite + `topics.json` 大砍 (349 → 205)
- **預期:** 同案不再被選 2 次
- **實際:** 漏抓「鄭捷案」(name_key=「鄭捷」只 2 字, < 3 char threshold), 5/5 又上傳一次
- **學到:** **2-char proper noun (鄭捷/張文/林宅) 是台灣案件常態, 3-char threshold 不夠**
- **Follow-up:** ✅ EXP-05 加 2-char prefix window

---

## EXP-05 (2026-05-06) — 鄭捷 bug fix + GEO blocklist

- **假設:** 加 2-char prefix window catch 短 proper noun
- **改動:** `topic_manager.py` 降 threshold 到 2 + 加 _GEO_PREFIXES (台灣/韓國/日本/名古 etc.) 排除
- **預期:** 抓到 鄭捷 paraphrase, 不誤判 「台南湯姆熊」vs「台南鐵路」
- **實際:** 14/14 test cases 通過. 過去 30 天 8 個重複案件全部會被擋
- **學到:** GEO 前綴是大量 false-positive 來源, 必須 hardcode blocklist
- **Follow-up:** None — 此 fix 穩定

---

## EXP-06 (2026-05-06) — 99% TIER-S prompt boost (v1)

- **假設:** prompt 最頂端 ⭐⭐⭐ 區塊 + 強調 8× ROI → LLM 主動嵌入
- **改動:** `title_dna.py` 加 TIER-S 區塊 + 8 個 trigger words 加 view_boost 標籤
- **預期:** 99% trigger 採用率 ≥ 80%
- **實際:** 5/9 review 採用率 5% (1/20). 「優先嘗試」對 LLM 太弱
- **學到:** ⭐⭐⭐ 視覺強調沒用, LLM 看 *語意強度* 不看 *視覺權重*
- **Follow-up:** ✅ EXP-08 升 HARD ≥2 (語意強度從「優先」→「必須」)

---

## EXP-07 (2026-05-07) — 4-layer truth defense

- **假設:** prompt + verify + blocklist + post-script 4 層擋住 LLM 幻想
- **改動:** `topic_manager.FABRICATED_BLOCKLIST` 加 3 / `script_agent.py` 加事實底線 / `claim_verifier.py` 新模組 / `topics.json` clean
- **預期:** 未來不再有 fact-check fail
- **實際:** 5/7 unlist 3 部歷史 fake (光華島/金山/彰化母女) → 5/10 完全 delete
- **學到:** 防禦只能擋未來, 已上傳的需要 manual unlist/delete (對 algo 仍是負信號)
- **Follow-up:** None — 防線穩定. 觀察 5/16+ 是否再出現幻想細節

---

## EXP-08 (2026-05-07) — Phase 1 三件齊發 (length / scoring / thumbnail v1)

- **假設:** 8-12 分長度 + score-based picker + Imagen Ultra thumbnail → CTR 3× / AVD 30→50%
- **改動:** `script_agent.py` 字數砍 35% / `topic_manager._score_topic` 函式 / `thumbnail_generator.py` Imagen Ultra primary + punch text + 紅字
- **成本:** +$0.06/部 thumbnail Imagen Ultra
- **預期:** Phase 1 KPI 6/6: 中位數 ≥ 100 / 0-view ≤ 5% / CTR ≥ 1.5%
- **實際:** 5/9 review 平均 73 (vs 56 baseline +30%) / Top 1 535 (vs 350 +53%) / 採用部分 trigger / 自檢通過率仍 53%
- **學到:** Imagen Ultra thumbnail 有 hooded silhouette 戲劇感 (smoke test 確認接近 @mystery2018)
- **Follow-up:** Phase 1 KPI 真正評估 6/10. 自檢未通過率高 → EXP-09 加 has_specific HARD

---

## EXP-09 (2026-05-08) — Phase 2 (Series + Wiki 中文 + Hook 3-beat)

- **假設:** Series 化 → binge-watch session +30% / Wiki 中文 query → 真實 footage / Hook 3-beat → 30s retention 60→80%
- **改動:** `series_manager.py` 5 大系列 auto-detect + auto playlist / `wiki_footage._generate_search_queries` 中文 modifier / `script_agent.py` Hook 3-beat structure
- **預期:** 後續每部 long-form 自動進對應 playlist + description header
- **實際:** **發現本機 launchd 在跑舊 generate.py (Shorts pipeline), Series 沒生效**. 5/7-5/9 上傳的 7 部全 series_tag = 空
- **學到:** 雙 cron 系統 (GH Actions + 本機 launchd) 必須同步 disable
- **Follow-up:** ✅ EXP-10 砍 launchd

---

## EXP-10 (2026-05-10) — HARD requirement + launchd kill + 3 fake delete

- **假設:** 升 trigger 從「優先」→「必採用 ≥2」+ has_specific HARD → 強迫 LLM 改變行為
- **改動:**
  - `title_dna.py` HARD ≥2 trigger + HARD has_specific (數字/地名/職業)
  - `launchctl unload com.aivideo.daily.plist` (本機 Shorts cron 停掉)
  - YT API delete 3 部 fake (Fuv6 光華島 / zV6j 金山 / OLga 彰化母女)
  - `scripts/delete_videos.py` + `scripts/verify_strategy_checkpoint.py` 工具新增
- **預期:** 5/11 起 long-form 標題 ≥80% 用 2+ trigger + 100% 含具體細節
- **實際:** 待 5/11 第一部 long-form 跑完評估
- **學到:** (待填)
- **Follow-up:** EXP-11 5/16 weekly review 評估真實採用率

---

## EXP-11 (待填, 5/16) — HARD requirement 真實採用評估

(下週日 weekly_title_review 跑完後填)

- **假設:** HARD ≥2 trigger 採用率 ≥ 70%
- **預期 metric:**
  - 99% trigger ≥ 60%
  - 為了 trigger ≥ 30%
  - 就剛剛 / 崩潰 ≥ 10%
  - has_specific ≥ 90%
- **實際:** TBD
- **Follow-up:** TBD

---

## EXP-12 (2026-05-11) — Resume A 完成 + 3.3 baseline 修正

- **假設:** Shorts→Long-form 升級策略 (todo.md Phase 3) 真的提升 views
- **改動:**
  - 1.4 dialogue rendering 視覺 cue (subtitle 『...』wrap)
  - 3.2(c) source_tag bug 修 (generate.py 加 --source CLI arg)
  - 3.3 tracker script 建立
- **預期:** 跑 tracker → 看到 D.B.庫柏 long-form upgrade 表現好不好
- **實際 (first attempt, 錯的!):** 庫柏 732 views / 14 baseline = 52× — 標記為 ✅
- **使用者抓包:** 「732 views 怎麼來的?」
- **重新查證:**
  - 4N7z7JS_gi8 是 71 秒 **Short**, 不是 long-form
  - GH Actions run 24946381573 (4/26 庫柏 long-form trigger) **FAILED**
  - 從來沒有 long-form 產出, source=shorts_upgrade 是 aspirational tag
  - 把 71s Short 跟 long-form baseline (14) 比 = apples vs oranges
- **學到 (這個最重要):**
  - **「verify 別猜」是真的, 連我自己也會掉坑**
  - tracker baseline 應該 format-matched (Short ↔ Short median, Long ↔ Long)
  - Shorts baseline (median) 自動算 = 51 views, 庫柏 732/51 = **14× Shorts median** (依然爆款但不是 52×)
- **修正:**
  - tracker 重寫: format-matched baseline, 自動分類 Short vs Long
  - 4N7z7JS_gi8 移除誤導的 source=shorts_upgrade tag
  - 現況: **0 個真正的 Shorts→Long-form 升級樣本** (3.2 從未成功)
- **Follow-up:** Phase 3 升級假設仍未測試. 若未來 Short 又破 500 views (耕讀園 535), 手動 workflow_dispatch 跑 long-form 升級 + 確認跑成功.

---

## 待嘗試 (backlog)

- **真人配音實驗** (ElevenLabs Pro $22/月 / 外包 $30/部) — Phase 2 deferred
- **Trending case 即時跟進** — Google News RSS < 72h 案件優先 (1 hr 工程)
- **TikTok cross-post** — 7 天看內容市場是否買單 (0 工程)
- **動物頻道 Pivot A** — 6/10 若劇本 C 才啟動

---

## 統計 (滾動更新)

| 指標 | 4/26 | 5/2 | 5/9 | 5/10 | 6/10 目標 |
|---|---|---|---|---|---|
| 訂閱 | ~10 | ? | ? | **25** | 225 |
| 7天平均 views | < 50 | 94 | 73 | **90** | 150+ |
| Top 1 (7天) | ? | 720 | 350 | **535** | 800+ |
| 99% trigger 採用率 | 0% | 0% | 5% | 5% | 70%+ |
| has_specific 通過率 | ? | 65% | 55% | 53% | 90%+ |
