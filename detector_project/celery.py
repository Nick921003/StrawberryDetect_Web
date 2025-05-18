# detector_project/celery.py
import os
from celery import Celery
import django

# 設定 Django 的 settings 模組給 Celery。
# 'detector_project' 應替換為你的專案名稱。
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'detector_project.settings')
django.setup()
app = Celery('detector_project')

# 使用 Django settings.py 中的設定來配置 Celery。
# 'CELERY_' 開頭的設定會被自動載入。
app.config_from_object('django.conf:settings', namespace='CELERY')

# 自動從所有已註冊的 Django app 中載入 tasks.py 檔案。
app.autodiscover_tasks()

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')