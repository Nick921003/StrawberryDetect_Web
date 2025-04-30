# StrawberryDetect_Web
# 草莓病蟲害辨識系統 (Docker 版)

這是一個使用 Django、YOLO、PostgreSQL 和 Nginx 建構的草莓病蟲害辨識系統，並透過 Docker Compose 進行容器化部署。

## 環境需求

* **Docker:** [安裝 Docker](https://docs.docker.com/get-docker/)
* **Docker Compose:** 通常隨 Docker Desktop 一起安裝。若無，請參考 [安裝 Docker Compose](https://docs.docker.com/compose/install/)。

## 設定與執行步驟

1.  **取得專案檔案：**
    * 如果你是透過 Git Clone 取得專案：
        ```bash
        git clone <你的 Git 倉庫 URL>
        cd <專案目錄名稱>
        ```
    * 或者，確保你取得了以下檔案，並將它們放在同一個目錄下：
        * `docker-compose.yml`
        * `nginx.conf`
        * (如果需要) 其他非程式碼的設定檔

2.  **建立環境變數檔案 (`.env`)：**
    * 在專案根目錄（與 `docker-compose.yml` 同層）**手動建立**一個名為 `.env` 的檔案。
    * 複製以下內容到你的 `.env` 檔案中，並**修改**成你自己的設定值（特別是 `SECRET_KEY` 和資料庫密碼）：

        ```dotenv
        # Django 設定
        # 請務必產生一個新的、隨機的 SECRET_KEY！可以使用 Django secret key generator 等工具。
        SECRET_KEY=請替換成一個強隨機密鑰!例如: 'django-insecure-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
        DEBUG=0 # 生產環境建議設為 0 (False)，本地測試可設為 1

        # PostgreSQL 資料庫設定 (需與 docker-compose.yml 中的設定一致)
        POSTGRES_DB=strawberry_db
        POSTGRES_USER=strawberry_user
        # 請設定一個安全的資料庫密碼
        POSTGRES_PASSWORD=請設定你的資料庫密碼
        DATABASE_HOST=db # 這個通常保持為 'db'，對應 docker-compose.yml 的服務名稱
        DATABASE_PORT=5432 # PostgreSQL 預設端口

        # YOLO 設定 (如果需要)
        YOLO_CONFIG_DIR=/tmp/yolov8_config # 通常保持預設即可

        # 其他你可能需要的環境變數，例如 ALLOWED_HOSTS
        # ALLOWED_HOSTS=localhost,127.0.0.1,your_domain.com
        ```
    * **重要：** `.env` 檔案包含敏感資訊，請**不要**將它提交到公開的 Git 倉庫。`.gitignore` 檔案中應包含 `.env`。
    * 如不使用docker，DATABASE_HOST=localhost

3.  **建立必要的本地目錄：**
    * 在專案根目錄下建立 `media` 目錄，用於存放使用者上傳的檔案：
        ```bash
        mkdir -p media/temp_uploads
        mkdir -p media/uploads
        mkdir -p media/results
        ```
    * (僅限本地開發，且遇到權限問題時) 為了讓容器有權限寫入，你可能需要在**主機**上執行：
        ```bash
        chmod -R 777 media
        ```
        *注意：`chmod 777` 權限非常寬鬆，不建議在生產環境使用。*  
        *後續會嘗試改用雲端儲存AWS或是GCS，或是在linux原生環境部屬網站時，匹配 UID/GID方式*

4.  **拉取 Docker 映像檔 (可選)：**
    * `docker-compose up` 會自動拉取映像檔，但你也可以先手動拉取 `web` 服務的映像檔（將 `<使用者名稱>` 和 `<映像庫名稱>` 換成實際的）：
        ```bash
        docker pull <你的 Docker Hub 使用者名稱>/<映像庫名稱>:latest
        ```

5.  **啟動應用程式：**
    * 在專案根目錄的終端機中執行：
        ```bash
        docker-compose up -d
        ```
    * `-d` 參數會讓容器在背景執行。首次啟動會需要一些時間來建立資料庫和應用遷移。
    * 如不使用docker，執行:
        ```bash
        python manage.py runserver
        ```

6.  **資料庫遷移 (首次啟動後)：**
    * 雖然推薦的 `Dockerfile` `CMD` 會自動執行遷移，但如果沒有自動執行，你可能需要手動執行一次：
        ```bash
        docker-compose exec web python manage.py migrate
        ```
    * 如不使用docker，執行:
      ```bash
      python manage.py migrate
      ```

## 訪問應用程式

* 容器成功啟動後，打開你的網頁瀏覽器，訪問：[http://localhost:8000/detector](http://localhost:8000/detector)

## 其他常用指令

* **停止並移除容器、網路：**
    ```bash
    docker-compose down
    ```
* **查看所有服務的日誌：**
    ```bash
    docker-compose logs
    ```
* **持續追蹤特定服務的日誌 (例如 web)：**
    ```bash
    docker-compose logs -f web
    ```
* **在 web 容器內執行指令 (例如進入 shell)：**
    ```bash
    docker-compose exec web bash
    ```


