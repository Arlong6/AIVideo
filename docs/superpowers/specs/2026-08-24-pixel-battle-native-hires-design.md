# pixel_battle Native Hi-Res 設計

**日期**: 2026-08-24
**狀態**: 設計已核可,待實作
**前置**: repo 收尾完成 (commit 2439992);b01-b21 渲染成品已遺失,需重新渲染

本文所有數字均為 2026-08-24 在 main (2439992) 上實測所得,非估計值。

---

## 1. 問題

打鬥畫面以 480x854 渲染後上採樣 2.25 倍到 1080x1920,火柴人的細線條與武器特效在滿版手機上偏糊。

| 項目 | 實測值 | 來源 |
|---|---|---|
| raw 輸出 | 480x854 @60fps | `ffprobe` b01_lumen_jugg_raw.mp4 |
| 成品輸出 | 1080x1920 @30fps | 同上 (_short.mp4) |
| 放大倍率 | 2.25x | `build_short.py:86` `scale=1080:1920:flags=lanczos` |
| 現行補償 | `unsharp=5:5:0.35` | 註解自述 "recover crispness after the upscale" |
| 渲染耗時 | 33.5 秒/部,10.2 ms/幀 | 實跑 b01 (3274 幀) |

HUD 與字幕是 `build_short.py` 用 PIL 繪製的原生 1080x1920 overlay,本來就清晰。**收益精準落在打鬥畫面本身**。

### 時機

b01-b21 渲染成品已遺失(本機 `output/` 僅存 b01;SSD 上 `pixel_battle_archive_20260601/` 是 6/01 更早期實驗,非該批)。腳本 yaml 與引擎代碼完整,重跑即可還原。既然無論如何都要重渲染一輪,此時導入 hi-res 不需額外付「21 部重渲染」的代價。

### 成本不構成取捨

2.25 倍邊長約 5 倍像素量,但 Python 端幾何與模擬成本不變,只有 rasterization 變重。即使保守估 5 倍,一輪 21 部約 1 小時,可接受。

---

## 2. 目標與非目標

**目標**
- 打鬥畫面原生 1080x1920,消除 2.25 倍上採樣
- 打鬥行為(KO 時間、命中序列、勝負)與現況完全一致
- 單一開關 `S=1.0` 可完整還原舊行為

**非目標**
- 不改遊戲平衡、招式、鏡頭邏輯
- 不改 HUD/字幕排版(已是原生 1080)
- 不處理 480/854=0.5621 與 1080/1920=0.5625 之間 0.08% 的長寬比差異。854 對 9:16 精確值 853.33 僅多 0.67px,視覺不可辨
- 不改動 `engine/` 的 episode 渲染路徑(見 §4 範圍界定)

---

## 3. 方案選擇

### 採用: 物理/渲染分離 + shim

物理座標系完全不動(`renderer.py` WIDTH=480 / HEIGHT=854、`physics.py` ARENA_LEFT=10 / ARENA_RIGHT=470 / GROUND_Y=700),只在繪圖出口把座標與線寬乘上縮放係數 S。

**選它的理由**: 打鬥行為不可能改變 — 這是結構保證而非測試兜底。失敗模式從「隱性改變遊戲結果」降級為「某元素明顯畫錯位置」,肉眼可見。座標先算後乘再取整,小數精度反而優於現況。

**關鍵支撐事實**: 物理與邏輯層天然不依賴 pygame。實測 `engine/` 下 `physics.py`、`battle.py`、`character.py`、`skill.py`、`rng.py`、`effects.py` 全部零 pygame import。分界線是現成的,不需人為切割。

### 未採用: 全域常數縮放

單一 RENDER_SCALE 貫穿物理與渲染。概念統一,但兩者共用同一套座標系,漏掉任一空間常數就改變打鬥結果,且失敗是隱性的 — 影片看起來正常但 KO 時間已變,21 場需全數重驗。這是原 roadmap 標為 effort-6 的原因。

### 未採用: 超採樣

畫大再降回。仍需縮放座標才有意義,等於本方案多做一次降採樣。

### shim 相對顯式改寫的取捨

