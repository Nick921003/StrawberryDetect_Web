from rest_framework.routers import DefaultRouter
from .views import DetectionViewSet

router = DefaultRouter()
# 路徑前綴為 'process'，對應到 DetectionViewSet.process
router.register(r'process', DetectionViewSet, basename='detection')

urlpatterns = router.urls
