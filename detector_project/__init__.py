# detector_project/__init__.py
from __future__ import absolute_import, unicode_literals

# 這將確保 app 總是在 Django 啟動時被匯入，
# 這樣 @shared_task 裝飾器才能使用它。
from .celery import app as celery_app

__all__ = ('celery_app',)