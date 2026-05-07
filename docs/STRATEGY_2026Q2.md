# Crime 頻道 90 天突破計畫 (2026-05-07 ~ 2026-08-07)

## 現況診斷

| 指標 | 我們 | 對標 @mystery2018 | 缺口 |
|---|---|---|---|
| 訂閱 | 估 < 5k | 數十萬 | - |
| 中位數觀看 | 48 (long) | 367,871 | **7,664×** |
| 上傳頻率 | 21/週 | ~2/週 | 過量 11× |
| Top 1 (30天) | 732 views | ~1.1M | - |
| 標題 DNA 命中 | 100% (但深度不夠) | - | 質量問題 |
| Thumbnail 設計 | Pexels 隨機路人 | 設計過 noir + 大字 | 嚴重落後 |
| 配音 | AI TTS | 真人 | 影響可信度 |
| 內容定位 | 全球 (TW/JP/KR/US) | 台灣本土 | 算法分不出頻道 |

**Root causes (按 impact 排序):**

1. **算法信號被稀釋** — 21 部/週 vs 同領域的 2-3 部/週。每部都「平均 48 views」,YT 算法無法識別任何一部值得推
2. **頻道無辨識度** — 全球題材 + AI 配音 + Pexels 縮圖 = 算法歸不到任何 niche cluster
3. **Thumbnail 是最大短板** — CTR 直接決定 algo 推不推,我們縮圖 quality < 1/10 競品
4. **品質方差過大** — 5 部 700+ views vs 30 部 0-50 views,沒有「穩定底線」算法不敢推
5. **AI 配音 + AI 腳本 雙 AI 標籤** — YT 2026 強制 disclose synthetic media, 算法天生壓制

---

## 競品 benchmark (5 個成功案例提煉)

### @mystery2018 (台灣本土, 367k median)
- **策略**: 100% 台灣在地化(地名 + 本土機構 + 政治隱喻)
- **節奏**: 每部 15-25 分鐘, 慢推進, 細節密
- **標題**: 第一人稱「我查了…」「我發現…」(製造主持人 IP)
- **可學**: 在地識別度 + 第一人稱

### 老高與小茉 (~700萬訂閱, 千萬 views 常態)
- **策略**: 反智 + 反主流(陰謀論定位)
- **節奏**: 雙人對談 + 動畫補位 + 8-15 分鐘
- **標題**: 「你絕對沒聽過」「99%人不知道」公式化
- **可學**: 對談感 + 知識感包裝(我們純解說太單調)

### 腦洞烏托邦 (252萬, title_dna 源頭)
- **策略**: 政治 + 懸案 + 國際關係(高 controversy)
- **可學**: 標題公式(已部分 ported)

### 光暗雜學館 (102k, 國際懸案)
- **策略**: 受害者導向(共情驅動)
- **節奏**: 8-12 分鐘短長片,案件密度高
- **可學**: 中等長度 (8-12 分) 比我們 15-20 分更易過 retention

### JCS Criminal Psychology (英語, 1000萬訂閱)
- **策略**: 「警察審訊心理分析」 — 高度 niche
- **節奏**: 配上原始警察錄像 + 即時心理 caption
- **可學**: 高度 niche down + 用真實素材(我們缺真實 footage)

---

## 90 天 Roadmap (3 phase)

### Phase 1 (Day 1-30, 5/7-6/6) — **減量 + 品質基礎**

**已執行 (今天):**
- ✅ Shorts cron 停掉
- ✅ Long-form 改 Mon/Wed/Fri (3部/週)
- ✅ Fact-check 4 layer defense
- ✅ Title DNA 99% TIER-S 強化

**待 ship (本月):**
- 🟡 **Thumbnail 升級 v1** — Imagen Ultra 生 hero face + ffmpeg overlay 大字 (8-12 字標題核心詞)
  - Effort: ~2 天
  - 預期 effect: CTR 從 ~0.5% → 1.5%+ (3×)
