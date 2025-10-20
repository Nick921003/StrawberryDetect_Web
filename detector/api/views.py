# detector/api/views.py

from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser # <-- 匯入檔案上傳 parser
from rest_framework.pagination import PageNumberPagination # <-- 匯入分頁
from django.shortcuts import get_object_or_404 # <-- 匯入
import logging
import os # <-- 【新增】 匯入 os (雖然 upload_images 中有用到但好像忘了 import)

from rest_framework.parsers import MultiPartParser, FormParser, JSONParser # <-- 在檔案頂部加入 JSONParser
from ..tasks import process_s3_folder_task
from ..services import process_image_bytes # <-- 匯入核心處理邏輯
from ..models import DetectionRecord, BatchDetectionJob # <-- 匯入 models

# --- 【新增 import】 ---
from django.conf import settings 
from ..retention_manager import DataRetentionManager
# --- 【新增 import 結束】 ---

from .serializers import ( # <-- 匯入我們即將建立的 Serializers
    S3FolderProcessRequestSerializer,
    DetectionRecordDetailSerializer,
    DetectionRecordListSerializer,
    BatchDetectionJobListSerializer,
    BatchDetectionJobDetailSerializer
)

logger = logging.getLogger(__name__)

# --- (新增) 標準分頁類別 ---
class StandardResultsSetPagination(PageNumberPagination):
    """
    用於 API 列表的標準分頁設定
    """
    page_size = 1 # 預設每頁 10 筆
    page_size_query_param = 'page_size' # 允許客戶端用 ?page_size= 參數覆寫
    max_page_size = 50 # 最大每頁 50 筆


