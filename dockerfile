# 使用官方 Python 作為基礎映像 (選擇與你環境相近的版本，例如 3.10 或 3.12)
# slim 版本比較小
FROM python:3.12-slim

# --- 環境變數 ---
# 設定 Python 相關環境變數
ENV PYTHONDONTWRITEBYTECODE 1  # 防止 Python 寫入 .pyc 文件
ENV PYTHONUNBUFFERED 1      # 讓 Python 的輸出直接打印到終端，方便看 Log
# 設定 Django settings 模組 (如果 manage.py 或 wsgi.py 需要)
# ENV DJANGO_SETTINGS_MODULE=detector_project.settings # 取消註解並改成你的 settings 路徑
# 設定 Gunicorn worker 數量 (可選，也可以在 CMD 或運行時指定)
# ENV WEB_CONCURRENCY=4 # 範例：設定 4 個 worker

# --- 工作目錄 ---
# 設定容器內的工作目錄
WORKDIR /app

# --- 系統依賴 ---
# 更新 apt 套件列表並安裝必要的系統依賴
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
       # opencv-python-headless 可能需要的圖形庫
       libgl1-mesa-glx \
       libglib2.0-0 \
       # psycopg2 (非 binary) 可能需要的編譯工具和函式庫
       libpq-dev \
       gcc \
    # 清理 apt 快取以縮小映像檔大小
    && rm -rf /var/lib/apt/lists/*

# --- Python 依賴 ---
# 升級 pip
RUN pip install --upgrade pip

# --- 安裝 CPU 版本的 PyTorch 和 Torchvision ---
RUN pip install --no-cache-dir torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cpu

# 複製 requirements.txt
COPY requirements.txt .

# 安裝 Python 依賴
RUN pip install --no-cache-dir -r requirements.txt

# --- 複製應用程式程式碼 ---
# 將目前目錄 (.) 的所有內容 (根據 .dockerignore 排除的檔案除外) 複製到容器的 /app 目錄
# 放在 pip install 之後，以利用快取
COPY . .

# --- 複製模型檔案 ---
# 複製 YOLO 模型檔案到指定路徑
COPY ./yolo/best.pt ./yolo/best.pt

# --- 建立非 Root 使用者 ---
# 建立一個名為 appuser 的非特權使用者和群組
RUN addgroup --system appuser && adduser --system --ingroup appuser appuser
# 將工作目錄 /app 及其所有內容的擁有者變更給 appuser
# 這樣 appuser 對複製進來的程式碼和模型檔案有權限
RUN chown -R appuser:appuser /app

# --- Django 靜態檔案 ---
# 切換到 appuser 來執行 collectstatic 和 CMD
USER appuser
RUN python manage.py collectstatic --noinput --clear

# --- 端口暴露 ---
# 聲明容器預計監聽的端口 (Gunicorn 將綁定此端口)
EXPOSE 8000

# --- 啟動命令 ---
# 使用 Gunicorn 運行 Django WSGI 應用 (會以 appuser 身份運行)
# 這裡保留了你設定的 4 個 worker
CMD ["sh", "-c", "python manage.py migrate && gunicorn --bind 0.0.0.0:8000 -w 4 detector_project.wsgi:application"]
# 如果不想指定 worker 數量，可以使用下面這行
# CMD ["gunicorn", "--bind", "0.0.0.0:8000", "detector_project.wsgi:application"]
