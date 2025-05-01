# StrawberryDetect_Web
# 草莓病蟲害辨識系統

這是一個使用 Django、YOLO、PostgreSQL 和 Nginx 建構的草莓病蟲害辨識系統。本文件提供兩種運行方式的說明：使用 Docker（推薦，用於部署和一致的環境）和直接在本地環境運行（用於開發）。

---

## 方法一：使用 Docker 運行 (推薦)

此方法使用 Docker Compose 來建立和管理應用程式所需的服務容器（Web 應用、資料庫、反向代理）。

### 環境需求

* **Docker:** [安裝 Docker](https://docs.docker.com/get-docker/)
* **Docker Compose:** 通常隨 Docker Desktop 一起安裝。若無，請參考 [安裝 Docker Compose](https://docs.docker.com/compose/install/)。

### 設定與執行步驟

1.  **取得專案檔案：**
    * 透過 Git Clone：
        ```bash
        git clone <你的 Git 倉庫 URL>
        cd <專案目錄名稱>
        ```
    * 或者，確保你取得了 `docker-compose.yml` 和 `nginx.conf` 等必要設定檔。

2.  **建立環境變數檔案 (`.env`)：**
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
        DEBUG=0 # 生產建議設為 0，本地測試可設為 1

        # PostgreSQL 資料庫設定 (需與 docker-compose.yml 中的設定一致)
        POSTGRES_DB=strawberry_db
        POSTGRES_USER=strawberry_user
        POSTGRES_PASSWORD=請設定你的資料庫密碼
        DATABASE_HOST=db # Docker Compose 服務名稱
        DATABASE_PORT=5432

        # YOLO 設定
        YOLO_CONFIG_DIR=/tmp/yolov11_config
        ```
    * **重要：** `.env` 包含敏感資訊，切勿提交到 Git。`.gitignore` 應包含 `.env`。

3.  **建立本地 `media` 目錄：**
    * 容器需要地方寫入使用者上傳的檔案。在專案根目錄執行：
        ```bash
        mkdir -p media/temp_uploads
        mkdir -p media/uploads
        mkdir -p media/results
        ```
    * **(僅限本地開發權限問題)** 若在 Windows (WSL) 或 macOS 的 Docker Desktop 環境遇到寫入權限錯誤，可能需要在**主機**終端機執行（生產環境不建議）：
        ```bash
        chmod -R 777 media
        ```
        * *備註：後續會嘗試在生產環境使用雲端儲存 (AWS S3/GCS) 或在 Linux 伺服器上匹配 UID/GID 來處理權限。*

4.  **取得 Docker 映像檔：**
    * **推薦方式：從 Docker Hub 拉取預建映像檔。** 這會使用開發者已經建置並上傳的版本：
        ```bash
        docker pull nick45320639/strawberrydetect:latest
        ```
        *(Docker Compose 在 `up` 時如果本地找不到也會嘗試拉取，但手動拉取可以確認下載成功)*
    * **替代方式：在本地建構映像檔。** 如果你想自行修改 `Dockerfile` 或基於最新程式碼建構：
        ```bash
        docker-compose build web
        ```

5.  **啟動應用程式容器：**
    * 在專案根目錄的終端機中執行：
        ```bash
        docker-compose up -d
        ```
    * `-d` 參數讓容器在背景執行。

6.  **資料庫遷移 (首次啟動)：**
    * 推薦的 `Dockerfile` `CMD` 會自動執行遷移。如果遇到問題或未自動執行，可手動執行：
        ```bash
        docker-compose exec web python manage.py migrate
        ```

### 訪問應用程式 (Docker)

* 容器成功啟動後，打開瀏覽器訪問：[http://localhost:8000/detector](http://localhost:8000/detector) 

### Docker 常用指令

* **停止並移除容器、網路：** `docker-compose down`
* **查看所有服務日誌：** `docker-compose logs`
* **持續追蹤 web 服務日誌：** `docker-compose logs -f web`
* **在 web 容器內執行 shell：** `docker-compose exec web bash`

---

## 方法二：直接在本地環境運行 (不使用 Docker，主要用於開發)

此方法直接在你本地的作業系統（例如 WSL Ubuntu）上安裝依賴並運行 Django 開發伺服器。

### 環境需求

* **Python:** 3.9 或更高版本。
* **Pip:** Python 套件管理器。
* **PostgreSQL:** 需要在本機安裝並運行 PostgreSQL 資料庫服務。

### 設定與執行步驟

1.  **取得專案檔案：**
    * 透過 Git Clone：
        ```bash
        git clone <你的 Git 倉庫 URL>
        cd <專案目錄名稱>
        ```

2.  **設定 Python 虛擬環境 (推薦)：**
    * 建立虛擬環境：
        ```bash
        python -m venv venv
        ```
    * 啟用虛擬環境：
        * Linux/macOS/WSL: `source venv/bin/activate`
        * Windows (CMD): `venv\Scripts\activate.bat`
        * Windows (PowerShell): `venv\Scripts\Activate.ps1`

3.  **安裝 Python 依賴：**
    ```bash
    pip install -r requirements.txt
    ```
    * *注意：如果 `requirements.txt` 包含 GPU 版本的 PyTorch，而你本地沒有相應的 GPU 或驅動，可能會遇到問題或效能不佳。開發時可能需要調整 `requirements.txt` 或安裝 CPU 版本。*

4.  **設定本地 PostgreSQL 資料庫：**
    * 確保你的 PostgreSQL 服務正在運行。
    * 建立一個新的資料庫 (例如 `strawberry_db_local`)。
    * 建立一個新的資料庫使用者 (例如 `strawberry_user_local`) 並設定密碼。
    * 授予該使用者對新資料庫的權限。

5.  **設定環境變數 (`.env`)：**
    * 在專案根目錄建立 `.env` 檔案（如果還沒有的話）。
    * 複製以下內容並**修改**以匹配你的**本地**資料庫設定：

        ```dotenv
        # Django 設定
        SECRET_KEY='請設定一個本地開發用的密鑰'
        DEBUG=1 # 本地開發設為 1 (True)

        # 本地 PostgreSQL 資料庫設定
        POSTGRES_DB=strawberry_db_local # 你建立的本地資料庫名稱
        POSTGRES_USER=strawberry_user_local # 你建立的本地使用者名稱
        POSTGRES_PASSWORD=你的本地資料庫密碼
        DATABASE_HOST=localhost # 或 127.0.0.1
        DATABASE_PORT=5432 # 本地 PostgreSQL 預設端口

        # YOLO 設定
        YOLO_CONFIG_DIR=/tmp/yolov8_config # 或其他本地可寫路徑

        # 其他環境變數
        # ALLOWED_HOSTS=localhost,127.0.0.1
        ```
    * 你的 Django 專案需要使用 `python-dotenv` 來讀取此檔案（已包含在 `requirements.txt` 中）。

6.  **建立本地 `media` 目錄：**
    ```bash
    mkdir -p media/temp_uploads
    mkdir -p media/uploads
    mkdir -p media/results
    ```

7.  **執行資料庫遷移：**
    * 確保虛擬環境已啟用。
    * 在專案根目錄執行：
        ```bash
        python manage.py makemigrations detector # 如果有模型變更
        python manage.py migrate
        ```

8.  **啟動 Django 開發伺服器：**
    * 在專案根目錄執行：
        ```bash
        python manage.py runserver
        ```

### 訪問應用程式 (本地)

* 開發伺服器啟動後，打開瀏覽器訪問：[http://127.0.0.1:8000/detector](http://127.0.0.1:8000/detector) (或其他你設定的 URL)

---