兩者物理層同樣不動。顯式作法把每個呼叫點改為 `d.line(...)`,需修改 324 處;shim 在檔案頂端替換 import,呼叫點零修改。選 shim 是因為 324 個繪圖呼叫的機械式改寫本身就是出錯來源,而 shim 把縮放邏輯集中在單一檔案便於審查。代價是隱式替換,需在模組 docstring 與各 import 點明確標示。

---

## 4. 架構

### 範圍界定(實測)

實跑 `render_script(b01)` 後 dump `sys.modules`,執行時期實際載入且 import pygame 的模組**僅 7 個**:

| 模組 | 處置 |
|---|---|
| `rl/stick_renderer.py` | 套 shim(另含 `from pygame import gfxdraw`,line 14) |
| `rl/impact_fx.py` | 套 shim(延遲 import,由 play.py:1300 載入) |
| `rl/hud.py` | 套 shim(延遲 import,由 play.py:1299 載入) |
| `rl/weapons.py` | 套 shim |
| `rl/play.py` | 套 shim |
| `rl/play_scripted.py` | 套 shim |
| `video/recorder.py` | **不套 shim**,改由呼叫端傳入縮放後尺寸 |

`engine/` 下另有 9 個 import pygame 的檔案(animator、banner、charge_fx、cinematic、hud、impact_fx、particles、projectile、renderer),經實測**不在 b01-b21 主線上** — 它們屬於 `engine/battle.py` 的 episode 路徑(ep01 等)。本次不改動。`episodes/` 與 `video/captions.py` 同理。

`rl/hud.py` 與 `rl/impact_fx.py` 是函式內延遲 import,靜態掃描看不到,必須從執行時期清單確認 — 這是本節數字以實跑而非 grep 為準的原因。

### shim 模組

新增 `pixel_battle/rl/scaled_pygame.py`(約 150-200 行),持有全域縮放係數 `S`(預設 2.25;`S=1.0` 時行為與現況完全相同)。

各渲染層檔案頂端改為:

```python
from pixel_battle.rl import scaled_pygame as pygame
```

shim 以 `__getattr__` 將未覆蓋的 API 原樣轉發至真 pygame,因此 `SRCALPHA`(81 處)、`BLEND_RGB_ADD`(22 處)、`transform.rotate`、`image.load`、`display` 等不受影響。

### API 覆蓋範圍(主線 6 檔實測)

| API | 次數 | 縮放對象 |
|---|---|---|
| `draw.line` | 139 | 端點座標、width |
| `draw.circle` | 92 | 圓心、radius、width |
| `draw.polygon` | 46 | 所有頂點 |
| `draw.rect` | 33 | Rect |
| `draw.lines` | 7 | 點列、width |
| `draw.ellipse` | 7 | Rect |
| `gfxdraw.aacircle` / `filled_circle` | 3 | 圓心、radius |
| `Surface((w,h))` | 116 | 尺寸 |
| `Rect(...)` | 3 | 座標與尺寸 |
| `font.SysFont` | 5 | size |
| `transform.smoothscale` | 6 | 目標尺寸(僅絕對值) |
| `SRCALPHA` / `BLEND_*` | 106 | 純轉發 |

繪圖呼叫合計 324 處(含 gfxdraw 327)。縮放後的線寬與 radius 取 `max(1, round(v * S))`,避免細線取整後消失。

### 主畫布尺寸與取整

`854 * 2.25 = 1921.5`,非整數。處置: **主畫布固定為 1080x1920**,S=2.25 僅作用於繪圖座標與尺寸,超出畫布底部的 1.5px 自然裁切。

安全性: GROUND_Y=700 縮放後為 1575,距畫布底部 345px;地板以下區域本就是空白襯底,裁切 1.5px 不影響任何可見元素。此作法保持等比縮放(圓形仍是正圓),優於為湊整而採用非等比 Sx/Sy。

一般 Surface(非主畫布)的尺寸取 `max(1, round(v * S))`。

### 錄影尺寸

`FrameRecorder.__init__(output_path, fps, width, height)` 的尺寸由呼叫端傳入,共 3 處: `play_scripted.py:74`、`play.py:2471`、`play.py:2519`,均傳 `WIDTH, HEIGHT`。shim 使繪圖 surface 變為 2.25 倍後,這 3 處必須同步傳入縮放後尺寸,否則寫入 ffmpeg 的幀尺寸不匹配。

