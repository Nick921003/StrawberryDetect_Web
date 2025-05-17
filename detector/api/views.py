# detector/api/views.py
import base64
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
import logging
from ..tasks import process_s3_folder_task # <-- 匯入新的批次任務
from .serializers import S3FolderProcessRequestSerializer # <-- 匯入新的 Serializer
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
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        s3_bucket = serializer.validated_data['s3_bucket_name']
        s3_prefix = serializer.validated_data['s3_folder_prefix']

        # 呼叫 Celery 批次處理任務
        task = process_s3_folder_task.delay(s3_bucket, s3_prefix)
        logger.info(f"S3 folder processing task sent to Celery for s3://{s3_bucket}/{s3_prefix}. Task ID: {task.id}")

        # 立即回傳，告知客戶端任務已提交
        return Response({
            'message': f'S3 資料夾 (s3://{s3_bucket}/{s3_prefix}) 的批次處理任務已提交，正在背景執行。',
            'batch_task_id': task.id # 回傳批次任務的 ID
        }, status=status.HTTP_202_ACCEPTED)