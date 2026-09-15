# TikTok 自動上傳與帳號數量 — 查證報告（2026-09-11）

研究方法：5 個獨立角度並行檢索 → 每條主張由兩種對抗式鏡頭（來源真實性 / 過度延伸與過時）
獨立反駁 → 完整性批判補洞 → 綜合。共 71 個 agent、1385 次工具呼叫。所有 URL 已 curl 實測 200。

本報告更新 `docs/pivot_playbook.md` 的 TikTok 章節。

---

## 一、能不能綁自動上傳

**結論：官方 API 這條路對你的用途是書面違規，且過不了審核。合法的自動發佈只能透過已通過審核的第三方排程商，或 TikTok 自家的原生排程器。**

TikTok 的 Content Posting API 仍在維護，有兩種模式：
- Direct Post（scope `video.publish`）— 直接發佈
- Upload（scope `video.upload`）— 丟進創作者收件匣變草稿，人要自己進 app 完成

擋住自建 client 的是兩條明文規則：

1. App Review Guidelines：`Apps must not be for private or personal use`，且
   `Apps that are still in development or testing will not be approved`。
   https://developers.tiktok.com/doc/app-review-guidelines/

2. Content Sharing Guidelines 把這個用途逐字列為不可接受：
   `Not acceptable: A utility tool to help upload contents to the account(s) you or your team manages.`
   並要求 `API Clients must not be limited to test applications and should be intended for a
   wide audience, not limited to internal groups/private use.`
   https://developers.tiktok.com/doc/content-sharing-guidelines/

**常見誤解澄清：不需要註冊公司。** 組織身分是 highly recommended but not required。
擋住你的是「不能私人/個人用途」與「不能是給自己帳號用的上傳工具」。

未過審的 client：Direct Post 被強制 SELF_ONLY，且發文帳號本身必須設為私人，否則回 403
`unaudited_client_can_only_post_to_private_accounts`；同一 client 24 小時最多 5 個使用者。
https://developers.tiktok.com/doc/content-posting-api-reference-direct-post/

**警告：誠實送審被拒是低風險的正常結果；為過審而謊報用途才是高風險。**
Developer Guidelines 寫明違規
`will likely lead to immediate revocation of your integration and a permanent ban on all
future integrations by your account and business entity`。
https://developers.tiktok.com/doc/our-guidelines-developer-guidelines/

---

## 二、一人最多 3 個帳號？—— 這個記憶是錯的

**政策面完全沒有數字上限。** 美國版 ToS、其他地區版 ToS、現行與 2026-09-24 生效的新版
Community Guidelines 全文搜尋「up to N accounts」類模式，零命中。指引反而明文允許：
`You can have multiple accounts—for example, for fan content or creative expression—but
not to deceive others or break the rules.`
https://www.tiktok.com/safety/en/policies-and-engagement/integrity-authenticity

**「3」這個數字查不到任何 TikTok 一手來源（標記未證實）。** 已查說明中心登入/帳號文章、
Wayback 快照與 CDX 全索引、兩版 Community Guidelines、兩版 ToS。TikTok 自己只寫
`You can add additional accounts to your device and switch between them on TikTok.`，沒有數字。
流傳的 3 / 5 / 6 互相矛盾，出處全是賣多帳號工具或 antidetect 瀏覽器的廠商部落格。

**真正的天花板是識別碼：** 一個 email 只能綁一個帳號，一個手機號碼只能綁一個，
一個社群登入帳號也只能綁一個。刪除帳號後 30 天永久清除才能重用識別碼。
https://www.tiktok.com/support/faq_detail?id=7581820709597583928

**連坐條款剛變嚴：** 2026-09-24 生效版把 `we may ban all of their accounts` 改成
`we may ban all of their accounts, including associated accounts`。TikTok **從未定義**
什麼叫 associated——該詞在整份 2026 版指引只出現這一次，沒有任何文件提到裝置、IP 或
付款方式會被用來串連帳號。任何「TikTok 用裝置指紋連坐」的說法查無一手來源。
https://www.tiktok.com/safety/en/policies-and-engagement/accounts-features?cgversion=2026H2update

---

## 二之二、username 規則（2026-09-15 以 firecrawl 補查，官方原文）

前一版把改名限制標為「查無一手來源」，那是**工具用錯**不是真的查不到：
WebFetch 對 TikTok 說明中心（SPA）只拿到空殼，改用 `firecrawl scrape` 一次就取得正文。

https://www.tiktok.com/support/faq_detail?id=7581821550156962315

- `Your username can be changed once every 30 days.` — **30 天限制是官方明文的。**
- `If you give up your username, you will not be able to add that username to an
  account for a short period of time.` 放掉的名字短期內不能綁回。