class DetectionViewSet(viewsets.ViewSet):
    """
    統一處理所有 API 請求的 ViewSet。
    ... (省略註解) ...
    """
    
    # 為 'upload_images' action 指定 parsers
    # S3FolderProcessRequestSerializer 會使用預設的 JSONParser
    parser_classes = [MultiPartParser, FormParser] 
    pagination_class = StandardResultsSetPagination # 套用分頁

    # --- (新增) 分頁輔助函式 ---
    @property
    def paginator(self):
        if not hasattr(self, '_paginator'):
            if self.pagination_class is None:
                self._paginator = None
            else:
                self._paginator = self.pagination_class()
        return self._paginator

    def paginate_queryset(self, queryset):
        if self.paginator is None:
            return None
        return self.paginator.paginate_queryset(queryset, self.request, view=self)

    def get_paginated_response(self, data):
        assert self.paginator is not None
        return self.paginator.get_paginated_response(data)

    
    # --- (使用者原有的 Action) ---
    @action(detail=False, methods=['post'], url_path='process_s3_folder', parser_classes=[JSONParser]) # 指定此 action 不使用檔案 parser
    def process_s3_folder(self, request):
        """
        POST /api/process/process_s3_folder/
        (自走車流程) 觸發 S3 批次辨識任務
        """
        serializer = S3FolderProcessRequestSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Invalid S3 folder process request: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        s3_bucket = serializer.validated_data['s3_bucket_name']
        s3_prefix = serializer.validated_data['s3_folder_prefix']

        # 呼叫 Celery 批次處理任務
        # 【修正】使用 .s() 傳遞參數，確保任務簽章正確
        task = process_s3_folder_task.s(s3_bucket, s3_prefix).apply_async()
        
        logger.info(f"S3 folder processing task sent to Celery for s3://{s3_bucket}/{s3_prefix}. Celery Task ID: {task.id}")

        return Response({
            'message': f'S3 資料夾 (s3://{s3_bucket}/{s3_prefix}) 的批次處理任務已提交，正在背景執行。',
            'celery_task_id': task.id # 【修正】使用 task.id (apply_async 回傳的是 AsyncResult)
        }, status=status.HTTP_202_ACCEPTED)

    
    # --- (新增) 功能一 & 二: 手動上傳 (單張或多張) ---
    @action(detail=False, methods=['post'], url_path='upload')
    def upload_images(self, request):
        """
        POST /api/process/upload/
        (手動上傳) 接收單張或多張圖片 (最多 5 張)
        """
        # 'images' S3'upload_form.html' S3 <input name="images">
        images = request.FILES.getlist('images') 

        if not images:
            return Response({'error': '沒有提供圖片檔案。'}, status=status.HTTP_400_BAD_REQUEST)
        
        # 限制 5 張 (如您所述)
        if len(images) > 5:
            return Response({'error': f'一次最多只能上傳 5 張圖片，您上傳了 {len(images)} 張。'}, status=status.HTTP_400_BAD_REQUEST)

        results = []
        for uploaded_file in images:
            try:
                image_bytes = uploaded_file.read()
                # 從檔案名稱獲取副檔名 (例如: .png, .jpg)
                # 【修正】使用 os.path.splitext 更安全
                extension = os.path.splitext(uploaded_file.name)[1].lower()
                if extension not in ['.jpg', '.jpeg', '.png']:
                        logger.warning(f"Skipping invalid file type: {uploaded_file.name}")
                        continue 

                # 創建紀錄實例 (手動上傳，batch_job=None)
                manual_record_instance = DetectionRecord() 
                
                # 呼叫您在 services.py 中的核心邏輯
                # (此服務會處理模型推論、S3 上傳、儲存紀錄)
                process_image_bytes(
                    detection_record_instance=manual_record_instance,
                    image_bytes=image_bytes,
                    file_ext=extension
                )
                
                results.append(manual_record_instance)

            except Exception as e:
                logger.error(f"Error processing uploaded image {uploaded_file.name}: {e}", exc_info=True)
                # 即使一張失敗，也繼續處理下一張
        
        if not results:
             return Response({'error': '所有圖片處理失敗或檔案格式不符。'}, status=status.HTTP_400_BAD_REQUEST)

        # 使用 Detail Serializer S3 S3
        serializer = DetectionRecordDetailSerializer(results, many=True)
        
        # --- 【在這裡加入即時清理】 ---
        try:
            logger.info(f"Triggering immediate manual cleanup (keep={settings.MANUAL_RECORDS_TO_KEEP})...")
            manager = DataRetentionManager()
            deleted_count_info = manager.run_immediate_manual_cleanup()
            logger.info(f"Immediate manual cleanup complete. Details: {deleted_count_info}")
        except Exception as e:
            # 清理失敗不應影響 API 回應，僅記錄錯誤
            logger.error(f"Error during immediate manual cleanup: {e}", exc_info=True)
        # --- 【加入結束】 ---

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # --- (新增) API: 獲取手動上傳歷史列表 (分頁) ---
    @action(detail=False, methods=['get'], url_path='history/manual')
    def get_manual_history(self, request):
        """
        GET /api/process/history/manual/
        Gets the list of manually uploaded detection records (paginated).
        """
        # --- ↓↓↓ Correct the field name in order_by ↓↓↓ ---
        queryset = DetectionRecord.objects.filter(batch_job__isnull=True).order_by('-uploaded_at') # <-- Change '-timestamp' to '-uploaded_at'
        # --- ↑↑↑ Correction ends ↑↑↑ ---
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = DetectionRecordListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = DetectionRecordListSerializer(queryset, many=True)
        return Response(serializer.data)

    # --- (新增) API: 獲取批次任務歷史列表 (分頁) ---
    @action(detail=False, methods=['get'], url_path='history/batch')
    def get_batch_history(self, request):
        """
        GET /api/process/history/batch/
        獲取所有批次任務的列表 (分頁)
        """
        queryset = BatchDetectionJob.objects.all().order_by('-created_at')
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = BatchDetectionJobListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = BatchDetectionJobListSerializer(queryset, many=True)
        return Response(serializer.data)

    # --- (新增) API: 獲取單筆辨識紀錄詳情 ---
    @action(detail=False, methods=['get'], url_path='record/(?P<record_id>[^/.]+)')
    def get_record_detail(self, request, record_id=None):
        """
        GET /api/process/record/<uuid:record_id>/
        獲取單筆辨識紀錄的詳細資訊 (手動或批次皆可)
        """
        record = get_object_or_404(DetectionRecord, id=record_id)
        serializer = DetectionRecordDetailSerializer(record)
        return Response(serializer.data)

    # --- (新增) API: 獲取單筆批次任務詳情 (包含其所有辨識紀錄) ---
    @action(detail=False, methods=['get'], url_path='batch/(?P<batch_id>[^/.]+)')
    def get_batch_detail(self, request, batch_id=None):
        """
        GET /api/process/batch/<uuid:batch_id>/
        獲取單筆批次任務的詳細資訊 (包含其所有辨識紀錄)
        """
        # 使用 prefetch_related 來避免 N+1 問題
        batch_job = get_object_or_404(BatchDetectionJob.objects.prefetch_related('detection_records'), id=batch_id)
        serializer = BatchDetectionJobDetailSerializer(batch_job)
        return Response(serializer.data)