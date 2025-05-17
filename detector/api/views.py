# detector/api/views.py
# import base64 # 這個 view action 不直接用 base64
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
import logging
from ..tasks import process_s3_folder_task # <-- 匯入的是我們修改過的 task
from .serializers import S3FolderProcessRequestSerializer

logger = logging.getLogger(__name__)

class DetectionViewSet(viewsets.ViewSet):
    """
    使用 ViewSet，把多個 related actions 都放一起。
    """

    @action(detail=False, methods=['post'], url_path='process_s3_folder')
    def process_s3_folder(self, request):
        """
        POST /api/process/process_s3_folder/
        body: { "s3_bucket_name": "your-bucket", "s3_folder_prefix": "path/to/images_folder/" }
        接收 S3 資料夾資訊，非同步觸發批次辨識任務。
        """
        serializer = S3FolderProcessRequestSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Invalid S3 folder process request: {serializer.errors}") # 增加日誌
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        s3_bucket = serializer.validated_data['s3_bucket_name']
        s3_prefix = serializer.validated_data['s3_folder_prefix']

        # 呼叫 Celery 批次處理任務
        # process_s3_folder_task 是我們在 tasks.py 中修改過的函式
        # 它內部會處理 BatchDetectionJob 的創建
        task = process_s3_folder_task.delay(s3_bucket, s3_prefix)
        
        logger.info(f"S3 folder processing task sent to Celery for s3://{s3_bucket}/{s3_prefix}. Celery Task ID: {task.id}")

        # 立即回傳，告知客戶端任務已提交
        # 我們可以考慮在回傳中也包含 BatchDetectionJob 的 ID (如果能立即獲取)
        # 但由於 BatchDetectionJob 是在 task 內部異步創建的，這裡直接返回 Celery task ID 是標準做法
        # 未來如果需要在 API 返回 BatchDetectionJob ID，則 process_s3_folder_task 需要同步創建 BatchDetectionJob
        # 或者 API 輪詢 Celery task 結果來獲取。目前的設計是 task 內部創建。
        
        return Response({
            'message': f'S3 資料夾 (s3://{s3_bucket}/{s3_prefix}) 的批次處理任務已提交，正在背景執行。',
            'celery_task_id': task.id # 回傳的是 Celery 任務的 ID
        }, status=status.HTTP_202_ACCEPTED)