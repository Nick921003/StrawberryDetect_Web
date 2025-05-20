# 使用官方 Python 3.12 slim 作為基礎映像
FROM python:3.12-slim

# ====== 環境變數 ======
# 不產生 .pyc 檔
ENV PYTHONDONTWRITEBYTECODE=1
# 立即輸出 log
ENV PYTHONUNBUFFERED=1
# ENV DJANGO_SETTINGS_MODULE=detector_project.settings  # 如需自訂 settings 可取消註解
# ENV WEB_CONCURRENCY=4  # Gunicorn worker 數量（可選）

# ====== 設定工作目錄 ======
WORKDIR /app

# ====== 安裝系統依賴 ======
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1-mesa-glx \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# ====== 安裝 Python 依賴 ======
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir ultralytics==8.3.130 && \
    pip install --no-cache-dir -r requirements.txt

# ====== 複製專案程式碼 ======
COPY . .

# ====== 建立非 root 使用者並調整權限 ======
RUN addgroup --system appuser && adduser --system --ingroup appuser appuser && \
    chown -R appuser:appuser /app

# ====== 收集 Django 靜態檔案 ======
USER appuser
RUN python manage.py collectstatic --noinput --clear

# ====== 容器監聽端口 ======
EXPOSE 8000

# ====== 啟動指令（預設用 Gunicorn） ======
CMD ["sh", "-c", "python manage.py migrate && gunicorn --preload --bind 0.0.0.0:8000 -w 4 detector_project.wsgi:application"]
