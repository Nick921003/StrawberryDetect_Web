# detector/retention_manager.py
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import logging
from .models import DetectionRecord, BatchDetectionJob

logger = logging.getLogger(__name__)

class DataRetentionManager:
    """
    管理 DetectionRecord 和 BatchDetectionJob 的數據保留策略。
    """

    def _get_setting(self, setting_name, default_value):
        """輔助函式，從 settings 獲取配置，若無則使用預設值。"""
        return getattr(settings, setting_name, default_value)
    
    def cleanup_manual_records_by_time(self, log_prefix=""):
        """
        按時間清理手動上傳的 DetectionRecord，只保留 X 天內的資料。
        X 從 settings.DAYS_TO_KEEP_MANUAL_RECORDS 讀取。
        """
        deleted_count = 0
        try:
            days_to_keep = self._get_setting('DAYS_TO_KEEP_MANUAL_RECORDS', 30)
            cutoff_date = timezone.now() - timedelta(days=days_to_keep)
            manual_records_qs = DetectionRecord.objects.filter(
                batch_job__isnull=True,
                uploaded_at__lt=cutoff_date
            )
            count_to_delete = manual_records_qs.count()
            logger.info(f"{log_prefix} [按時間清理手動紀錄] 找到 {count_to_delete} 筆早於 {cutoff_date.strftime('%Y-%m-%d')} (保留 {days_to_keep} 天)。")
            if count_to_delete > 0:
                info = manual_records_qs.delete()
                deleted_count = info[0] if isinstance(info, tuple) else 0
                logger.info(f"{log_prefix} [按時間清理手動紀錄] 成功刪除 {deleted_count} 筆。詳情: {info}")
            else:
                logger.info(f"{log_prefix} [按時間清理手動紀錄] 無需刪除。")
        except Exception as e:
            logger.error(f"{log_prefix} [按時間清理手動紀錄] 發生錯誤: {e}", exc_info=True)
        return deleted_count

    def cleanup_manual_records_by_count(self, log_prefix=""):
        """
        只保留最新 N 筆手動上傳的 DetectionRecord (batch_job__isnull=True)。
        N 由 settings.MANUAL_RECORDS_TO_KEEP 決定。
        """
        records_to_keep = self._get_setting('MANUAL_RECORDS_TO_KEEP', 10)
        deleted_count = 0
        try:
            manual_records_qs = DetectionRecord.objects.filter(batch_job__isnull=True).order_by('-uploaded_at')
            total_manual_records = manual_records_qs.count()
            logger.info(f"{log_prefix} [手動記錄-數量清理] 設定保留: {records_to_keep} 筆, 目前有: {total_manual_records} 筆。")

            if total_manual_records > records_to_keep:
                num_to_delete = total_manual_records - records_to_keep
                ids_to_delete = list(manual_records_qs.values_list('id', flat=True)[records_to_keep:])
                if ids_to_delete:
                    logger.info(f"{log_prefix} [手動記錄-數量清理] 刪除 {num_to_delete} 筆 (IDs: {ids_to_delete[:5]}...)")
                    info = DetectionRecord.objects.filter(id__in=ids_to_delete).delete()
                    deleted_count = info[0] if isinstance(info, tuple) else 0
                    logger.info(f"{log_prefix} [手動記錄-數量清理] 已刪除 {deleted_count} 筆。")
                else:
                    logger.info(f"{log_prefix} [手動記錄-數量清理] 無需刪除 (ids_to_delete 為空)。")
            else:
                logger.info(f"{log_prefix} [手動記錄-數量清理] 無需刪除 ({total_manual_records} <= {records_to_keep})。")
        except Exception as e:
            logger.error(f"{log_prefix} [手動記錄-數量清理] 清理時發生錯誤: {e}", exc_info=True)
        return deleted_count

    def cleanup_batch_jobs_by_time(self, log_prefix=""):
        """
        按時間清理 BatchDetectionJob，刪除超過設定天數的舊批次。
        """
        deleted_count = 0
        try:
            days_to_keep = self._get_setting('DAYS_TO_KEEP_BATCHES', 30)
            cutoff_date = timezone.now() - timedelta(days=days_to_keep)
            
            batch_jobs_to_delete_qs = BatchDetectionJob.objects.filter(
                created_at__lt=cutoff_date,
                status__in=[ # 只清理已處於最終狀態的批次
                    BatchDetectionJob.StatusChoices.COMPLETED,
                    BatchDetectionJob.StatusChoices.FAILED,
                    BatchDetectionJob.StatusChoices.PARTIAL_COMPLETION,
                    BatchDetectionJob.StatusChoices.PROCESSING,
                
                ]
            )
            count_to_delete = batch_jobs_to_delete_qs.count()
            logger.info(f"{log_prefix} [按時間清理批次] 找到 {count_to_delete} 個批次早于 {cutoff_date.strftime('%Y-%m-%d')} (保留 {days_to_keep} 天)。")

            if count_to_delete > 0:
                # 假設 on_delete=models.CASCADE 會處理關聯的 DetectionRecord 和 S3 檔案 (透過 django-cleanup)
                info = batch_jobs_to_delete_qs.delete()
                deleted_count = info[0] if isinstance(info, tuple) else 0
                logger.info(f"{log_prefix} [按時間清理批次] 成功刪除 {deleted_count} 個。詳情: {info}")
            else:
                logger.info(f"{log_prefix} [按時間清理批次] 無符合條件的舊批次可刪除。")
        except Exception as e:
            logger.error(f"{log_prefix} [按時間清理批次] 時發生錯誤: {e}", exc_info=True)
        return deleted_count

    def cleanup_batch_jobs_by_count(self, log_prefix=""):
        """
        按數量清理 BatchDetectionJob，只保留最新的 N 筆已完成/失敗的批次。
        N 從 settings.BATCH_JOBS_TO_KEEP_BY_COUNT 讀取。
        """
        deleted_count = 0
        try:
            jobs_to_keep = self._get_setting('BATCH_JOBS_TO_KEEP_BY_COUNT', 20)
            
            # 查詢所有處於最終狀態的批次，按創建時間倒序 (最新的在前)
            final_state_jobs_qs = BatchDetectionJob.objects.filter(
                status__in=[
                    BatchDetectionJob.StatusChoices.COMPLETED,
                    BatchDetectionJob.StatusChoices.FAILED,
                    BatchDetectionJob.StatusChoices.PARTIAL_COMPLETION,
                    BatchDetectionJob.StatusChoices.PROCESSING,
                ]
            ).order_by('-created_at')

            total_final_state_jobs = final_state_jobs_qs.count()
            logger.info(f"{log_prefix} [按數量清理批次] 設定保留: {jobs_to_keep} 筆, 目前最終狀態批次有: {total_final_state_jobs} 筆。")

            if total_final_state_jobs > jobs_to_keep:
                num_to_delete = total_final_state_jobs - jobs_to_keep
                # 獲取超出保留數量的、較舊的批次任務的 ID 列表
                ids_to_delete = list(final_state_jobs_qs.values_list('id', flat=True)[jobs_to_keep:])
                
                if ids_to_delete:
                    logger.info(f"{log_prefix} [按數量清理批次] 準備刪除 {num_to_delete} 筆 (IDs: {ids_to_delete[:5]}...).")
                    info = BatchDetectionJob.objects.filter(id__in=ids_to_delete).delete()
                    deleted_count = info[0] if isinstance(info, tuple) else 0
                    logger.info(f"{log_prefix} [按數量清理批次] 成功刪除 {deleted_count} 個。詳情: {info}")
                else:
                    logger.info(f"{log_prefix} [按數量清理批次] 無需刪除 (ids_to_delete 為空)。")
            else:
                 logger.info(f"{log_prefix} [按數量清理批次] 無需刪除 ({total_final_state_jobs} <= {jobs_to_keep})。")
        except Exception as e:
            logger.error(f"{log_prefix} [按數量清理批次] 時發生錯誤: {e}", exc_info=True)
        return deleted_count

    def run_scheduled_cleanup(self):
        log_prefix = "Scheduled Cleanup"
        logger.info(f"{log_prefix}: ===== 開始執行定期數據清理 =====")

        deleted_batches_time = self.cleanup_batch_jobs_by_time(log_prefix=f"{log_prefix} - Time")
        deleted_batches_count = self.cleanup_batch_jobs_by_count(log_prefix=f"{log_prefix} - Count")
        deleted_manual_time = self.cleanup_manual_records_by_time(log_prefix=f"{log_prefix} - Manual/Time")
        deleted_manual_count = self.cleanup_manual_records_by_count(log_prefix=f"{log_prefix} - Manual/Count")

        summary = {
            "manual_records_deleted_by_time": deleted_manual_time,
            "manual_records_deleted_by_count": deleted_manual_count,
            "batch_jobs_deleted_by_time": deleted_batches_time,
            "batch_jobs_deleted_by_count": deleted_batches_count,
        }
        logger.info(f"{log_prefix}: ===== 定期數據清理完成 ===== 摘要: {summary}")
        return summary

    def run_immediate_manual_cleanup(self):
        """
        執行手動上傳後的即時數量清理。由 View 呼叫。
        """
        log_prefix = "Immediate Manual Cleanup"
        # logger.info(f"{log_prefix}: ===== 開始執行即時手動記錄清理 =====") # 已在 cleanup_manual_records_by_count 內部記錄
        deleted_count = self.cleanup_manual_records_by_count(log_prefix=f"{log_prefix} - Manual/Count")
        # logger.info(f"{log_prefix}: ===== 即時手動記錄清理完成, 刪除 {deleted_count} 筆 =====") # 已在 cleanup_manual_records_by_count 內部記錄
        return deleted_count

    def run_immediate_batch_cleanup_after_finalization(self, finalized_batch_job_id):
        """
        在一個批次任務完成後，執行即時的基於數量的批次清理。
        由 Celery 任務 (finalize_batch_processing_task) 呼叫。
        """
        log_prefix = f"Immediate Batch Cleanup (after BatchJob {str(finalized_batch_job_id)[:8]})"
        # logger.info(f"{log_prefix}: ===== 開始執行即時批次數量清理 =====") # 已在 cleanup_batch_jobs_by_count 內部記錄
        # 這裡的關鍵是 cleanup_batch_jobs_by_count 會重新查詢資料庫，
        # 此時剛完成的 finalized_batch_job_id 的狀態應該已經被保存並對查詢可見。
        deleted_count = self.cleanup_batch_jobs_by_count(log_prefix=log_prefix)
        # logger.info(f"{log_prefix}: ===== 即時批次數量清理完成, 刪除 {deleted_count} 筆 =====") # 已在 cleanup_batch_jobs_by_count 內部記錄
        return deleted_count
