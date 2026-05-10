---
title: BingX API FAQ
source: BingX Official API Documentation
languages: zh-TW, en
updated: 2026-05-08
---

# BingX API FAQ

> This document pairs each question and answer in both Chinese (zh-TW) and English (en).
> Each entry is self-contained for use in RAG / semantic search / AI context injection.

## FAQ-01

**Q (zh-TW):** Q：BingX的伺服器在哪裡？

**A (zh-TW):**

BingX 目前部署於 AWS 新加坡區域（ap-southeast-1），伺服器使用多個可用區域（Availability Zones），包括可用區域 ID：apse1-az1、apse1-az2、apse1-az3，以確保高可用性與穩定性。

**Q (en):** Q: Where are BingX servers located?

**A (en):**

BingX is hosted on AWS in the Singapore region (ap-southeast-1), utilizing multiple Availability Zones, including Availability Zone IDs: apse1-az1, apse1-az2, and apse1-az3 to ensure high availability and stability.

---

## FAQ-02

**Q (zh-TW):** Q：什麼是UID?

**A (zh-TW):**

UID是用戶ID，是標示每個用戶的唯一ID（包括母用戶和子用戶），UID可以在Web或App界面的個人信息裡查看到，也可以通過接口GET /openApi/account/v1/uid獲得。

**Q (en):** Q: What is UID?

**A (en):**

UID stands for User ID, which is a unique identifier for each user (including parent users and sub-users). UID can be viewed in the personal information section of the web or app interface, and it can also be obtained through the GET /openApi/account/v1/uid interface.

---

## FAQ-03

**Q (zh-TW):** Q：一個用戶可以申請多少個API Key？

**A (zh-TW):**

每個母用戶可創建20組API Key，每個母用戶還可創建20個子用戶，每個子用戶可創建20組API Key，每個API Key可設置不同權限。

**Q (en):** Q: How many API Keys can a user apply for?

**A (en):**

Each parent user can create up to 20 sets of API Keys. Each parent user can also create up to 20 sub-users, and each sub-user can create up to 20 sets of API Keys. Each API Key can be set with different permissions.

---

## FAQ-04

**Q (zh-TW):** Q：為什麼經常出現斷線、超時的情況？

**A (zh-TW):**

有可能網絡抖動問題，建議重連。

**Q (en):** Q: Why do I often experience disconnections and timeouts?

**A (en):**

It could be due to network fluctuations. We recommend reconnecting in such cases.

---

## FAQ-05

**Q (zh-TW):** Q：為什麼WebSocket總是斷開連接?

**A (zh-TW):**

可檢查一下你的代碼是否在收到Ping後返回Pong，如果是賬戶相關websocket訂閱，請再檢查一下是否定期更新listenkey，建議先使用我們的示例代碼。

**Q (en):** Q: Why does WebSocket connection always get disconnected?

**A (en):**

You can check if your code returns a Pong after receiving a Ping. If you are subscribing to account-related websockets, please also check if you are regularly updating the listenkey. We recommend using our sample code first.

---

## FAQ-06

**Q (zh-TW):** Q：為什麼簽名認證總返回失敗?

**A (zh-TW):**

請先仔細閱讀我們的簽名說明，或先使用我們的示例代碼進行測試。

**Q (en):** Q: Why does signature authentication always fail?

**A (en):**

Please carefully read our signature authentication instructions, or test using our sample code first.

---

## FAQ-07

**Q (zh-TW):** Q：U本位合約API Key和現貨是否同一個?

**A (zh-TW):**

U本位合約API Key和現貨API Key是同一個，兩個是一樣的。由於現貨交易和合約交易權限是分開的，需要配置好對應的權限。

**Q (en):** Q: Is the API Key for U-based contracts the same as Spot trading?

**A (en):**

The API Key for U-based contracts is the same as the API Key for Spot trading. However, the permissions for spot trading and contract trading are separate and need to be configured accordingly.

---

## FAQ-08

**Q (zh-TW):** Q：BingX對API有多少種風控限制?

**A (zh-TW):**

BingX有接口限頻、交易限制、網絡防火牆限制三種風控策略，這些限制可能會隨時變更。

接口限頻：每個接口限頻不一樣，請參考具體的接口文檔說明。

