import os
from django.apps import AppConfig
from django.conf import settings
from ultralytics import YOLO
import logging

app_logger = logging.getLogger(__name__)

class DetectorConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'detector'

    # 將 yolo_model 初始化為類別的屬性
    yolo_model = None

    def ready(self):
        """
        當 Django 應用程式準備就緒時，此方法會被呼叫。
        這是載入模型的最佳時機。
        """
        # 檢查模型是否已經被載入，避免重複載入
        if DetectorConfig.yolo_model is None:
            app_logger.info("YOLO model loading initiated...")
            try:
                MODEL_PATH = os.path.join(settings.BASE_DIR, "yolo", "best.pt")
                
                if not os.path.exists(MODEL_PATH):
                    app_logger.error(f"CRITICAL: YOLO model file not found at {MODEL_PATH}")
                    return 

                # 將載入的模型指派給類別的屬性，而不是全局變數
                DetectorConfig.yolo_model = YOLO(MODEL_PATH)
                app_logger.info(f"YOLO model loaded successfully from {MODEL_PATH}")

            except Exception as e:
                app_logger.error(f"CRITICAL: Failed to load YOLO model: {e}", exc_info=True)
                # 即使失敗，也確保屬性存在，只是值為 None
                DetectorConfig.yolo_model = None