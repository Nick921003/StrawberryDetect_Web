# 草莓病蟲害辨識系統 - 後端 API (Django)

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-4.x-darkgreen?logo=django)](https://www.djangoproject.com/)
[![Django REST framework](https://img.shields.io/badge/DRF-API-red?logo=django)](https://www.django-rest-framework.org/)
[![Celery](https://img.shields.io/badge/Celery-Tasks-green?logo=celery)](https://docs.celeryq.dev/)
[![Docker](https://img.shields.io/badge/Docker-Containerized-blue?logo=docker)](https://www.docker.com/)

這是草莓病蟲害辨識系統的後端 RESTful API 服務，使用 Django 和 Django REST framework 建構。它負責處理圖片辨識請求、管理資料庫、執行背景任務 (透過 Celery)，並提供 API 接口供前端或其他客戶端呼叫。

**前端專案連結:**
* [Strawberry-detect-frontend (Vue.js)](https://github.com/Nick921003/Strawberry-detect-frontend.git)

---

## ✨ 核心功能

* **圖片辨識 API:**
    * 接收手動上傳的圖片 (單張/多張)。
    * 觸發 S3 資料夾的批次辨識任務。
    * 使用 YOLO 模型進行草莓病蟲害推論。
    * 計算嚴重程度分數。
    * 將原始圖片、標註後圖片和結果儲存至 S3 (或本地) 與資料庫。
* **歷史紀錄 API:**
    * 提供手動上傳和批次任務的歷史紀錄查詢 (支援分頁)。
    * 提供單筆紀錄和批次任務的詳細資料查詢 (包含巢狀結果)。
* **背景任務處理 (Celery):**
    * 非同步處理 S3 批次辨識任務，避免阻塞 API 請求。
    * 使用 Celery Beat 執行定期的舊資料清理任務。
* **資料保留策略:**
    * 可設定手動上傳和批次任務的保留天數或數量。
    * 手動上傳後**立即**清理舊紀錄，維持設定數量。
    * 批次任務完成後**立即**清理舊批次，維持設定數量。
* **Docker 化部署:**
    * 使用 Docker Compose 整合 Django (Gunicorn)、Nginx、PostgreSQL、Redis、Celery Worker 和 Celery Beat，簡化部署流程。

## 🔧 主要 API 端點

所有 API 端點皆位於 `/api/process/` 基礎路徑下：

* **`POST /api/process/upload/`**: 手動上傳圖片 (multipart/form-data)。
    * 請求體: `images` 欄位包含一個或多個圖片檔案。
    * 回應: `201 Created`，包含一個或多個 `DetectionRecordDetail` 物件。
* **`POST /api/process/process_s3_folder/`**: 觸發 S3 批次處理任務。
    * 請求體 (JSON): `{ "s3_bucket_name": "...", "s3_folder_prefix": "..." }`
    * 回應: `202 Accepted`，包含 `message` 和 `celery_task_id`。
* **`GET /api/process/history/manual/`**: 獲取手動上傳歷史紀錄列表 (支援分頁 `?page=...`)。
    * 回應: 分頁物件，`results` 包含 `DetectionRecordList` 物件陣列。
* **`GET /api/process/history/batch/`**: 獲取批次任務歷史列表 (支援分頁 `?page=...`)。
    * 回應: 分頁物件，`results` 包含 `BatchDetectionJobList` 物件陣列。
* **`GET /api/process/record/{record_id}/`**: 獲取單筆辨識紀錄詳情。
    * 回應: `DetectionRecordDetail` 物件。
* **`GET /api/process/batch/{batch_id}/`**: 獲取單筆批次任務詳情 (包含巢狀的 `detection_records`)。
    * 回應: `BatchDetectionJobDetail` 物件。

*(詳細的 Serializer 欄位請參考 `detector/api/serializers.py`)*

## 🐳 使用 Docker Compose 運行 (推薦)

**環境需求:**

* [Docker](https://www.docker.com/products/docker-desktop/)
* [Docker Compose](https://docs.docker.com/compose/install/)

**步驟:**

1.  **Clone 儲存庫:**
    ```bash
    git clone [https://github.com/Nick921003/StrawberryDetect_Web.git](https://github.com/Nick921003/StrawberryDetect_Web.git)
    cd StrawberryDetect_Web
    ```

2.  **建立環境變數檔案:**
    * 複製 `.env.example` (如果有的話) 或手動建立 `.env` 檔案。
    * 填寫必要的環境變數，至少包含：
        * `SECRET_KEY` (Django 金鑰，可自行生成)
        * `DEBUG` (設為 `1` 開發，`0` 生產)
        * `ALLOWED_HOSTS` (例如 `localhost,127.0.0.1`)
        * `CSRF_TRUSTED_ORIGINS` (例如 `http://localhost:8000,http://127.0.0.1:8000`)
        * `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` (資料庫設定)
        * `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME` (S3 設定)
        * `CORS_ALLOWED_ORIGINS` (**重要!** 必須包含前端應用的來源 URL，例如 `http://127.0.0.1:5173` 或部署後的 GitHub Pages URL)

3.  **建置並啟動容器:**
    ```bash
    docker-compose up -d --build
    ```

4.  **執行資料庫遷移:**
    ```bash
    docker-compose exec web python manage.py migrate
    ```

5.  **建立超級使用者 (可選):**
    ```bash
    docker-compose exec web python manage.py createsuperuser
    ```

6.  **訪問:**
    * API 服務: `http://localhost:8000/api/process/`
    * Admin 後台: `http://localhost:8000/admin/`

## ⚙️ AWS S3 設定指引

詳細的 IAM 權限、Bucket Policy 和 CORS 設定範例，請參考 `/doc/aws/` 目錄下的文件 ([explain.md](doc/aws/explain.md), [iam_policy_example.json](doc/aws/iam_policy_example.json), [s3_bucket_policy_example.json](doc/aws/s3_bucket_policy_example.json), [s3_cors_example.json](doc/aws/s3_cors_example.json))。

**重點提醒:**

* **CORS 設定:** 務必在 AWS S3 Bucket 的 CORS 設定中，允許來自前端應用程式來源 (例如 `http://127.0.0.1:5173` 或 GitHub Pages URL) 的 `GET`, `POST`, `PUT`, `HEAD` 等請求，並允許必要的標頭 (例如 `Authorization`, `Content-Type`)。同時，Django `settings.py` 中的 `CORS_ALLOWED_ORIGINS` 也需要包含前端來源。

## 🗑️ 資料保留策略設定

可在 `.env` 或 `detector_project/settings.py` 中調整以下參數：

* `MANUAL_RECORDS_TO_KEEP`: 手動上傳紀錄保留數量 (每次上傳後即時清理)。
* `DAYS_TO_KEEP_MANUAL_RECORDS`: 手動上傳紀錄保留天數 (由排程任務清理)。
* `BATCH_JOBS_TO_KEEP_BY_COUNT`: 批次任務記錄保留數量 (批次完成後即時清理)。
* `DAYS_TO_KEEP_BATCHES`: 批次任務記錄保留天數 (由排程任務清理)。
* Celery Beat 排程 (`CELERY_BEAT_SCHEDULE`): 設定定期清理任務的執行時間。

---

*(你可以視情況補充更多資訊)*