- `Changing your username will also change your profile link.`
- 長度 2 到 24 字元，只能用字母、數字、底線、句點，句點不能結尾。
- 已被他人使用、或被停權/停用帳號佔用的名字不能選，且不會立即釋出。

**操作後果：** 連續改兩次會被擋。規劃 handle 要一次到位。

---

## 三、三條路的風險完全不同

| 路徑 | 合規狀態 | 風險 |
|---|---|---|
| 自建 client 接 Content Posting API | 對此用途明文違規，過不了 app review | 高（謊報用途 = 永久封鎖所有未來整合） |
| TikTok 原生排程器（TikTok Studio） | 完全合規，是 TikTok 自家產品 | 與手動上傳等價 |
| 未授權第三方自動化（腳本、多帳號工具、antidetect） | 明文禁止 | 最高 |

**原生排程器不需要 Business 帳號（更正常見誤解）。** TikTok 現行說明頁把
「Upload, schedule, and edit posts」列在 creator tools，並寫
`Creator tools are available for both Personal and Business Accounts.`
https://www.tiktok.com/support/faq_detail?id=7581820704895703564

（「Creator 帳號」這個類型已不存在，現在只有 General/Personal、Verified Business、
Organization 三種。叫你「切換到 Creator 帳號」的教學都是過時的。）

窗口 15 分鐘到 10 天，排定後不能編輯，要改只能刪掉重上。

**台灣適用 Rest-of-World 版 ToS，是三個地區版本裡最嚴的：** 在「You may not:」清單直接寫
`use automated scripts to collect information from or otherwise interact with the Services`，
沒有寫 API 例外。美國版與 EEA 版後來改窄很多（只禁自動化擷取，不禁自動發佈）。
**任何引用美國版 ToS 的討論都會低估你的風險。**
https://www.tiktok.com/legal/page/row/terms-of-service/en

---

## 四、「怎麼發」vs「發什麼」——證據強度不對稱

- **「發什麼」有白紙黑字的政策。** 成文的 unoriginal content 定義（重複使用、輕度修改、
  投影片、純文字疊加會被取消貨幣化，已付獎勵追回）；2026 年 7 月宣布測試帳號層級偵測
  「accounts dedicated to posting AI-generated spam」，但範圍限定政治、理財建議、醫療三主題。

- **「怎麼發」查不到任何案例。** 特地搜尋 2025-2026「因使用官方 API 或合作夥伴排程器本身
  而被處分」的具名報導或一手來源，**一件都沒有**。所有這類說法追溯回去都是無一手出處的
  SEO 部落格。注意這是「查不到」不是「證明沒有」。

**兩個反直覺發現：**
1. **找不到任何 TikTok 政策把「AI 生成」本身視為不原創。** Originality Policy 四個分類
   全部關於抄襲或重製他人作品。AIGC 規則是另一回事（標示與誤導性描繪）。
2. **TikTok 從未公布任何數字門檻** — 一天幾則算 spam、多短算 extremely short、改多少算
   creative edit，全是裁量。`schedul` 在 Community Guidelines 全文出現零次。

---

## 五、YouTube 前科會被牽連嗎

**依目前公布的規則：不會。但論證基礎在 9/24 之後變弱。**

- ban evasion 規則全綁在「另一個你擁有的 **TikTok** 帳號」的既有處分：
  `we may restrict or permanently ban your account if you make any attempts to avoid a
  restriction or ban imposed on another account you own`。沒有任何條款納入別家平台處分。
  https://support.tiktok.com/en/safety-hc/account-and-user-safety/content-violations-and-bans

- 現行版 off-platform 條款列舉四項：暴力/仇恨組織成員、性侵、嚴重暴力犯罪、人口販運。
  YouTube 的 spam 終止不在內。

- **但新版把整段列舉刪掉，沒有東西取代。** 新版只剩
  `We may also restrict or ban accounts belonging to people who have engaged in egregious
  off-platform behaviors, when we have sufficient evidence to support enforcement.`
  `egregious` 在整份 2026 版只出現這一次，從未定義。TikTok 沒發任何說明為何刪除。

- 結論不變但理由要改寫：現在靠的是「緊鄰上方的 severe violations 清單所設定的嚴重度語境」
  推論 YouTube spam 終止不構成 egregious。**這是推論，不是條文。**

- **例外：** Creator Code of Conduct（2026-09-10 更新）明文適用 `on and off-platform`
  且點名 spam 與 deceptive behaviors。但它管的是 Creator Program / 貨幣化參與資格
  （文件自稱 `a privilege, not a right`），不是發文權，處分是三個月 program 限制。
  其列舉的證據類型不包含另一家平台的 TOS 執法決定。
  https://www.tiktok.com/creator-academy/en/article/creator-code-of-conduct

