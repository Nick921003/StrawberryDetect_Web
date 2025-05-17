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
        on_delete=models.SET_NULL,
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
            self.severity_score = None # 或者 0.0 如果你希望無檢測結果視為無嚴重性
            return

        # --- 評分參數設定  ---
        BASE_SCORE_HEALTHY = 0.05
        BASE_SCORE_ANGULAR_LEAF_SPOT = 0.4 # 檢測到角斑病的基礎分
        
        # 信心度對評分的影響因子 (0 到 1 之間，越高則信心度影響越大)
        CONFIDENCE_FACTOR_ANGULAR = 0.6 
        
        # 如果一張圖中有多個角斑病檢測框，每個額外框增加的分數 (可以設為0如果不考慮數量)
        PER_DETECTION_BONUS_ANGULAR = 0.05 # 暫不使用，簡化邏輯

        # --- 初始化 ---
        final_score = 0.0
        is_healthy_detected = False
        highest_healthy_confidence = 0.0
        
        angular_leaf_spot_detections = []

        # --- 遍歷所有檢測結果 ---
        for detection in self.results_data:
            class_name = detection.get('class', '').strip().lower() # strip() 去除前後空格
            confidence = detection.get('confidence_float', 0.0)

            if class_name == 'healthy':
                is_healthy_detected = True
                if confidence > highest_healthy_confidence:
                    highest_healthy_confidence = confidence
            
            elif class_name == 'angular leaf spot':
                angular_leaf_spot_detections.append(confidence) # 收集所有角斑病的信心度

        # --- 計算最終評分 ---
        if angular_leaf_spot_detections:
            # 如果檢測到角斑病
            current_disease_score = BASE_SCORE_ANGULAR_LEAF_SPOT
            
            # 取信心度最高的那個角斑病檢測作為主要評分依據
            if angular_leaf_spot_detections:
                max_confidence_angular = max(angular_leaf_spot_detections)
                # 信心度加權：(信心度 * 影響因子) 作為額外加分
                current_disease_score += max_confidence_angular * CONFIDENCE_FACTOR_ANGULAR
            
            # 如果考慮數量 (可選，目前註釋掉的 PER_DETECTION_BONUS_ANGULAR)
            current_disease_score += (len(angular_leaf_spot_detections) -1) * PER_DETECTION_BONUS_ANGULAR if len(angular_leaf_spot_detections) > 0 else 0

            final_score = current_disease_score
            
        elif is_healthy_detected:
            # 如果只檢測到健康 (沒有檢測到任何角斑病)
            # 可以讓健康的信心度稍微降低一點點總分 (如果final_score之前被其他輕微問題加分了)
            # 或者直接給一個固定的健康分數
            final_score = max(0, final_score - highest_healthy_confidence * 0.05)

        else:
            # 既沒有角斑病，也沒有明確的健康標籤，但 results_data 不為空
            # (這種情況在你的模型只有兩個類別時比較少見，除非信心度都很低沒有任何輸出)
            if self.results_data: # 確認 results_data 確實有內容但沒匹配上
                final_score = 0.2 # 給一個較低的不確定分數
            else: # results_data 為空 (YOLO 沒檢測到任何東西)
                self.severity_score = None # 或者 0.0
                return
        
        # --- 標準化分數到 0.0 - 1.0 範圍 ---
        self.severity_score = min(max(final_score, 0.0), 1.0)
        
        # 四捨五入到小數點後兩位 (可選)
        if self.severity_score is not None:
            self.severity_score = round(self.severity_score, 2)

    def save(self, *args, **kwargs):
        self.calculate_severity_score()
        super().save(*args, **kwargs)

    # (重要) 覆寫 delete 方法，以便在刪除資料庫記錄時，也刪除對應的圖片檔案
    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
