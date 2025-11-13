# 草莓病蟲害辨識系統 - 後端 API (Django+ YOLO)

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-4.x-darkgreen?logo=django)](https://www.djangoproject.com/)
[![Django REST framework](https://img.shields.io/badge/DRF-API-red?logo=django)](https://www.django-rest-framework.org/)
[![Celery](https://img.shields.io/badge/Celery-Tasks-green?logo=celery)](https://docs.celeryq.dev/)
[![Docker](https://img.shields.io/badge/Docker-Containerized-blue?logo=docker)](https://www.docker.com/)

這是草莓病蟲害辨識系統的 **後端 API 伺服器**。  
本專案使用 **Django** 框架建構，核心功能是透過 **YOLO (You Only Look Once)** 物件偵測模型 (`yolo/best.pt`)  
來辨識上傳圖片中的草莓病徵。

本系統設計為一個 **RESTful API 服務**，由前端專案  
👉 [**Strawberry-detect-frontend (Vue.js)**](https://github.com/Nick921003/Strawberry-detect-frontend) 呼叫。

---

## 🌐 公開 API 端點
> https://api.strawberrydetect.com/api/process

---

## ☁️ 生產環境架構 (AWS)

本專案部署於 **AWS**，採用多層次、高可用性架構，以確保效能與穩定性。

### 🖥️ 前端 (Client)
- **服務**：GitHub Pages  
- **網址**：https://nick921003.github.io/Strawberry-detect-frontend/  
- **CI/CD**：使用 GitHub Actions 自動部署，建置時會注入生產 API 位址。

### 🌐 網路閘道 (Gateway)
- **服務**：AWS Application Load Balancer (ALB)  
- **網址**：`api.strawberrydetect.com`  
- **憑證**：AWS Certificate Manager (ACM)  
- **職責**：
  - 處理 HTTPS (SSL 終止)
  - 解決混合內容錯誤
  - 將 443 端口流量轉發到 EC2 實例的 8000 端口

### 🧩 應用程式伺服器 (Server)
- **服務**：AWS EC2  
- **運行方式**：使用 `docker-compose.yml` 啟動多容器堆疊  
- **健康檢查**：ALB 透過 `GET /admin/`（回傳 200 或 302）確認 Django 存活

### 🗂️ 檔案儲存 (Storage)
- **服務**：AWS S3  
- **職責**：透過 `django-storages` 儲存所有使用者上傳的原始圖片與辨識後圖片

---

## 🐳 Docker Compose 服務堆疊

在 EC2 實例內部，`docker-compose.yml` 負責編排以下服務：

| 服務 | 說明 |
|------|------|
| **nginx** | 內部反向代理，接收來自 ALB 的 8000 端口流量並轉發給 web。設定高超時 (3000s) 以處理大型檔案。 |
| **web** | Gunicorn 應用伺服器，運行 Django 應用 (載入 YOLO 模型)。Gunicorn 超時設定為 120s。 |
| **db** | PostgreSQL 資料庫，儲存所有辨識紀錄 (`DetectionRecord`) 與批次任務 (`BatchDetectionJob`)。 |
| **redis** | Celery 使用的訊息中介 (Broker)，儲存任務隊列。 |
| **celery_worker** | 背景任務執行緒，處理 S3 批次辨識任務 (`process_s3_batch_task`)，避免 API 超時。 |
| **celery_beat** | 定時任務排程器，用於未來功能（如 S3 定期掃描或舊資料清理）。 |

---

## ✨ API 主要功能

後端由 **Django REST Framework (DRF)** 驅動，主要端點如下：

### 🧠 模型載入
- 伺服器啟動時 (Gunicorn) 預先載入 `yolo/best.pt` 模型，加速回應速度。

### 📤 即時辨識 (上傳圖片)
`POST /api/process/upload/`  
- 接收前端上傳的單張或多張圖片  
- 同步執行 YOLO 辨識  
- 回傳結果 (標註圖片 URL、JSON 數據) 並儲存至資料庫  
- 回應：`201 Created`

### ☁️ S3 批次觸發 (非同步任務)
`POST /api/process/trigger_s3_batch/`  
- 接收 S3 儲存桶與資料夾路徑  
- 將任務推送至 Redis，由 Celery 背景執行 (`tasks.py: process_s3_batch_task`)  
- 立即回傳 Celery **Task ID**

### 🕒 歷史紀錄查詢
- `GET /api/process/` → 手動上傳紀錄列表（支援分頁）  
- `GET /api/process/{id}/` → 單筆手動紀錄詳情  
- `GET /api/process/batch_jobs/` → 批次任務列表（支援分頁）  
- `GET /api/process/batch_jobs/{id}/` → 單筆批次任務詳情（含所有辨識紀錄）

### 🔒 安全性設定
已精確設定：
```python
CORS_ALLOWED_ORIGINS = ['https://nick921003.github.io']
CSRF_TRUSTED_ORIGINS = ['https://nick921003.github.io']
```

---

## 🛠️ 技術棧

| 類別 | 技術 |
|------|------|
| 框架 | Django, Django REST Framework |
| AI 模型 | YOLO (Ultralytics) |
| WSGI 伺服器 | Gunicorn |
| 反向代理 | Nginx |
| 資料庫 | PostgreSQL |
| 非同步任務 | Celery + Redis |
| 雲端服務 | AWS EC2, S3, ALB, ACM |
| 檔案儲存 | django-storages (連接 S3) |
| 環境管理 | Docker + Docker Compose |
| 環境變數管理 | python-dotenv (.env) |

---

## 🚀 本地開發設定

### 1️⃣ Clone 儲存庫
```bash
git clone https://github.com/Nick921003/StrawberryDetect_Web.git
cd StrawberryDetect_Web
```

### 2️⃣ 下載 YOLO 模型
請確保 `yolo/best.pt` 模型檔案存在。  
若不存在，請從您訓練的地方下載並放入 `yolo/` 資料夾中。

### 3️⃣ 建立 `.env` 檔案
在專案根目錄（與 `docker-compose.yml` 同層）建立 `.env`，範例如下：

```bash
# Django 設定
DEBUG=1
SECRET_KEY=your_local_secret_key_12345
ALLOWED_HOSTS=localhost,127.0.0.1

# 資料庫
POSTGRES_DB=strawberry_db
POSTGRES_USER=strawberry_user
POSTGRES_PASSWORD=strawberry_pass
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# 本地 CORS/CSRF (允許 Vue 開發伺服器)
CORS_ALLOWED_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:5173,http://localhost:5173

# AWS S3 (可選)
# AWS_ACCESS_KEY_ID=...
# AWS_SECRET_ACCESS_KEY=...
# AWS_STORAGE_BUCKET_NAME=your-s3-bucket-name
# AWS_S3_REGION_NAME=your-region
# AWS_S3_CUSTOM_DOMAIN=...
```

### 4️⃣ 啟動 Docker Compose
確保 **Docker Desktop**（或 Docker Engine）已啟動。

```bash
docker-compose up --build
```
> `--build` 會強制重新建置 Docker image。

### 5️⃣ 執行資料庫遷移
等待 `web` 服務啟動後，開啟新的終端機視窗：

```bash
docker-compose exec web python manage.py migrate
```

### 6️⃣ 建立超級使用者（可選）
用於登入 Django Admin 後台：

```bash
docker-compose exec web python manage.py createsuperuser
```

### 7️⃣ 訪問本地服務
- **API (Nginx)**： [http://127.0.0.1:8000/api/process/](http://127.0.0.1:8000/api/process/)  
- **Admin 後台**： [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)

---