---

## 六、對 21 支成品的具體建議

**技術上做得到（透過已審核第三方排程商），但不該做。** 理由不是規則禁止，而是：

1. 你的守則方向對，理由跟你寫的不一樣。你寫「API mass upload IS the spam signal」，
   證據顯示驅動執法的是內容不是管道。但對「零歷史 + 有前科 + 21 支同系列」的新帳號，
   這個分辨幫不上忙：你要的是不製造任何需要人工判斷的模糊訊號。
2. 21 支火柴人打鬥落在 `Using automation to run many accounts or send repetitive content`
   的語意射程內。系列化本身不是問題，**同封面模板、同標題結構、固定間隔倒出去才是**。
3. 省下的時間很少。一支手動 3-5 分鐘，21 支不到兩小時，低於任何排程管線的建置成本。

### 第一階段（前 2-3 週，第 1-8 支）
- 純手動，TikTok app 內上傳。不碰 API、不碰第三方工具、不排程。
- 一週 2-3 支，不要每天發，不要固定時間。
- 每支標題、封面、hashtag 做出差異，不要套模板。per-fight VS 縮圖是好起點。
- 影片若有 AI 生成成分，主動開 AI-generated content 標示。上次是被判 deceptive practices，
  主動標示是成本最低的保險。
- 全新 email + 全新手機號碼（識別碼一對一規則讓你沒有選擇）。
- **只開一個帳號。** 9/24 後連坐條款寫進 associated accounts 且無定義，多開是擴大風險面。

### 第二階段（帳號 30 天以上歷史、有自然流量後）
- 要減少手動負擔，**用 TikTok 自家原生排程器**（tiktok.com 網頁版 → TikTok Studio）。
  這是唯一無保留推薦的自動化：不經第三方、不涉 API 憑證、不需審核，風險與手動等價。
- 缺點：排定後不能編輯；隊列深度無官方數字（流傳的「只能排 10 則」未證實）。

### 第三階段（帳號健康運作數月、真要規模化時）
- 才考慮第三方排程商（Buffer / Later / Metricool / Publer / Hootsuite），五家都是真自動發佈。
  使用原生音樂、特效、貼紙或超長影片時全部退回手動通知模式。
- 成本：Buffer 最便宜（免費方案含 API）；Publer API 需 Business 約 $10/月；
  Later 最低 $18.75/月；Hootsuite $99/月起（單頻道個人創作者不划算）。
- **Buffer 有兩個必須先測的未驗證問題**（來源是 Buffer 自家建議板使用者貼文，非官方文件）：
  (a) 可能只支援 PULL_FROM_URL 傳影片，那需要你的網域在 TikTok 開發者後台驗證過；
  (b) 發佈流程可能沒有暴露 AI 內容標示開關。第二點對你特別重要，發一支實測再決定。
- **無法驗證**五家是否接受台灣帳單地址或台幣卡。定價頁沒寫國別限制，但不等於確認可用。

### 絕對不要做
- 不要自己寫 client 接 Content Posting API（過不了 app review，沒有例外）。
- 不要為過審而謊報 app 用途（唯一明文導致永久封鎖所有未來整合的動作）。
- 不要用 antidetect 瀏覽器或多帳號管理工具（ToW 版 ToS 與 Community Guidelines 同時直接禁止）。

---

## 七、明確標記為未證實 / 無法查證

- 帳號切換器「3 個」上限：查無 TikTok 一手來源，三個流傳數字互相矛盾。
  （注意：**username 30 天改名限制原本也列在此處，已於 2026-09-15 用 firecrawl
  取得官方原文證實**，見第二之二節。凡是 WebFetch 回空殼的頁面，先改用 firecrawl
  再下「無法證實」的結論。）
- Upload/收件匣模式是否豁免 unaudited 限制：從文件缺席推論，非明文豁免，且 TikTok 文件內部不一致。
- Buffer 的影片傳輸方式與 AI 標示開關：使用者回報，非官方文件。
- 五家排程商的台灣可付款性：未驗證。
- Hootsuite 說的「TikTok 每天上限 15 則」：廠商數字，TikTok 從未公布。
- 「排程會降觸及」或「不影響觸及」：TikTok 兩邊都沒說過，說法皆來自有商業利益的來源。
- 一天發幾則會被判 spam：無任何一手來源的數字門檻。
- 「TikTok 用裝置指紋 / IP / 付款方式串連 associated accounts」：查無一手來源。

註：developers.tiktok.com/doc/* 對 HEAD 回 404、對 GET 回 200，那是 SPA 行為不是死連結。
