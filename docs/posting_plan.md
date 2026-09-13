# pixel_battle 發布排程（21 支）

由 `tools/plan_posting.py` 產生，固定種子、可重現。改動排程請改工具不要改本檔。

## 為什麼需要排程

TikTok 有文件依據的執法訊號是**內容**不是頻率，原文是 `Using automation to run many accounts or send repetitive content`。21 支同格式對戰片本身就落在這個語意射程內，所以相鄰兩支必須在勝方所在畫面側、場地、對戰型態、文案開場結構四個維度上都不同。

原本 21 支**全部左方獲勝**，且結局一律贏家 40 血、輸家 0 血。這已於 commit 9c262f5 修正為 11 左 10 右。

## 排程

| # | 影片 | 對戰 | 勝方 | 側 | 場地 | 開場結構 | 標籤組 |
|---|------|------|------|----|----|----------|--------|
| 1 | `b01_lumen_jugg` | Lumen vs Juggernaut | Lumen | 左 | 霜原 | 問句開場 | #火柴人 #格鬥 #誰會贏 #stickman |
| 2 | `b14_bulwark_shade` | Bulwark vs Shade | Shade | 右 | 道場 | 反直覺開場 | #火柴人動畫 #對戰 #像素 #stickfight |
| 3 | `b06_pyre_wrecker` | Pyre vs Wrecker | Pyre | 左 | 熔岩 | 角色聚焦 | #火柴人 #一對一 #動畫 #animation |
| 4 | `b15_cyclone_ironfist` | Cyclone vs Ironfist | Cyclone | 左 | 遺跡 | 場地開場 | #火柴人 #格鬥 #誰會贏 #stickman |
| 5 | `b04_deadeye_bulwark` | Deadeye vs Bulwark | Deadeye | 左 | 霜原 | 賽況開場 | #火柴人動畫 #對戰 #像素 #stickfight |
| 6 | `b19_necro_ironfist` | Necro vs Ironfist | Ironfist | 右 | 遺跡 | 挑釁開場 | #火柴人 #一對一 #動畫 #animation |
| 7 | `b13_skylance_lumen` | Skylance vs Lumen | Skylance | 左 | 霜原 | 問句開場 | #火柴人 #格鬥 #誰會贏 #stickman |
| 8 | `b08_outlaw_skylance` | Outlaw vs Skylance | Skylance | 右 | 道場 | 反直覺開場 | #火柴人動畫 #對戰 #像素 #stickfight |
| 9 | `b20_totem_wrecker` | Totem vs Wrecker | Totem | 左 | 暮色 | 角色聚焦 | #火柴人 #一對一 #動畫 #animation |
| 10 | `b18_cleaver_warlock` | Cleaver vs Warlock | Warlock | 右 | 道場 | 場地開場 | #火柴人 #格鬥 #誰會贏 #stickman |
| 11 | `b03_frostbow_cleaver` | Frostbow vs Cleaver | Cleaver | 右 | 霜原 | 賽況開場 | #火柴人動畫 #對戰 #像素 #stickfight |
| 12 | `b02_wildfire_vanguard` | Wildfire vs Vanguard | Wildfire | 左 | 暮色 | 挑釁開場 | #火柴人 #一對一 #動畫 #animation |
| 13 | `b17_warlock_vanguard` | Warlock vs Vanguard | Warlock | 左 | 遺跡 | 問句開場 | #火柴人 #格鬥 #誰會贏 #stickman |
| 14 | `b09_jugg_outlaw` | Juggernaut vs Outlaw | Outlaw | 右 | 熔岩 | 反直覺開場 | #火柴人動畫 #對戰 #像素 #stickfight |
| 15 | `b12_shade_deadeye` | Shade vs Deadeye | Deadeye | 右 | 霜原 | 角色聚焦 | #火柴人 #一對一 #動畫 #animation |
| 16 | `b10_vanguard_wildfire` | Vanguard vs Wildfire | Vanguard | 左 | 熔岩 | 場地開場 | #火柴人 #格鬥 #誰會贏 #stickman |
| 17 | `b07_venom_reaver` | Venom vs Reaver | Venom | 左 | 暮色 | 賽況開場 | #火柴人動畫 #對戰 #像素 #stickfight |
| 18 | `b11_ronin_cleaver` | Ronin vs Cleaver | Ronin | 左 | 道場 | 挑釁開場 | #火柴人 #一對一 #動畫 #animation |
| 19 | `b16_wrecker_venom` | Wrecker vs Venom | Venom | 右 | 熔岩 | 問句開場 | #火柴人 #格鬥 #誰會贏 #stickman |
| 20 | `b05_quarrel_ironfist` | Quarrel vs Ironfist | Ironfist | 右 | 道場 | 反直覺開場 | #火柴人動畫 #對戰 #像素 #stickfight |
| 21 | `b21_forge_reaver` | Forge vs Reaver | Reaver | 右 | 熔岩 | 角色聚焦 | #火柴人 #一對一 #動畫 #animation |

勝方側序列 `LRLLLRLRLRRLLRRLLLRRR` — 最長連莊 3，每 8 支窗口維持 3 比 5 以內平衡，無固定週期。

## 六種開場結構

相鄰兩支永不重複，每六支輪一輪。

- **問句** — 直接問誰會贏，收留言
- **反直覺** — 點出誰看起來會輸
- **角色聚焦** — 從勝方的招式切入
- **場地** — 從場景寫起
- **賽況** — 強調最後一招才分勝負
- **挑釁** — 對留言區的預測下戰帖

## 節奏

- 前 2 到 3 週：一週 2 到 3 支，不要每天發，不要固定時段。
- 手動上傳。帳號有 30 天以上歷史後才考慮 TikTok Studio 原生排程器。
- 每支封面已是 per-fight 的 VS 縮圖，不要改用統一模板。

## 未決

- **品牌名未定**，所以逐支文案還沒寫。名字定案後依上表的開場結構與標籤組補齊。
- 帳號 handle 目前是本名 `@chuanlungchien`，建議發文前改掉。
- 配樂為 Kevin MacLeod〈Crusade〉，文案需保留 CC-BY 標註行。
