# TikTok + FB Reels 發布手冊（2026-07-06 查證版）

來源：官方頁面逐條查證（Meta Business Help / TikTok Support / Transparency Center），
第三方說法均已標注。完整查證紀錄見 memory `project_pivot_tiktok_fb`。

## 角色分工（先想清楚再發）

- **Facebook Reels = 變現主力**。台灣 + 中文在 Meta 官方 Content Monetization
  名單內（官方頁面已驗證）。但新制是**邀請制** —— 第一步是填官方 interest form 排隊：
  https://creators.facebook.com/content-monetization-interest-form
- **TikTok = 導流與養觀眾，不是收入**。Creator Rewards 台灣不適用（無官方開放跡象）；
  台灣唯一官方變現是直播/影片禮物（10k 粉絲門檻）。短期內別指望 TikTok 收錢。

## True crime 的變現現實（Meta 官方明文）

「Tragedy or conflict」與「Objectionable activity（明列 judicial proceedings 司法程序）」
屬於**受限變現類別** —— 即使進了分潤，RPM 會被壓。官方豁免方向：「explicitly uplifting」。

→ 腳本策略：**記錄／制度反思／正向收尾**的框架，不是獵奇框架。我們的「案件反思」
section 本來就有，之後把它加重（等真的拿到邀請再調 prompt，現在不動）。

## AI 標注：不是選項

兩平台都已部署 C2PA 自動偵測 —— 主流 AI 工具的產出會被**自動**貼 AI 標籤，藏不住。
- 發布時**主動開 AIGC/AI Info 標記**（官方明言標記不影響觸及）
- 文案內建揭露聲明（export_reel.py 已做）
- 真正會死的不是 AI 標籤，是被歸類「unoriginal / mass-produced」——
  Meta 2025-07 才為此懲處 50 萬帳號

## 冷啟動鐵則（YT 的教訓 + 兩平台官方紅線）

Meta 官方 spam 政策原文重點：**有重複性內容訊號時，低頻率也會被罰**。
「模板感 + 規律排程」的組合就是偵測特徵。

1. 前 2-3 週：**每日 ≤1 支**，發布時間不要規律（不同時段手動發）
2. **絕不用自動化上傳**（TikTok 官方明文禁 bulk-posting 工具）
3. 素材**去掉一切浮水印**（TikTok 用音訊指紋+視覺偵測抓搬運，直接壓觸及）
4. 每支影片的封面、文案開頭、結構要有可辨識差異 —— 減「工廠感」
5. 帳號用**真實資料**註冊（生日、姓名）；不開多帳號互推
6. TikTok 前 3-5 支發「絕對安全」的內容養帳號；不要用 #fyp 濫用 tag
7. TikTok 計酬（若未來開放）要求影片 >1 分鐘 —— crime reel 規格維持 60-90 秒正好

## 內容分級注意

- TikTok：無血腥畫面的敘述型 true crime 可進推薦；驚悚音效、屍體/傷口畫面會被
  排除出 For You feed
- Meta：敘述型（無畫面）不觸發暴力內容警告；避免真實暴力畫面素材

## arlong 待辦

- [ ] 開 TikTok 帳號（真實資料）+ FB 粉專或個人 Professional Mode
- [ ] 填 FB Content Monetization interest form（上面連結）
- [ ] 品牌名定案後告訴 Claude，補進文案模板