---

## 5. 風險點

**`get_size` / `get_rect` / `get_width` / `get_height` — 52 處**

主要審查對象。surface 尺寸經 shim 後變大,「置中」這類相對計算自動正確,但絕對像素偏移(如 `w - 40`)會產生位移。分布: `impact_fx.py` 21、`play.py` 21、`stick_renderer.py` 5、`hud.py` 4、`weapons.py` 1、`play_scripted.py` 0。逐處審查並記錄判定結果。

**既有的字型二倍技巧**

`hud.py:60-61`、`impact_fx.py:384/1115` 已使用 `SysFont(None, SIZE * 2)` 這類「畫大再縮」的文字超採樣手法。套 shim 後會變成 `SIZE * 2 * S`,需確認其後續 smoothscale 路徑仍自洽,不會過大或二次縮放。

**`pygame.surfarray` — `play.py:398`**

`import pygame.surfarray as _sa` 於函式內載入,直接操作像素緩衝而不經 draw API,需單獨確認其尺寸假設。

**`transform.smoothscale` — 6 處**

目標尺寸若由 `get_size()` 推導則自動正確;若為硬編絕對值需縮放。逐處判別。

**`display.set_mode` — 2 處**

離屏渲染使用 `SDL_VIDEODRIVER=dummy`,但仍需確認 set_mode 尺寸與 surface 尺寸一致。

---

## 6. 驗證

三層,全自動,缺一不可。

**第一層 — 行為不變**

渲染 b01,比對 `play_scripted` 的 `fight["events"]` 與 `S=1.0` 基準逐項相同(事件類型、時間戳、傷害值、勝負)。物理層不動,此層應必然通過;若不通過,代表 shim 洩漏進了邏輯層,立即停止。

**第二層 — 結構不變(抓漏縮放的主力)**

把新的 1080x1920 輸出降採樣回 480x854,與 `S=1.0` 基準逐幀比對 SSIM。任何漏乘 S 的元素會明顯跑位,SSIM 立即下降。抽樣需涵蓋: 開場、近身交戰、遠距對峙、特殊技施放、大招、KO 序列。

**第三層 — 既有測試**

維持 `555 passed`。5 個 pre-existing 失敗(test_battle ultimate x2、test_hitstop x2、test_poses garen/slam)與本工作無關: 2026-08-24 以 worktree 檢出動手前狀態 5829f7a 實跑,得到完全相同的 5 個失敗。不列入驗收標準。

---

## 7. 連帶調整

`build_short.py` 濾鏡鏈(line 86 起):
- 移除 `scale=1080:1920:flags=lanczos` — raw 已是原生 1080x1920
- 移除 `unsharp=5:5:0.35:5:5:0.0` — 該濾鏡註解自述用於補償上採樣模糊,來源變銳利後續用只會過銳
- `gradfun=1.2:16` 與 `noise=alls=2:allf=t` 保留(deband 與顆粒感與解析度無關)

---

## 8. 範圍總表

| 項目 | 規模 |
|---|---|
| 新增 `rl/scaled_pygame.py` | 約 150-200 行 |
| 改寫 import | 6 個檔案 |
| 調整 FrameRecorder 呼叫 | 3 處 |
| 審查 `get_size`/`get_rect` 類 | 52 處 |
| 審查字型二倍技巧 | 4 處 |
| 審查 `smoothscale` | 6 處 |
| 審查 `surfarray` / `set_mode` | 3 處 |
| 調整 `build_short.py` | 2 個濾鏡 |
| 物理/邏輯層改動 | 0 |
| `engine/` episode 路徑改動 | 0 |

完成後重新渲染 b01-b21,補回遺失的成品庫存。

---

## 9. 附記

**sprite 規格**: production sprite 為 736x1408。`scripts/sprite_prototype.py` 產出的 512x512 為 Imagen 原型,曾被誤複製覆蓋 production,已於 2026-08-24 還原。`gen_keyframes.py` 定義的 jump_up/apex/land 尚無 736 版本。渲染路徑不從 `assets/sprites/` 載入(全向量繪圖),與本設計無關。

**發佈通路**: 本輪不發佈。YT 頻道 2026-07-06 已遭永久終止,不得同帳號開新頻道。成品滿意後再議通路。