- 🟡 **Niche 收縮** — 暫凍 japan/korea_china/famous_intl bank,只跑 taiwan + 台灣 ai_generated
  - Effort: 30 分鐘
  - 預期 effect: 算法 cluster 進「台灣懸案」, 推送精度提升
- 🟡 **長度收斂 8-12 分鐘** — 現在 15-20 分,retention 應該腰斬。reduce script_agent target word count
  - Effort: 1 天 + A/B 觀察
  - 預期 effect: AVD 從估計 30% → 50%+
- 🟡 **Score-based topic picker** — 加歷史爆款 DNA 評分, 高分先做
  - Effort: 1 天
  - 預期 effect: 砍掉低分案件,中位數 48 → 100+

**Phase 1 KPI (6/6 檢核):**
- 中位數 long-form views ≥ 100 (現 48)
- 0-view 率 ≤ 5% (現 9%)
- CTR ≥ 1.5%

### Phase 2 (Day 31-60, 6/7-7/6) — **品質拉開**

- **真人配音實驗** — 找台灣 podcast 風格 voice (ElevenLabs Pro 或外包)
  - Effort: 預算 + 1 週
  - 預期 effect: AI label 移除, retention +20%
- **B-roll 真實素材** — 加爬 Wikimedia + 政府公開影像 + YT CC-BY 新聞片段
  - Effort: 3 天 (新 agent module)
  - 預期 effect: 影片質感提升, AI 痕跡降低
- **Series 化** — 「台灣冤案系列」「台灣黑幫往事」分系列, playlist 強化 binge
  - Effort: 1 天 metadata 改造
  - 預期 effect: session watch time +30%
- **Hook 重構 first 30s** — 模仿 JCS 開場, 用最荒誕細節 cold-open
  - Effort: script_agent prompt 改 + 評估

**Phase 2 KPI (7/6):**
- 中位數 ≥ 300
- AVD ≥ 50%
- 訂閱 +500/月

### Phase 3 (Day 61-90, 7/7-8/7) — **規模化**

- **Collaboration** — 合作其他犯罪/懸案頻道(互推 / playlist 交換)
- **Long-tail SEO 優化** — 描述欄 / hashtag / closed captions 滿配
- **trending case 優先** — 結合 Google Trends API, 新聞時效性高的案件第一時間做
- **Member-only 內容** — 開 Membership tier (深度版/未公開細節)
- **A/B test thumbnails** — 每部影片做 2 thumbnail variants

**Phase 3 KPI (8/7):**
- 中位數 ≥ 1,000 views
- 訂閱 ≥ 5,000
- 單一爆款 ≥ 10,000 views

---

## 製作品質 6 個改造方向 (按 ROI 排序)

### 1. Thumbnail 設計 (ROI: 5×)
**現況**: Pexels 隨機路人圖 + 黑白濾鏡 + 偶爾標題字
**目標**: Imagen Ultra hero face + 大字 4-6 字 hook + 紅色強調色
**參考**: @mystery2018 / 光暗雜學館 / JCS Criminal Psychology
**Spec**:
- 1280×720, ~30% face / 70% text
- 字體: 黑體粗 / 紅黃黑配色
- 4-8 字 hook ("99%沒看懂" "他被殺前夜")

### 2. Hook 結構 (ROI: 3×)
**現況**: 平鋪直敘介紹案件
**目標**: First 30s 用最荒誕細節 cold-open + 「接下來你會看到…」承諾
**參考**: JCS / Lemmino
**Spec**:
- 0-5s: 1 個 sound bite + 黑底大字
- 5-15s: 最荒誕細節 (傷亡數字, 兇手身分反轉)
- 15-30s: "今天我帶你拆解..." 承諾 + 訂閱誘餌

### 3. 配音真人化 (ROI: 2.5×)
**現況**: edge-tts 中文 (聽起來機械)
**目標**: ElevenLabs Pro voice clone 或外包真人台灣口音
**成本**: ElevenLabs Pro $22/月, 或外包 $30/部
**注意**: AI 配音被 YT 演算法天生壓制 (2026 synthetic media 規範)

