# StrawberryDetect_Web
# 草莓病蟲害辨識系統

本專案是一個使用 Django、YOLO (透過 Ultralytics)、PostgreSQL、Nginx、Celery 及 Redis 建構的草莓病蟲害辨識系統。系統能夠辨識如「角斑病 (angular leaf spot)」與「健康 (healthy)」的草莓葉片狀態。

**重要運行方式說明：**

* **本專案已深度整合 Redis 作為 Celery 的訊息代理 (Message Broker) 以支援非同步任務處理 (如批次圖片辨識、排程資料清理等)。因此，強烈建議（且主要支援）使用 Docker 進行部署與開發，以確保所有服務能正確協同運作。**
* 本專案預設設定使用 AWS S3 進行圖片等媒體檔案的儲存。

---

## 目錄 (Table of Contents)

* [專案功能簡述](#專案功能簡述)
* [技術棧](#技術棧)
* [核心機制](#核心機制)
* [使用 Docker 運行 (推薦)](#使用-docker-運行-推薦)
    * [環境需求](#環境需求)
    * [設定與執行步驟](#設定與執行步驟)
    * [訪問應用程式](#訪問應用程式-docker)
    * [Docker 常用指令](#docker-常用指令)
* [API 接口說明 (選填)](#api-接口說明-選填)
* [資料保留策略](#資料保留策略)
* [AWS S3 詳細設定指引](#aws-s3-詳細設定指引-iam-bucket-policy-cors)

---

## 專案功能簡述

* **圖片上傳與辨識**：使用者可以上傳草莓葉片圖片，系統將使用 YOLO 模型進行病蟲害辨識。
* **結果展示**：顯示原始圖片、標註後的結果圖以及辨識出的類別和信心度。
* **辨識歷史**：使用者可以查看最近的手動上傳辨識紀錄。
* **批次處理 (透過 API)**：支援透過 API 提交 S3 資料夾路徑，由系統非同步批次處理資料夾內所有圖片。
* **排程資料清理**：自動清理過期的辨識紀錄與批次任務。

---

## 技術棧

* **後端框架**: Django, Django REST Framework
* **物件偵測**: YOLO (Ultralytics)
* **資料庫**: PostgreSQL
* **網頁伺服器/反向代理**: Nginx
* **非同步任務佇列**: Celery
* **訊息代理/快取**: Redis
* **容器化**: Docker, Docker Compose
* **雲端儲存**: AWS S3

---

## 核心機制

* **非同步任務處理**:
    * **S3 資料夾批次圖片辨識**: 當透過 API 請求處理 S3 資料夾中的圖片時，此任務會被提交給 Celery。Celery Worker 會在背景非同步下載、辨識每一張圖片，並將結果儲存。這避免了 API 請求長時間等待。
    * **資料清理**: 使用 Celery Beat 排程定期任務，自動清理舊的辨識紀錄和批次任務資料，以維護系統效能和儲存空間。
* **模型推論**:
    * 應用程式啟動時會載入預先訓練好的 YOLO 模型 (`best.pt`)。
    * 對於上傳的圖片或 S3 中的圖片，系統會呼叫模型進行物件偵測，找出病害區域或健康葉片。
* **資料儲存**:
    * 辨識紀錄、批次任務資訊儲存於 PostgreSQL 資料庫。
    * 原始圖片及標註後的結果圖則上傳至 AWS S3 進行儲存與管理。

---

## 使用 Docker 運行 (推薦)

此方法使用 Docker Compose 來建立和管理應用程式所需的服務容器（Web 應用、資料庫、Redis、Celery Worker、Celery Beat、反向代理）。此設定預期使用 AWS S3 儲存上傳的檔案。

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
        CSRF_TRUSTED_ORIGINS=http://localhost:8000,[http://yourdomain.com](http://yourdomain.com),[https://yourdomain.com](https://yourdomain.com) # 根據 Nginx 端口和域名調整

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

        ```
    * **重要：** `.env` 包含敏感資訊，切勿提交到 Git。`.gitignore` 應包含 `.env`。
    * **AWS 詳細權限設定：** 除了上述環境變數，請參考本文件末尾的「[AWS S3 詳細設定指引 (IAM, Bucket Policy, CORS)](#aws-s3-詳細設定指引-iam-bucket-policy-cors)」章節，以完成必要的 AWS 端權限配置。

4.  **取得 Docker 映像檔：**
    * **推薦方式：從 Docker Hub 拉取預建映像檔 (如果已發布)。**
        ```bash
        docker pull nick45320639/strawberrydetect:latest
        ```
        *(Docker Compose 在 `up` 時如果本地找不到也會嘗試拉取，但手動拉取可以確認下載成功)*
    * **替代方式：在本地建構映像檔。** 如果你想自行修改 `Dockerfile` 或基於最新程式碼建構 (請確保 `yolo/best.pt` 模型已存在於專案中，`Dockerfile` 應包含複製此模型的步驟)：
        ```bash
        docker-compose build web celery_worker celery_beat # 建構需要的服務
        ```
        或僅建構 `web` (如果其他服務使用相同的基礎映像且 `build: .`)
        ```bash
        docker-compose build
        ```


5.  **啟動應用程式容器：**
    * 在專案根目錄的終端機中執行：
        ```bash
        docker-compose up -d
        ```
    * `-d` 參數讓容器在背景執行。
    * 此指令會啟動所有在 `docker-compose.yml` 中定義的服務，包括：
        * `db`: PostgreSQL 資料庫
        * `redis`: Redis 伺服器 (供 Celery 使用)
        * `web`: Django Gunicorn 應用程式伺服器
        * `celery_worker`: Celery 背景任務執行緒
        * `celery_beat`: Celery 排程任務觸發器
        * `nginx`: Nginx 反向代理伺服器

6.  **資料庫遷移 (首次啟動)：**
    * `Dockerfile` 中的 `CMD` 或 `ENTRYPOINT` 應已包含自動執行遷移的指令。如果遇到問題或未自動執行，可手動執行：
        ```bash
        docker-compose exec web python manage.py migrate
        ```
    * 若要創建超級使用者：
        ```bash
        docker-compose exec web python manage.py createsuperuser
        ```

### 訪問應用程式 (Docker)

* 容器成功啟動後，打開瀏覽器訪問：`http://localhost:PORT/detector` (其中 `PORT` 是您在 `.env` 中設定的 `NGINX_PORT` 或 `docker-compose.yml` 中 `nginx` 服務映射的主機端口，預設可能是 `8000`)。

### Docker 常用指令

* **啟動所有服務 (背景執行)：** `docker-compose up -d`
* **停止並移除容器、網路：** `docker-compose down`
* **僅停止服務：** `docker-compose stop`
* **僅啟動已停止的服務：** `docker-compose start`
* **查看所有服務日誌：** `docker-compose logs`
* **持續追蹤特定服務日誌 (例如 web)：** `docker-compose logs -f web`
* **在 web 容器內執行 shell：** `docker-compose exec web bash`
* **重新建構映像檔並啟動：** `docker-compose up -d --build`
* **查看運行中的容器：** `docker-compose ps`

---

## API 接口說明 

本專案提供 API 接口以支援自動化或外部系統整合。

### 批次處理 S3 資料夾中的圖片

* **端點 (Endpoint):** `/api/process/process_s3_folder/`
* **方法 (Method):** `POST`
* **請求體 (Request Body):** JSON 格式
    ```json
    {
        "s3_bucket_name": "your-s3-bucket-name",
        "s3_folder_prefix": "path/to/your/images_folder/"
    }
    ```
    * `s3_bucket_name` (string, required): 您的 AWS S3 儲存桶名稱。
    * `s3_folder_prefix` (string, required): S3 儲存桶中圖片所在資料夾的路徑/前綴 (例如 `uploads/batch1/`，結尾的 `/` 可選，系統會自動處理)。
* **成功回應 (Success Response):** `202 Accepted`
    ```json
    {
        "message": "S3 資料夾 (s3://your-s3-bucket-name/path/to/your/images_folder/) 的批次處理任務已提交，正在背景執行。",
        "celery_task_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" // Celery 主任務的 ID
    }
    ```
    * 這表示請求已被接受，Celery 任務已成功分派到背景執行。您可以透過 Celery Task ID (或後續產生的 BatchDetectionJob ID) 追蹤任務狀態 (目前需透過 Django Admin 或資料庫查詢)。
* **失敗回應 (Error Response):**
    * `400 Bad Request`: 若請求體格式錯誤或缺少必要欄位。
        ```json
        {
            "s3_bucket_name": ["This field is required."],
            "s3_folder_prefix": ["This field is required."]
        }
        ```
    * 其他伺服器錯誤 (如 `500 Internal Server Error`) 可能表示 Celery 服務無法連接或分派任務時發生問題。

---

## 資料保留策略

為有效管理儲存空間與系統效能，本系統實施以下資料保留策略：

* **手動上傳辨識紀錄 (`DetectionRecord` where `batch_job` is NULL):**
    * **即時清理**: 每次成功手動上傳後，系統會檢查並自動刪除較舊的記錄，僅保留最新的 `MANUAL_RECORDS_TO_KEEP_IMMEDIATE` 筆 (預設值請參考 `detector_project/settings.py`)。
    * **定期清理**: 透過 Celery Beat 排程任務，每日定期清理，確保手動上傳記錄不超過 `MANUAL_RECORDS_TO_KEEP` 筆。
* **批次辨識任務 (`BatchDetectionJob`):**
    * **按數量清理**: 每次批次任務完成（狀態變為 `COMPLETED`, `FAILED`, `PARTIAL_COMPLETION`）後，系統會檢查並自動刪除較舊的已完成/失敗批次任務，僅保留最新的 `BATCH_JOBS_TO_KEEP_BY_COUNT` 個。
    * **按時間清理 (定期)**: 透過 Celery Beat 排程任務，每日定期清理創建時間早於 `DAYS_TO_KEEP_BATCHES` 天的已完成/失敗批次任務。

相關參數可在 `detector_project/settings.py` 中調整。所有刪除操作會同時嘗試刪除 AWS S3 上對應的圖片檔案 (透過 `django-cleanup` 和自訂信號處理)。

---

## AWS S3 詳細設定指引 (IAM, Bucket Policy, CORS)

本專案預設使用 AWS S3 儲存上傳的圖片及辨識結果圖。除了在 `.env` 檔案中設定 AWS 憑證和基本 S3 參數外，為了確保系統能安全且正確地與 AWS S3 互動，您還需要在 AWS 控制台進行以下 IAM 許可、S3 儲存貯體政策及 CORS 的設定。

我們提供了建議的設定範例 (位於 `doc/aws/` 目錄下)，您可以根據這些範例調整以符合您的實際需求。

**1. IAM 許可 (IAM Policy)**

您的 Django 應用程式需要一個 IAM 角色或使用者，並擁有適當的權限才能上傳、讀取和管理 S3 中的媒體檔案。

* **必要權限摘要**：
    * `s3:PutObject`：允許上傳檔案到 `arn:aws:s3:::your-s3-bucket-name/*`
    * `s3:GetObject`：允許讀取 `arn:aws:s3:::your-s3-bucket-name/*` 中的檔案
    * `s3:DeleteObject`：允許刪除 `arn:aws:s3:::your-s3-bucket-name/*` 中的檔案
    * `s3:ListBucket`：允許列出 `arn:aws:s3:::your-s3-bucket-name` 中 `media/*` 和 `static/*` (如果您的靜態檔案也由 S3 托管) 前綴下的物件。
* **範例政策檔案**：
    * 參考 `docs/aws/iam_policy_example.json`，並修改其中的 `your-s3-bucket-name`。

**2. S3 儲存貯體政策 (Bucket Policy)**

建議為您的 S3 儲存貯體設定政策以增強安全性，例如強制加密和 HTTPS 存取。

* **建議的安全措施**：
    * 強制所有上傳物件使用伺服器端加密 (例如 AES256)。
    * 強制所有請求透過 HTTPS。
* **範例政策檔案**：
    * 參考 `docs/aws/s3_bucket_policy_example.json`，並替換 `your-s3-bucket-name`。

**3. S3 CORS (跨來源資源共享) 設定**

如果您的前端應用程式（瀏覽器端）需要直接從 S3 存取資源（例如顯示圖片），您需要在 S3 儲存貯體上設定 CORS。

* **設定要點**：
    * `AllowedOrigins`：應包含您應用程式的部署域名以及本地開發環境的 URL (例如 `http://localhost:8000`, `https://your-production-domain.com`)。
    * `AllowedMethods`：至少應允許 `GET` 和 `HEAD` 方法。
    * `AllowedHeaders`：根據需要設定，範例中允許了常用標頭及 `*`。
* **範例設定檔案**：
    * 參考 `docs/aws/s3_cors_example.json`，並修改 `AllowedOrigins` 中的域名。

**注意**：在設定這些 AWS 資源時，請務必遵循 AWS 的安全最佳實踐，並確保只授予必要的最小權限。

---

## (附錄) 本地環境運行 (已棄用/不建議)

**由於本專案已整合 Redis 以支援 Celery 非同步任務，強烈建議使用上述的 Docker 方法進行部署與開發。**

若您仍需要在本地直接運行（不使用 Docker），請注意以下事項：

* 您需要自行在本地安裝並設定 PostgreSQL 資料庫服務。
* 您需要自行在本地安裝並設定 Redis 服務。
* Celery Worker 和 Celery Beat 需要單獨啟動。
* 本地環境設定複雜且容易出錯，**此運行方式的說明不再主動維護**，且可能無法完整體驗所有功能 (特別是非同步任務)。
* 您自行調整以適應 Redis 的加入。

---