交易限制：交易行為是根據普通用戶的交易行為進行評估，如果您的交易行為與普通用戶的行為偏離較遠，可能會被禁止交易，禁止時長不定。假設出現以下狀況時您的禁止交易時長會增加：

1. 總是頻繁占據買一賣一價；

2. 頻繁掛單/撤單，且沒有任何成交；

3. 成交率非常低，成交率=交易筆數/（掛單筆數+撤銷筆數）；

4. 成交權重非常低，成交權重=交易總額/（掛單總額+撤銷總額）；

5. 接口報429後依然頻繁請求。

網絡防火牆限制：目前我們沒有提供關於網絡防火牆限制的明確信息，如果您收到了HTTP403錯誤提示，這說明您違反了一條網絡防火牆的規則，大多數情況下出現這個錯誤提示是因為過多的請求並且會持續禁止五分鐘，但是如果您發送的請求被判定為惡意請求，那麼它也可能導致持續禁止更長的時間甚至永久禁號。

**Q (en):** Q: How many types of risk control restrictions does BingX have for APIs?

**A (en):**

BingX has three types of risk control strategies for APIs: api rate limiting, trading restrictions, and network firewall restrictions. These restrictions may change at any time.

Interface rate limiting: The rate limiting for each api may vary. Please refer to the specific api documentation for details.

Trading restrictions: Trading behavior is evaluated based on the behavior of regular users. If your trading behavior deviates significantly from that of regular users, you may be prohibited from trading, and the duration of the prohibition is uncertain. The duration of the trading prohibition may increase under the following circumstances:

1. Frequently occupying the best bid and ask prices.

2. Frequently placing/canceling orders without any trades.

3. Very low trade completion rate, where the completion rate = number of trades / (number of placed orders + number of canceled orders).

4. Very low trade weight, where the trade weight = total trade amount / (total placed order amount + total canceled order amount).

5. Continuously sending frequent requests after receiving a 429 error response.

Network Firewall Restrictions: Currently, we do not provide explicit information about network firewall restrictions. If you receive an HTTP 403 error message, it means you have violated a network firewall rule. In most cases, this error occurs due to excessive requests and will result in a five-minute temporary ban. However, if your requests are considered malicious, it may lead to a longer ban or even permanent suspension.

---

## FAQ-09

**Q (zh-TW):** Q：遇到API接口錯誤該如何反饋？

**A (zh-TW):**

請聯繫官方客服並按照如下模板向我們反饋問題，會有技術支持技術解答。

1. 問題描述。

2. 問題發生的用戶Id(UID)和訂單Id(如果和賬戶、訂單有關係)、API KEY。

3. 完整的請求參數（如果有）。

4. 完整的JSON格式的返回結果。

5. 問題出現時間和頻率（如何時開始出現，是否可以重現）。

6. 簽名信息。

**Q (en):** Q: How to report API errors?

**A (en):**

Please contact our official customer service and provide the following template to report the issue. Our technical support will assist you:

1. Problem description.

2. User ID (UID) and order ID (if related to account or order), API KEY.

3. Complete request parameters (if applicable).

4. Complete JSON formatted response.

5. Time and frequency of the issue (when it started, if it can be reproduced).

6. Signature information.

---

## FAQ-10

**Q (zh-TW):** Q：API支持標準合約交易嗎？

**A (zh-TW):**

當前不支持。

**Q (en):** Q: Does the API support standard contract trading?

**A (en):**

Currently not supported.

---

## FAQ-11

**Q (zh-TW):** Q：API支持股票、外匯、商品、股票指數等TradFi或非數字貨幣幣對交易嗎？

**A (zh-TW):**

支持。

**Q (en):** Q: Does the API support stocks, forex, commodities, stock indices, and other TradFi or non-crypto perpetual pairs?

**A (en):**

Supported.

---

## FAQ-12

**Q (zh-TW):** Q：手機端支持API Key的管理嗎？

**A (zh-TW):**

支持。

**Q (en):** Q: Does the mobile app support API Key management?

**A (en):**

Supported.

---

## FAQ-13

**Q (zh-TW):** Q：BingX單IP可以訂閱的頻道數量？

**A (zh-TW):**

當前沒有限制，但是有訂閱頻率限制，請不要超過10/s。

**Q (en):** Q: How many channels can be subscribed per IP address on BingX?

**A (en):**

Currently, there is no limit, but there is a subscription rate limit. Please do not exceed 10/s.

---
