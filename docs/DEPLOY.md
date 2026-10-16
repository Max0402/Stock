# 🌐 部署成真正的網站

完成後你會有一個像 `https://stock-tracker-xxxx.onrender.com` 的網址，手機、電腦打開就能用，不用再開終端機。

## 架構

```
瀏覽器 ──HTTPS──▶ Render（免費主機）──────────▶ Neon（免費 PostgreSQL）
                 │ 一個 Docker 容器：            存持股、追蹤清單、新聞
                 │  · FastAPI 提供 /api/*
                 │  · 同時提供前端網頁（靜態檔）
                 │  · 密碼保護（APP_PASSWORD）
                 ▲
GitHub Actions ──┘ 每小時呼叫一次，更新新聞與訊號
```

| 角色 | 服務 | 為什麼需要 |
| --- | --- | --- |
| 網站主機 | **Render**（也可以用 Railway、Fly.io，或任何能跑 Docker 的主機） | 執行 App |
| 資料庫 | **Neon** 或 Supabase（PostgreSQL） | 免費主機的硬碟重開機就會清空，資料要放在外部資料庫 |
| 每小時排程 | **GitHub Actions** | 免費主機沒人用時會休眠，App 內建的排程不會跑 |

> ⚠️ 下面關於「免費方案」的描述是依照我目前的了解。這些平台的規定常常改，**註冊時請以各平台的價格頁為準**。

---

## 第 1 步：建立免費資料庫（Neon）

1. 到 <https://neon.tech> 用 GitHub 帳號註冊
2. 建立一個 Project（名稱隨意，Region 選離你近的，例如 Singapore 或 Sydney）
3. 在 Dashboard 找到 **Connection string**，複製下來，長得像：

   ```
   postgresql://neondb_owner:xxxxxxxx@ep-xxxx-xxxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
   ```

   - 直接貼這串就好，程式會自動轉成需要的格式（`postgresql+psycopg://`）。
   - 資料表不用自己建，App 第一次啟動時會自動建立。
   - 🔐 這串裡面有資料庫密碼，**不要貼到 GitHub 或公開的地方**。

<details>
<summary>改用 Supabase？</summary>

到 Project Settings → Database → Connection string，選 **Session pooler**（不要選 Direct connection，因為那個常常只支援 IPv6，很多主機連不上）。

</details>

## 第 2 步：部署到 Render

1. 到 <https://render.com> 用 GitHub 帳號登入，授權 Render 讀取 `Max0402/Stock`
2. 點 **New → Blueprint**，選 `Max0402/Stock` 這個 repo，分支選程式所在的分支
   （Render 會讀取 repo 根目錄的 [`render.yaml`](../render.yaml)，自動設定好大部分項目）
3. 它會請你填 `DATABASE_URL` → 貼上第 1 步的連線字串
4. 按 **Apply / Deploy**，第一次 build 大約要 5–10 分鐘

> 如果 Blueprint 那一步出錯，也可以手動建立：**New → Web Service** → 選這個 repo → Runtime 選 **Docker** →
> 在 Environment 裡手動加入 `DATABASE_URL`、`APP_USERNAME`、`APP_PASSWORD`、`CRON_SECRET` 這幾個變數。

## 第 3 步：登入你的網站

1. 在 Render 這個服務的 **Environment** 頁面，可以看到自動產生的 `APP_PASSWORD`（點眼睛圖示顯示）
2. 打開 Render 給你的網址（頁面上方，`https://...onrender.com`）
3. 瀏覽器會跳出登入視窗：帳號 `admin`，密碼 = `APP_PASSWORD`

🎉 完成！在手機瀏覽器打開同一個網址，選「加入主畫面」，就會像一個 App 圖示一樣。

## 第 4 步：每小時自動更新新聞（GitHub Actions）

1. 在 Render 的 Environment 頁面複製 `CRON_SECRET`
2. 到 GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**，新增兩個：

   | Name | Value |
   | --- | --- |
   | `APP_URL` | 你的網址，例如 `https://stock-tracker-xxxx.onrender.com`（結尾不要加 `/`） |
   | `CRON_SECRET` | 剛剛複製的值 |

3. 到 **Actions** 分頁 → 左邊選 **Hourly news refresh** → **Run workflow** 手動跑一次，看到綠色勾勾就成功了

設定檔在 [`.github/workflows/hourly-refresh.yml`](../.github/workflows/hourly-refresh.yml)。
（GitHub 的排程只會在 repo 的**預設分支**上執行。）

---

## 常見問題

**打開網站要等很久？**
免費主機閒置一段時間後會休眠，下一次打開需要幾十秒喚醒，之後就正常了。

**怎麼登出？**
Basic Auth 沒有登出按鈕，關掉瀏覽器就會登出（或使用無痕視窗）。

**怎麼換密碼？**
在 Render 的 Environment 修改 `APP_PASSWORD`，存檔後服務會自動重新啟動。

**有別人可以看到我的持股嗎？**
沒有密碼就只會看到「需要登入」。`/api/health`（只回傳狀態）和 `/api/jobs/refresh-news`（需要 `CRON_SECRET`）例外。

**想加 AI 摘要或 Finnhub？**
在 Render 的 Environment 新增 `ANTHROPIC_API_KEY` 或 `FINNHUB_API_KEY` 即可。

**不想用 Render？**
任何能跑 Docker 的地方都可以：

```bash
docker build -t stock-tracker .
docker run -p 8000:8000 \
  -e APP_PASSWORD='一組長的隨機密碼' \
  -e DATABASE_URL='postgresql://...' \
  -e CRON_SECRET='另一組隨機字串' \
  stock-tracker
```

---

## 🔐 這個部署做了哪些資安防護

| 防護 | 說明 | 程式 |
| --- | --- | --- |
| 密碼保護 | 所有網頁與 API 都需要 HTTP Basic Auth；`compare_digest` 防計時攻擊 | `backend/app/security.py` |
| 強制 HTTPS | 平台提供 HTTPS；回應帶 `Strict-Transport-Security`，瀏覽器之後一律走 HTTPS | 同上 |
| 安全標頭 | `X-Frame-Options: DENY`（防點擊劫持）、`nosniff`、`Referrer-Policy` | 同上 |
| 非 root 執行 | 容器以一般使用者 `appuser` 執行，就算被入侵權限也有限 | `Dockerfile` |
| 機密不進程式碼 | 密碼、資料庫連線字串都是平台上的環境變數，不在 Git 裡 | `render.yaml`（`sync: false` / `generateValue`） |
| 最小權限 | GitHub Actions workflow 設定 `permissions: {}` | `hourly-refresh.yml` |
| 密碼強度提醒 | 沒設密碼或密碼少於 12 字元，啟動時會在 log 警告 | `backend/app/main.py` |

> 進階練習：Basic Auth 適合個人使用。要開放多人註冊，就需要真正的帳號系統（例如 Supabase Auth + JWT），
> 並讓每個人只能存取自己的資料，見 `backend/app/deps.py` 的註解。
