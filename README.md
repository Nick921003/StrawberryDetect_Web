# StrawberryDetect_Web
# 草莓病蟲害辨識系統

這是一個使用 Django、YOLO (透過 Ultralytics)、PostgreSQL 和 Nginx 建構的草莓病蟲害辨識系統。系統能夠辨識如「角斑病 (angular leaf spot)」與「健康 (healthy)」的草莓葉片狀態。本文件提供兩種運行方式的說明：使用 Docker（推薦，用於部署和一致的環境）和直接在本地環境運行（用於開發）。

**重要：** 本專案預設設定使用 AWS S3 進行圖片等媒體檔案的儲存。

---

## 專案功能簡述

* **圖片上傳與辨識**：使用者可以上傳草莓葉片圖片，系統將使用 YOLO 模型進行病蟲害辨識。
* **結果展示**：顯示原始圖片、標註後的結果圖以及辨識出的類別和信心度。
* **辨識歷史**：使用者可以查看最近的辨識紀錄（系統預設保留最近10筆）。

---

## 方法一：使用 Docker 運行 (推薦)

此方法使用 Docker Compose 來建立和管理應用程式所需的服務容器（Web 應用、資料庫、反向代理）。此設定預期使用 AWS S3 儲存上傳的檔案。

### 環境需求

