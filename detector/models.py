from django.db import models
import uuid # 用於產生不會重複的 ID
import os
from django.utils import timezone

class BatchDetectionJob(models.Model):
    """
    代表一次對 S3 資料夾中所有圖片的批次辨識任務。
    """
    class StatusChoices(models.TextChoices):
        PENDING = 'PENDING', '待處理'
        PROCESSING = 'PROCESSING', '處理中'
        COMPLETED = 'COMPLETED', '已完成'
        PARTIAL_COMPLETION = 'PARTIAL_COMPLETION', '部分完成' # 當批次中部分圖片處理失敗時
        FAILED = 'FAILED', '失敗' # 整個批次任務啟動或執行時發生嚴重錯誤

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="批次任務 ID")
    celery_task_id = models.CharField(max_length=255, blank=True, null=True, verbose_name="Celery 批次任務 ID", help_text="觸發此批次的主 Celery 任務 ID (process_s3_folder_task)")

    s3_bucket_name = models.CharField(max_length=255, verbose_name="S3 儲存桶名稱")
    s3_folder_prefix = models.CharField(max_length=1024, verbose_name="S3 資料夾路徑")

    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING,
        verbose_name="批次狀態"
    )

    total_images_found = models.IntegerField(default=0, verbose_name="找到的圖片總數")
    images_processed_successfully = models.IntegerField(default=0, verbose_name="成功處理圖片數")
    images_failed_to_process = models.IntegerField(default=0, verbose_name="處理失敗圖片數")

    # 用於儲存整個批次的摘要結果，例如整體健康狀況描述、各類病害的統計數字等
    summary_results = models.JSONField(null=True, blank=True, verbose_name="批次摘要結果")
    # 如果整個批次任務本身執行失敗（例如 S3 無法訪問），記錄錯誤訊息
    error_message = models.TextField(blank=True, null=True, verbose_name="批次錯誤訊息")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="建立時間")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="最後更新時間")

    def __str__(self):
        return f"批次任務 {self.id} ({self.s3_folder_prefix}) - {self.get_status_display()}"

    class Meta:
        ordering = ['-created_at']
        verbose_name = "批次辨識任務"
        verbose_name_plural = "批次辨識任務"

def get_original_image_upload_path(instance, filename):
    """決定原始圖片的上傳路徑"""
    if instance.batch_job_id: # 檢查是否有 batch_job_id (避免在 instance.batch_job 未儲存前就訪問)
        # 批次上傳路徑
        return os.path.join('uploads', f'batch_{instance.batch_job_id}', 'original', filename)
    else:
        # 手動上傳路徑
        now = timezone.now()
        return os.path.join('uploads', 'manual', now.strftime('%Y'), now.strftime('%m'), now.strftime('%d'), filename)

def get_annotated_image_upload_path(instance, filename):
    """決定標註後圖片的上傳路徑"""
    if instance.batch_job_id:
        # 批次結果路徑
        return os.path.join('results', f'batch_{instance.batch_job_id}', 'annotated', filename)
    else:
        # 手動結果路徑
        now = timezone.now()
        return os.path.join('results', 'manual', now.strftime('%Y'), now.strftime('%m'), now.strftime('%d'), filename)

class DetectionRecord(models.Model):
    # ... (id, batch_job 欄位保持不變) ...
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch_job = models.ForeignKey(
        BatchDetectionJob,
        on_delete=models.CASCADE, # 刪除批次任務時，刪除所有相關的辨識紀錄
        null=True,
        blank=True,
        related_name='detection_records',
        verbose_name="所屬批次任務"
    )

    # 修改 ImageField 的 upload_to 參數
    original_image = models.ImageField(
        upload_to=get_original_image_upload_path, # 使用我們定義的函式
        verbose_name="原始圖片"
    )
    annotated_image = models.ImageField(
        upload_to=get_annotated_image_upload_path, # 使用我們定義的函式
        null=True, blank=True,
        verbose_name="標註結果圖"
    )

    # ... (results_data, severity_score, uploaded_at, __str__, Meta, calculate_severity_score, save 方法保持不變) ...
    results_data = models.JSONField(
        null=True, blank=True,
        verbose_name="辨識結果數據"
    )
    severity_score = models.FloatField(
        null=True,
        blank=True,
        verbose_name="嚴重程度評分",
        help_text="數值越高代表越嚴重 (例如 0.0 至 1.0)"
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="上傳時間"
    )

    def __str__(self):
        if self.batch_job:
            return f"辨識紀錄 (批次 {self.batch_job_id} - {self.id})"
        return f"辨識紀錄 ({self.id} - 上傳於 {self.uploaded_at.strftime('%Y-%m-%d %H:%M')})"

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = "辨識紀錄"
        verbose_name_plural = "辨識紀錄"

    def calculate_severity_score(self):
        if not self.results_data:
            self.severity_score = None
            return

        # 可擴展的 class 參數設定
        CLASS_PARAMS = {
            'angular leaf spot': {
                'base': 0.4,
                'confidence_factor': 0.6,
                'per_detection_bonus': 0.05,
            },
            'healthy': {
                'base': 0.05,
                'confidence_factor': 0.05,
                'per_detection_bonus': 0.0,
            },
            # 其他病害可在此擴充
        }

        # 統計每個 class 的 confidence
        class_confidences = {}
        for detection in self.results_data:
            class_name = detection.get('class', '').strip().lower()
            confidence = detection.get('confidence_float', 0.0)
            class_confidences.setdefault(class_name, []).append(confidence)

        # 先處理所有病害類別（排除 healthy）
        disease_scores = []
        for cls, params in CLASS_PARAMS.items():
            if cls == 'healthy':
                continue
            if cls in class_confidences:
                confs = class_confidences[cls]
                score = params['base']
                if confs:
                    score += max(confs) * params['confidence_factor']
                    score += (len(confs) - 1) * params['per_detection_bonus'] if len(confs) > 0 else 0
                disease_scores.append(score)

        # 取所有病害分數的最大值（最嚴重的病害為主）
        if disease_scores:
            final_score = max(disease_scores)
        elif 'healthy' in class_confidences:
            # 只檢測到 healthy
            healthy_confs = class_confidences['healthy']
            final_score = CLASS_PARAMS['healthy']['base']
            if healthy_confs:
                final_score = max(0, final_score - max(healthy_confs) * CLASS_PARAMS['healthy']['confidence_factor'])
        else:
            # 既沒有病害也沒有 healthy，但有其他未知類別
            final_score = 0.2

        # 標準化分數到 0.0 - 1.0
        self.severity_score = min(max(final_score, 0.0), 1.0)
        if self.severity_score is not None:
            self.severity_score = round(self.severity_score, 2)

    def save(self, *args, **kwargs):
        self.calculate_severity_score()
        super().save(*args, **kwargs)

    # (重要) 覆寫 delete 方法，以便在刪除資料庫記錄時，也刪除對應的圖片檔案
    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