### 4. 影片長度收斂 (ROI: 2×)
**現況**: 15-20 分鐘
**目標**: 8-12 分鐘 (光暗雜學館的甜蜜點)
**理由**: AVD (平均觀看時長) 是 retention 關鍵, 短一點更易破 50%

### 5. B-roll 真實素材 (ROI: 1.5×)
**現況**: Pexels stock + Imagen 生成 (3 場景)
**目標**: 加爬 Wikimedia 公共領域 + 政府公開影像 (台灣司法院 / 警政署)
**Effort**: 新 footage_downloader 模組

### 6. 字幕 burn-in 優化 (ROI: 1.2×)
**現況**: SRT 上傳 (用戶要手動開)
**目標**: 燒入大字幕 (Mr. Beast 風)
**理由**: 移動端用戶 50%+ 不開字幕, burn-in 強制可見

---

## 題材方向 (niche down)

### 主軸: 台灣懸案專營 (70% 配比)

**為什麼 niche down**:
- 算法需要識別頻道 cluster
- @mystery2018 367k 中位數證實台灣本土流量大
- 我們有 fact-check 優勢(中文 source 易驗證)

**子系列建議:**
1. 「**台灣冤案檔案**」 — 江國慶 / 鄭性澤 / 邱和順 / 蘇建和 等已平反 / 仍爭議的冤案
2. 「**台灣未解懸案**」 — 江子翠 / 林宅血案 / 劉邦友 / 彭婉如 等未破案
3. 「**台灣校園黑色史**」 — 國三生 / 嘉義大學 / 校園命案
4. 「**台灣政治謀殺疑雲**」 — 林宅血案 / 陳文成 / 王迎先 等政治意涵案件
5. 「**台灣黑幫往事**」 — 竹聯 / 四海 / 陳啟禮 / 翁奇楠 等黑道刑案

### 副軸: 國際高知名案 (30% 配比, 用於拓客流量)
- 日本: 世田谷 / 名古屋 / 秋葉原 / 三億円
- 韓國: 華城 / N號房 / 趙斗淳
- 國際: BTK / Zodiac / Dahmer
- **限制**: 只做 Wikipedia 中文有專條的案件

### 不做:
- 純歷史案件 (1900 年前)
- 沒有確鑿證據的案件
- 美國地方案件 (台灣觀眾共鳴低)
- 純犯罪心理學 (太抽象)

---

## 衡量指標 + checkpoint

| 週期 | 指標 | 目標 |
|---|---|---|
| 每日 | 上傳成功 + 0 errors + Imagen 配額 | green |
| 每週 (Sun) | weekly_title_review trigger 採用率 | ≥80% |
| 每兩週 | CTR (新片上傳 7 天內) | 提升 +10% |
| 每月 | 中位數 / Top 1 / 訂閱 | Phase KPI |
| 每季 | ROI 重估 (是否 pivot) | 看數據定 |

---

## 高風險假設 (要驗證)

1. **「3 部/週比 21 部/週好」** — 假設 algo runway 是瓶頸,實際可能是 quality 瓶頸. 做完 Phase 1 看
2. **「真人配音 retention +20%」** — 業內 anecdotal,不確定中文 niche 適用
3. **「Niche down 流量會升」** — 短期可能掉(global 蹭流量沒了),長期穩定後上
4. **「Thumbnail 是最大瓶頸」** — 也可能其實是 hook 30s, 同步測

---

## 不做 (避免雞肋)

- ❌ 暫不做 Membership / Patreon (訂閱數還太低,不到變現門檻)
- ❌ 暫不做廣告投放 (有機 reach 還沒榨乾)
- ❌ 暫不擴 Crime 以外 niche (老高/Books 已證實稀釋焦點)
- ❌ 暫不開直播 / community post (effort 高 / impact 低)

---

**下一步:** 今天先 ship cron 砍量 + niche 收縮(2 個 commit)。
Phase 1 其餘三項(thumbnail / 長度 / scoring)分批 ship,每項 1-2 天。
