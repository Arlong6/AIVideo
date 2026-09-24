# pixel_battle 新玩法評估：大混鬥、附屬武器

2026-09-25 · 依實際讀碼估算，不是憑感覺

arlong 早先提到第二個月要「慢慢做更多變化，可能大混鬥或是附屬武器」。這份文件回答一個問題：**這兩個各要動多少、值不值得、先做哪個。**

## 結論先講

| | 大混鬥（3 人以上） | 附屬武器（中途換武器） |
|---|---|---|
| 引擎改動 | **深**：`Battle(left, right)` 寫死兩人，`.left`/`.right` 在 engine 27 處、renderer 80 處、env 18 處、HUD 6 處 | **淺**：武器是靜態查表 `_WEAPONS[char_id]`，渲染依 `weapon.kind` 分派 |
| 編排改動 | 重寫：`gen_fight` 的時間軸是 `left_timeline`/`right_timeline` 兩條，ARC 六階段、壓制、追逼、鏡像錯開全部假設一對一 | 小：多一種時間軸動作 `swap_weapon:<kind>` |
| 鏡頭 | 重做：fit-zoom 只算兩人的水平跨度 | 不動 |
| 勝負判定 | 重做：`KO` 狀態 = 任一方倒下；混鬥要「最後一人」 | 不動 |
| 驗證工具 | `check_pacing` / `check_arc` / `sim_render` 全部假設兩條血條 | 不動 |
| 對已發布 21 支的風險 | 高（碰到共用路徑就要回歸驗證） | 低（新動作不存在於舊腳本，等於沒用到） |
| 估計 | **5-8 個工作天**，且第一週沒有新素材進來 | **1-2 個工作天** |

**建議：先做附屬武器，大混鬥當第三個月的題目。** 理由不是大混鬥不好，是它會讓一週沒有產出，而第二個月正好要從一天一支加碼到一天兩支 — 那是最不能斷更的時候。

## 附屬武器：具體設計

### 它在觀眾眼裡是什麼

打到一半，角色把手上的東西一扔，換一把。畫面上有招式字卡「WEAPON SWAP!」，音效換一組（鐵棍變刀就該有金屬聲），之後的攻擊動畫和特效跟著換。這是**在同一場 53 秒裡製造第二個轉折**，跟逆轉弧疊起來：落後 → 換武器 → 反撲。

### 為什麼便宜

`pixel_battle/rl/weapons.py` 的 `_WEAPONS` 是 `char_id → Weapon(kind, length, grip, width)` 的靜態表；`get_weapon(char_id)` 查它；`draw_weapon` 按 `weapon.kind` 走不同繪製分支（greatsword / katana / pistols …）。也就是說**渲染層已經支援所有武器種類**，缺的只是「同一個角色在時間 T 之後查到不同的武器」。

音效路由 `_route_audio_for_events` 用 `_weapon_kind(ev.actor)` 決定命中／揮擊音 — 也是按角色 id 查表。改成「按角色 id **與時間**查表」即可。

### 要動的地方

1. **時間軸動作**：`script/loader.py` 的動作表加 `swap_weapon:<kind>`（一個新 id）。`timeline_driver` 遇到它時記錄 `(actor, t_ms, kind)` 到 battle 的事件流，型別 `WEAPON_SWAP`。
2. **渲染查表**：`weapons.get_weapon(char_id, t_ms=None)` 加一個可選的覆寫層 — battle 事件流裡最近一次 `WEAPON_SWAP` 決定當前武器。`play.py` 呼叫處改傳時間。
3. **音效路由**：`_weapon_kind(actor, video_ms)` 同樣看覆寫層。
4. **編排**：`gen_fight` 的 ARC 第三階段（反撲）開頭插一個 `swap_weapon`。哪些角色能換、換成什麼，寫在 `characters.json` 的 `secondary_weapon` 欄位；沒寫的角色不換。
5. **字卡**：既有的 `spawn_skill_banner` 直接用，文字 `WEAPON SWAP!`。
6. **迷因層**：`cue_plan` 加一個 `swap` 節點，配鐵棍聲（換武器掉在地上，語意剛好）。

### 不要做的

- 不改傷害數值。換武器是**視覺與聲音**的轉折，不是平衡改動 — 改傷害會讓 `measure()` 的 HP 調校、逆轉弧、勝負全部重跑，而且觀眾看不出來。
- 不做「撿地上的武器」。那需要地圖物件與位置感知，是大混鬥級的改動。

### 驗證

`tools/hires_verify.py` 的 `compare_events` 對舊腳本必須零差異（新動作不出現在舊腳本裡）；新腳本渲一支目視換武器的瞬間；`check_pacing` / `check_arc` 不受影響（傷害沒變）。

## 大混鬥：如果真的要做

最小可行版本是 **3 人自由混戰、最後一人站著的贏**。要動：

- `engine/battle.py`：`Battle` 從 `(left, right)` 改成 `fighters: list`，事件的 `actor`/`target` 已經是 id 所以不用改，但 `_end_ko` 的「任一方倒下即結束」改成「剩一人」。
- `rl/env.py`：動作的 `opp` 從固定對手改成「目標」— 混鬥需要**目標選擇**，這是全新的邏輯（最近的？血最少的？）。
- `rl/hud.py`：三條血條的版面。
- `rl/play.py`：80 處 `.left`/`.right`；鏡頭改成 fit-all；KO 戲劇迴圈要處理「倒下一人但戰鬥繼續」。
- `gen_fight.py`：ARC、壓制、追逼、鏡像全部是一對一概念，要重新設計「誰壓制誰」。
- `check_pacing` / `check_arc` / `sim_render` / `plan_posting`（勝方側）：全部改。

第三個月做，而且要先跑一次 brainstorming 把規則談清楚：幾個人、怎麼決定目標、53 秒怎麼分配、封面怎麼呈現三個人。這些決定會影響編排器怎麼寫，不該由我單方面定。

## 順帶：這次批次二暴露的三件事，跟新玩法有關

1. **遠程對遠程不能看**（10/10 停滯），已在 `extend_batch` 否決。大混鬥如果三個都是遠程會更慘 — 選角規則要帶進去。
2. **後退無上限會走進牆裡**，已在 `env.py` 加 `MAX_SEPARATION = 260`。混鬥的走位更複雜，這條規則是前提。
3. **cyclone 和 yasuo 的套路跟其他人不同**（旋轉擊飛、閃現距離不夠）。加新玩法之前，這種「角色級的異常」要先有工具能自動抓 — `check_pacing` 按角色聚合失敗率是下一步。
