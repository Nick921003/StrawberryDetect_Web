# 使用官方 Python 作為基礎映像 (選擇與你環境相近的版本，例如 3.10 或 3.12)
# slim 版本比較小
FROM python:3.12-slim

# 設定環境變數
ENV PYTHONDONTWRITEBYTECODE 1  # 防止 Python 寫入 .pyc 文件
ENV PYTHONUNBUFFERED 1      # 讓 Python 的輸出直接打印到終端，方便看 Log

# 設定工作目錄 (容器內的路徑)
WORKDIR /app

# 安裝系統層級的依賴套件
# opencv-python-headless 有時需要一些底層圖形庫
# libpq-dev 是 psycopg2 可能需要的 (雖然 binary 通常自帶，但加上較保險)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libgl1-mesa-glx \
       libglib2.0-0 \
       libpq-dev \
       gcc \
    # 清理 apt 快取以縮小映像檔大小
    && rm -rf /var/lib/apt/lists/*

# 更新 pip
RUN pip install --upgrade pip

# 複製 requirements.txt 到工作目錄
# 先複製和安裝依賴，可以利用 Docker 的快取機制，
# 只要 requirements.txt 沒變，之後重新 build 時就不會重新安裝套件。
COPY requirements.txt .

# 安裝 Python 依賴套件
# --no-cache-dir 可以減少映像檔大小
RUN pip install --no-cache-dir -r requirements.txt

# 複製整個專案的程式碼到工作目錄
# .dockerignore 檔案會控制哪些檔案/資料夾「不要」被複製進去
COPY . .

# 複製模型檔案 (假設你的模型放在專案根目錄下的 ml_models 資料夾)
# 確保 apps.py 中讀取的也是容器內的這個路徑 (例如 相對於 /app)
COPY ./yolo/best.pt ./yolo/best.pt

# 執行 Django collectstatic
# 需要先設定 STATIC_ROOT，確保你的 settings.py 有設定
# 例如：STATIC_ROOT = BASE_DIR / 'staticfiles'
# 如果執行 manage.py 需要環境變數，可以在這裡用 ENV 設定
# ENV DJANGO_SETTINGS_MODULE=main_project.settings
RUN python manage.py collectstatic --noinput --clear

# 公開 Gunicorn 預計使用的端口
EXPOSE 8000

# 容器啟動時運行的預設指令
# 使用 Gunicorn 來運行你的 Django WSGI 應用
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "detector_project.wsgi:application"]
