# detector/api/serializers.py (完整修正版)

from rest_framework import serializers
from ..models import DetectionRecord, BatchDetectionJob # <-- 匯入 models

class S3FolderProcessRequestSerializer(serializers.Serializer):
    """
    (使用者原有的) 用於 /api/process/process_s3_folder/ 請求的序列化器。
    """
    s3_bucket_name = serializers.CharField(max_length=255)
    s3_folder_prefix = serializers.CharField(max_length=1024)

# --- 以下為修正後的 Serializers ---

class DetectionRecordListSerializer(serializers.ModelSerializer):
    """
    用於辨識紀錄列表 (手動上傳歷史) 的序列化器 (簡化版)
    """
    # 【修正】明確定義 URL 欄位名稱，並使用 'source' 指向 model 欄位
    original_image_url = serializers.ImageField(source='original_image', read_only=True)
    
    class Meta:
        model = DetectionRecord
        fields = [
            'id', 
            'uploaded_at',
            'severity_score', 
            'original_image_url'  # 【修正】使用新的 URL 欄位
        ]


class DetectionRecordDetailSerializer(serializers.ModelSerializer):
    """
    用於單筆辨識紀錄詳細資料的序列化器
    (供 'upload_images', 'get_record_detail' 和 'BatchDetectionJobDetailSerializer' 使用)
    """
    # 【修正】明確定義 URL 欄位名稱，以匹配 Vue 組件 (ResultCard.vue) 的期望
    original_image_url = serializers.ImageField(source='original_image', read_only=True)
    annotated_image_url = serializers.ImageField(source='annotated_image', read_only=True)
    # 【修正】將 ForeignKey 'batch_job' 序列化為其 ID
    batch_job_id = serializers.PrimaryKeyRelatedField(source='batch_job', read_only=True)

    class Meta:
        model = DetectionRecord
        fields = [
            'id', 
            'uploaded_at',
            'results_data',
            'severity_score',
            'original_image_url',   # 【修正】使用新的 URL 欄位
            'annotated_image_url',  # 【修正】使用新的 URL 欄位
            'batch_job_id',         # 【修正】使用 'batch_job_id'，方便前端跳轉
        ]

class BatchDetectionJobListSerializer(serializers.ModelSerializer):
    """
    用於批次任務列表的序列化器 (簡化版)
    (這個序列化器是 OK 的，保持原樣)
    """
    class Meta:
        model = BatchDetectionJob
        fields = [
            'id', 
            'created_at',
            'updated_at',
            'status', 
            's3_bucket_name',      # 【修正】補上 s3_bucket_name 欄位
            's3_folder_prefix', 
            'total_images_found',
            'images_processed_successfully',
            'images_failed_to_process', # 【修正】補上 images_failed_to_process 欄位
            'error_message',
        ]

class BatchDetectionJobDetailSerializer(serializers.ModelSerializer):
    """
    用於單筆批次任務詳細資料 (包含其所有辨識紀錄)
    """
    # 【重大修正】 
    # 應使用 'DetectionRecordDetailSerializer' (詳細版) 
    # 才能獲取 'annotated_image_url' 和 'results_data' 等所有欄位
    detection_records = DetectionRecordDetailSerializer(many=True, read_only=True) 

    class Meta:
        model = BatchDetectionJob
        fields = [
            'id', 
            'created_at',
            'updated_at',
            'status', 
            's3_bucket_name',      # 【修正】補上 s3_bucket_name
            's3_folder_prefix', 
            'total_images_found',
            'images_processed_successfully',
            'images_failed_to_process', # 【修正】補上 images_failed_to_process
            'summary_results',
            'error_message',
            'detection_records'    # 欄位名稱 'detection_records' 是正確的
        ]