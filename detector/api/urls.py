# detector/api/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DetectionViewSet # <-- 匯入我們修改後的 ViewSet

# 使用 DefaultRouter 來自動產生 ViewSet 的 URL
# 它會處理 /api/process/, /api/process/upload/, /api/process/history/manual/ 等
router = DefaultRouter()
router.register(r'process', DetectionViewSet, basename='process')

# router.urls S3
# GET /api/process/history/manual/
# GET /api/process/history/batch/
# GET /api/process/record/<uuid:record_id>/
# GET /api/process/batch/<uuid:batch_id>/
# POST /api/process/upload/
# POST /api/process/process_s3_folder/

urlpatterns = [
    path('', include(router.urls)),
]