* **Docker:** [安裝 Docker](https://docs.docker.com/get-docker/)
* **Docker Compose:** 通常隨 Docker Desktop 一起安裝。若無，請參考 [安裝 Docker Compose](https://docs.docker.com/compose/install/)。
* **AWS S3 帳戶與憑證:** 用於儲存上傳的圖片及辨識結果圖。

### 設定與執行步驟

1.  **取得專案檔案：**
    * 透過 Git Clone：
        ```bash
        git clone <你的 Git 倉庫 URL>
        cd <專案目錄名稱>
        ```
    * 或者，確保你取得了 `docker-compose.yml`, `nginx.conf` 等必要設定檔，以及 `yolo/best.pt` 模型檔案。

2.  **準備 YOLO 模型檔案：**
    * 確保您的 YOLO 模型權重檔案 (例如 `best.pt`) 存放於專案根目錄下的 `yolo/best.pt`。此模型將被 Django 應用程式載入。

3.  **建立環境變數檔案 (`.env`)：**
    * 在專案根目錄（與 `docker-compose.yml` 同層）**手動建立**一個名為 `.env` 的檔案。
    * **產生 SECRET_KEY：** 在你的**本地開發環境**（啟用虛擬環境後）的終端機中執行以下指令來產生一個安全的隨機密鑰：
        ```bash
        python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
        ```
    * 複製以下內容到 `.env` 中，並**修改**設定值：

        ```dotenv
        # Django 設定
        # 請務必產生一個新的、隨機的 SECRET_KEY！
        SECRET_KEY='請替換成一個強隨機密鑰!例如: django-insecure-...'
        DEBUG=0 # 生產建議設為 0
        ALLOWED_HOSTS=yourdomain.com,[www.yourdomain.com](https://www.yourdomain.com),localhost # 部署時請修改為您的域名或 IP

        # PostgreSQL 資料庫設定 (需與 docker-compose.yml 中的設定一致)
        POSTGRES_DB=strawberry_db
        POSTGRES_USER=strawberry_user
        POSTGRES_PASSWORD=請設定你的資料庫密碼
        DATABASE_HOST=db # Docker Compose 服務名稱
        DATABASE_PORT=5432

        # AWS S3 設定 (用於媒體檔案儲存)
        AWS_ACCESS_KEY_ID='你的AWS Access Key ID'
        AWS_SECRET_ACCESS_KEY='你的AWS Secret Access Key'
        AWS_STORAGE_BUCKET_NAME='你的S3 Bucket名稱'
        AWS_S3_REGION_NAME='你的S3 Bucket所在區域 (例如 ap-northeast-1)'
        # AWS_S3_ENDPOINT_URL='如果使用相容S3的服務(如MinIO)，請設定此項' # 選填
        ```
    * **重要：** `.env` 包含敏感資訊，切勿提交到 Git。`.gitignore` 應包含 `.env`。
    * **AWS 詳細權限設定：** 除了上述環境變數，請參考本文件末尾的「[AWS S3 詳細設定指引 (IAM, Bucket Policy, CORS)](#aws-s3-詳細設定指引-iam-bucket-policy-cors)」章節，以完成必要的 AWS 端權限配置。

4.  **本地 `media` 目錄 (備援說明)：**
    * 此專案的 Django 設定 (`settings.py`) 預設使用 AWS S3 儲存。因此，Docker 容器內的 Web 應用會直接將檔案上傳到 S3。
    * 以下建立本地 `media` 目錄的指令主要適用於**不使用 S3 或 S3 設定失敗時的本地檔案儲存備援** (需同時調整 Django `settings.py` 中的 `STORAGES` 設定)，或者用於**本地非 Docker 開發**。
        ```bash
        # 若不使用 S3 或作為備援，可能需要這些目錄
        # mkdir -p media/temp_uploads
        # mkdir -p media/uploads
        # mkdir -p media/results
        ```
    * 如果確實需要在 Docker 容器內使用本地掛載的 `media` 目錄且遇到權限問題，才考慮執行 `chmod` (不建議生產環境對 S3 模式使用)。

5.  **取得 Docker 映像檔：**
    * **推薦方式：從 Docker Hub 拉取預建映像檔。**
        ```bash
        docker pull nick45320639/strawberrydetect:latest
        ```
        *(Docker Compose 在 `up` 時如果本地找不到也會嘗試拉取，但手動拉取可以確認下載成功)*
    * **替代方式：在本地建構映像檔。** 如果你想自行修改 `Dockerfile` 或基於最新程式碼建構 (請確保 `yolo/best.pt` 模型已存在於專案中，`Dockerfile` 應包含複製此模型的步驟)：
        ```bash
        docker-compose build web
        ```

6.  **啟動應用程式容器：**
    * 在專案根目錄的終端機中執行：
        ```bash
        docker-compose up -d
        ```
    * `-d` 參數讓容器在背景執行。

7.  **資料庫遷移 (首次啟動)：**
    * 推薦的 `Dockerfile` `CMD` 或 `ENTRYPOINT` 應會自動執行遷移。如果遇到問題或未自動執行，可手動執行：
        ```bash
        docker-compose exec web python manage.py migrate
        ```

### 訪問應用程式 (Docker)

* 容器成功啟動後，打開瀏覽器訪問：`http://localhost:8000/detector` (或您 `nginx.conf` 中設定的對外端口和路徑)

### Docker 常用指令

* **停止並移除容器、網路：** `docker-compose down`
* **查看所有服務日誌：** `docker-compose logs`
* **持續追蹤 web 服務日誌：** `docker-compose logs -f web`
* **在 web 容器內執行 shell：** `docker-compose exec web bash`

---

## 方法二：直接在本地環境運行 (不使用 Docker，主要用於開發)

此方法直接在你本地的作業系統（例如 WSL Ubuntu）上安裝依賴並運行 Django 開發伺服器。此設定也會優先使用 AWS S3 (如果 `.env` 中提供了相關憑證)，否則回退到本地 `media` 目錄。

### 環境需求

* **Python:** 3.9 或更高版本。
* **Pip:** Python 套件管理器。
* **PostgreSQL:** 需要在本機安裝並運行 PostgreSQL 資料庫服務。
* **YOLO 模型檔案:** 將 `best.pt` 放置於專案根目錄下的 `yolo/best.pt`。

### 設定與執行步驟

1.  **取得專案檔案：**
    ```bash
    git clone <你的 Git 倉庫 URL>
    cd <專案目錄名稱>
    ```

2.  **準備 YOLO 模型檔案：**
    * 將您的 YOLO 模型權重檔案 (例如 `best.pt`) 存放於專案根目錄下的 `yolo/best.pt`。

3.  **設定 Python 虛擬環境 (推薦)：**
    * 建立虛擬環境：
        ```bash
        python -m venv venv
        ```
    * 啟用虛擬環境：
        * Linux/macOS/WSL: `source venv/bin/activate`
        * Windows (CMD): `venv\Scripts\activate.bat`
        * Windows (PowerShell): `venv\Scripts\Activate.ps1`

4.  **安裝 Python 依賴：**
    ```bash
    pip install -r requirements.txt
    ```
    * **YOLO 相關依賴特別注意：** `requirements.txt` 中關於 `torch`, `torchvision`, `ultralytics` 的註解提到它們可能需要手動安裝或指定 CPU 版本以避免 CUDA 相關問題。請參考 Ultralytics 官方文件獲取適合您環境的安裝指令。例如，安裝 CPU 版本的 PyTorch：
        ```bash
        # pip install torch torchvision torchaudio --index-url [https://download.pytorch.org/whl/cpu](https://download.pytorch.org/whl/cpu)
        # pip install ultralytics
        ```

5.  **設定本地 PostgreSQL 資料庫：**
    * 確保你的 PostgreSQL 服務正在運行。
    * 建立一個新的資料庫 (例如 `strawberry_db_local`)。
    * 建立一個新的資料庫使用者 (例如 `strawberry_user_local`) 並設定密碼。
    * 授予該使用者對新資料庫的權限。

6.  **設定環境變數 (`.env`)：**
    * 在專案根目錄建立 `.env` 檔案（如果還沒有的話）。
    * 複製以下內容並**修改**以匹配你的設定：

        ```dotenv
        # Django 設定
        SECRET_KEY='請設定一個本地開發用的密鑰(不同於生產環境)'
        DEBUG=1 # 本地開發設為 1 (True)
        ALLOWED_HOSTS=localhost,127.0.0.1

        # 本地 PostgreSQL 資料庫設定
        POSTGRES_DB=strawberry_db_local # 你建立的本地資料庫名稱
        POSTGRES_USER=strawberry_user_local # 你建立的本地使用者名稱
        POSTGRES_PASSWORD=你的本地資料庫密碼
        DATABASE_HOST=localhost # 或 127.0.0.1
        DATABASE_PORT=5432 # 本地 PostgreSQL 預設端口

        # AWS S3 設定 (可選，若未提供，將使用本地 media 資料夾)
        AWS_ACCESS_KEY_ID=
        AWS_SECRET_ACCESS_KEY=
        AWS_STORAGE_BUCKET_NAME=
        AWS_S3_REGION_NAME=
        # AWS_S3_ENDPOINT_URL=
        ```
    * 你的 Django 專案使用 `python-dotenv` 來讀取此檔案（已包含在 `requirements.txt` 中）。
    * **AWS 詳細權限設定：** 如果您選擇使用 AWS S3，除了上述環境變數，請參考本文件末尾的「[AWS S3 詳細設定指引 (IAM, Bucket Policy, CORS)](#aws-s3-詳細設定指引-iam-bucket-policy-cors)」章節，以完成必要的 AWS 端權限配置。

7.  **建立本地 `media` 目錄 (若不使用 S3)：**
    * 如果**沒有**在 `.env` 中設定 AWS S3 憑證，Django 將使用本地檔案系統儲存媒體檔案。請確保以下目錄存在：
        ```bash
        mkdir -p media/temp_uploads
        mkdir -p media/uploads
        mkdir -p media/results
        ```

8.  **執行資料庫遷移：**
    * 確保虛擬環境已啟用。
    * 在專案根目錄執行：
        ```bash
        python manage.py makemigrations detector # 如果有模型變更
        python manage.py migrate
        ```

9.  **啟動 Django 開發伺服器：**
    * 在專案根目錄執行：
        ```bash
        python manage.py runserver
        ```

### 訪問應用程式 (本地)

* 開發伺服器啟動後，打開瀏覽器訪問：`http://127.0.0.1:8000/detector`
---

## AWS S3 詳細設定指引 (IAM, Bucket Policy, CORS)

本專案預設使用 AWS S3 儲存上傳的圖片及辨識結果圖。除了在 `.env` 檔案中設定 AWS 憑證和基本 S3 參數外，為了確保系統能安全且正確地與 AWS S3 互動，您還需要在 AWS 控制台進行以下 IAM 許可、S3 儲存貯體政策及 CORS 的設定。

我們提供了建議的設定範例(doc)，您可以根據這些範例調整以符合您的實際需求。

**1. IAM 許可 (IAM Policy)**

您的 Django 應用程式需要一個 IAM 角色或使用者，並擁有適當的權限才能上傳、讀取和管理 S3 中的媒體檔案。

* **必要權限摘要**：
    * `s3:PutObject`：允許上傳檔案到 `arn:aws:s3:::your-s3-bucket-name/*`
    * `s3:GetObject`：允許讀取 `arn:aws:s3:::your-s3-bucket-name/*` 中的檔案
    * `s3:DeleteObject`：允許刪除 `arn:aws:s3:::your-s3-bucket-name/*` 中的檔案
    * `s3:ListBucket`：允許列出 `arn:aws:s3:::your-s3-bucket-name` 中 `media/*` 和 `static/*` (如果您的靜態檔案也由 S3 托管) 前綴下的物件。
* **範例政策檔案**：
    * 我們提供了一個建議的 IAM 政策範例，您可以參考並修改其中的 `your-s3-bucket-name` 為您實際的儲存貯體名稱。
    * 範例檔案路徑：`docs/aws/iam_policy_example.json`

**2. S3 儲存貯體政策 (Bucket Policy)**

建議為您的 S3 儲存貯體設定政策以增強安全性，例如強制加密和 HTTPS 存取。

* **建議的安全措施**：
    * 強制所有上傳物件使用伺服器端加密 (例如 AES256)。
    * 強制所有請求透過 HTTPS。
* **範例政策檔案**：
    * 參考我們提供的 S3 儲存貯體政策範例，並替換 `your-s3-bucket-name`。
    * 範例檔案路徑：`docs/aws/s3_bucket_policy_example.json`

**3. S3 CORS (跨來源資源共享) 設定**

如果您的前端應用程式（瀏覽器端）需要直接從 S3 存取資源（例如顯示圖片），您需要在 S3 儲存貯體上設定 CORS。

* **設定要點**：
    * `AllowedOrigins`：應包含您應用程式的部署域名以及本地開發環境的 URL (例如 `http://localhost:8000`, `https://your-production-domain.com`)。
    * `AllowedMethods`：至少應允許 `GET` 和 `HEAD` 方法。
    * `AllowedHeaders`：根據需要設定，範例中允許了常用標頭及 `*`。
* **範例設定檔案**：
    * 參考我們提供的 S3 CORS 設定範例，並修改 `AllowedOrigins` 中的域名。
    * 範例檔案路্ডিং：`docs/aws/s3_cors_example.json`

**注意**：在設定這些 AWS 資源時，請務必遵循 AWS 的安全最佳實踐，並確保只授予必要的最小權限。

---
