# detector/tasks.py
# ------------------------------------------------
# Celery 任務：處理單張/批次 S3 圖片，與排程清理舊資料
# ------------------------------------------------
import os
import traceback
import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from django.db.models import F
from celery import shared_task, group
from .retention_manager import DataRetentionManager
from .models import BatchDetectionJob, DetectionRecord
from .services import process_image_bytes, ImageDecodeError
import logging

logger = logging.getLogger(__name__)

# ====== 常數 ======
MIN_VALID_IMAGE_SIZE = 1024  # 最小圖檔大小 (bytes)


# ====== 工具函式 ======
def _increment_batch_failure(batch_job_id):
    """批次失敗計數遞增。"""
    BatchDetectionJob.objects.filter(id=batch_job_id).update(
        images_failed_to_process=F('images_failed_to_process') + 1
    )


# ====== Celery 任務：單張 S3 圖片處理 ======
@shared_task(bind=True, acks_late=True, time_limit=300, soft_time_limit=280, max_retries=3)
def process_s3_image_task(self, s3_bucket, s3_key, batch_job_id=None):
    """
    處理單張 S3 圖片：下載、驗證大小、辨識並儲存結果。
    回傳 dict 包含處理狀態與結果摘要。
    """
    task_label = f"Task[{self.request.id}]-Batch[{batch_job_id or 'N/A'}]"
    logger.info(f"{task_label}: Start processing s3://{s3_bucket}/{s3_key}")

    # 取得或驗證 BatchDetectionJob
    batch = None
    if batch_job_id:
        try:
            batch = BatchDetectionJob.objects.get(id=batch_job_id)
        except BatchDetectionJob.DoesNotExist:
            logger.error(f"{task_label}: BatchJob {batch_job_id} not found.")
            self.update_state(state='FAILURE', meta={
                'exc_type': 'BatchJobNotFound',
                'exc_message': f'id={batch_job_id} 不存在'
            })
            return {
                'status': 'FAILURE', 's3_key': s3_key,
                'error': 'BatchJob 不存在', 'processed': False,
                'class_counts': {}, 'severity_score': None
            }
        except Exception as e:
            logger.error(f"{task_label}: Fetch BatchJob error: {e}", exc_info=True)
            raise self.retry(exc=e, countdown=60)

    # 下載 S3 圖片
    try:
        client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
            config=boto3.session.Config(retries={'max_attempts': 3, 'mode': 'standard'})
        )
        obj = client.get_object(Bucket=s3_bucket, Key=s3_key)
        img_bytes = obj['Body'].read()
        size = len(img_bytes)
        logger.info(f"{task_label}: Downloaded {size} bytes, Content-Type={obj.get('ContentType')}")

        if size < MIN_VALID_IMAGE_SIZE:
            logger.warning(f"{task_label}: 圖片過小 ({size} bytes)，略過")
            if batch:
                _increment_batch_failure(batch.id)
            self.update_state(state='FAILURE', meta={'exc_type': 'InvalidImage', 'exc_message': '圖檔過小'})
            return {
                'status': 'FAILURE', 's3_key': s3_key,
                'error': '圖檔過小', 'processed': False,
                'class_counts': {}, 'severity_score': None
            }
    except ClientError as err:
        logger.error(f"{task_label}: S3 下載錯誤: {err}", exc_info=True)
        if batch:
            _increment_batch_failure(batch.id)
        raise self.retry(exc=err, countdown=60 * (self.request.retries + 1))

    # 構建 DetectionRecord
    filename = os.path.basename(s3_key)
    ext = os.path.splitext(filename)[1].lower() or '.jpg'
    record = DetectionRecord(batch_job=batch)

    # 執行影像處理與儲存
    try:
        processed = process_image_bytes(
            image_bytes=img_bytes,
            file_ext=ext,
            detection_record_instance=record
        )
        if not processed or not processed.id:
            raise RuntimeError('Record 未儲存')

        logger.info(f"{task_label}: 處理完成，Record ID={processed.id}")
        if batch:
            BatchDetectionJob.objects.filter(id=batch.id).update(
                images_processed_successfully=F('images_processed_successfully') + 1
            )

        # 建立 class_counts
        counts = {}
        for item in processed.results_data or []:
            cls = item.get('class', 'unknown')
            counts[cls] = counts.get(cls, 0) + 1

        return {
            'status': 'SUCCESS', 'record_id': str(processed.id),
            's3_key': s3_key,
            'original_image_url': getattr(processed.original_image, 'url', None),
            'annotated_image_url': getattr(processed.annotated_image, 'url', None),
            'results_data': processed.results_data,
            'severity_score': processed.severity_score,
            'class_counts': counts, 'processed': True
        }

    except ImageDecodeError as ide:
        logger.error(f"{task_label}: 圖片解碼錯誤: {ide}", exc_info=True)
        if batch:
            _increment_batch_failure(batch.id)
        record.results_data = {'error': str(ide), 'original_s3_key': s3_key}
        record.severity_score = 1.0
        record.save()
        self.update_state(state='FAILURE', meta={'exc_type': 'ImageDecodeError', 'exc_message': str(ide)})
        return {
            'status': 'FAILURE', 's3_key': s3_key,
            'error': f'DecodeError: {ide}', 'processed': False,
            'class_counts': {}, 'severity_score': None
        }

    except Exception as ex:
        logger.error(f"{task_label}: 處理錯誤: {ex}", exc_info=True)
        if batch:
            _increment_batch_failure(batch.id)
        if not record.pk:
            record.results_data = {'error': str(ex), 'original_s3_key': s3_key}
            record.severity_score = 1.0
            record.save()
        self.update_state(state='FAILURE', meta={'exc_type': type(ex).__name__, 'exc_message': str(ex)})
        return {
            'status': 'FAILURE', 's3_key': s3_key,
            'error': f'ProcessingError: {ex}', 'processed': False,
            'class_counts': {}, 'severity_score': None
        }


# ====== Celery 任務：批次彙總與清理 ======
@shared_task(bind=True, name="detector.tasks.finalize_batch_processing")
def finalize_batch_processing_task(self, results, batch_job_id):
    """
    批次處理完成後彙總結果並清理舊筆數。
    """
    task_label = f"Task[{self.request.id}]-Finalize[{batch_job_id}]"
    logger.info(f"{task_label}: 開始最終統計")

    try:
        batch = BatchDetectionJob.objects.get(id=batch_job_id)
    except BatchDetectionJob.DoesNotExist:
        logger.error(f"{task_label}: BatchJob 不存在，跳過")
        return

    # 彙總計數與狀態
    success, fail = 0, 0
    total_score, score_count = 0.0, 0
    agg_counts = {}

    for r in results:
        if not isinstance(r, dict) or 'processed' not in r:
            logger.warning(f"{task_label}: 非預期結果: {r}")
            continue
        if r['status'] == 'SUCCESS':
            success += 1
            if r.get('severity_score') is not None:
                try:
                    total_score += float(r['severity_score'])
                    score_count += 1
                except (TypeError, ValueError):
                    logger.warning(f"{task_label}: 無效嚴重度: {r['severity_score']}")
            for cls, cnt in r.get('class_counts', {}).items():
                agg_counts[cls] = agg_counts.get(cls, 0) + cnt
        else:
            fail += 1

    # 更新 BatchDetectionJob 欄位與狀態
    batch.images_processed_successfully = success
    batch.images_failed_to_process = batch.total_images_found - success
    if fail == 0:
        batch.status = BatchDetectionJob.StatusChoices.COMPLETED
    elif success > 0:
        batch.status = BatchDetectionJob.StatusChoices.PARTIAL_COMPLETION
    else:
        batch.status = BatchDetectionJob.StatusChoices.FAILED
        batch.error_message = batch.error_message or "All images failed."

    # 計算平均嚴重度
    avg_score = round(total_score / score_count, 3) if score_count else None
    summary = {
        "message": f"Found {batch.total_images_found}, success {success}, failed {fail}",
        "detected_classes_summary": agg_counts,
        "average_severity_score": avg_score
    }
    batch.summary_results = summary
    batch.save()

    # 立即執行批次清理
    try:
        logger.info(f"{task_label}: 執行即時清理")
        DataRetentionManager().run_immediate_batch_cleanup_after_finalization(finalized_batch_job_id=batch.id)
    except Exception as e:
        logger.error(f"{task_label}: 清理錯誤: {e}", exc_info=True)

    logger.info(f"{task_label}: 完成，狀態={batch.get_status_display()}")
    return {'status': 'FINALIZED', 'batch_job_id': str(batch.id), 'final_status': batch.status}


# ====== Celery 任務：定期清理舊資料 ======
@shared_task(name="detector.tasks.cleanup_old_detection_data")
def cleanup_old_detection_data_task():
    """定期清理舊偵測資料。"""
    label = "Task-CleanupOldData"
    logger.info(f"{label}: 啟動排程清理")
    try:
        result = DataRetentionManager().run_scheduled_cleanup()
        logger.info(f"{label}: 完成，摘要={result}")
        return f"Cleanup complete: {result}"
    except Exception as e:
        logger.error(f"{label}: 清理失敗: {e}", exc_info=True)
        return f"Cleanup failed: {e}"


# ====== Celery 任務：批次處理 S3 資料夾 ======
@shared_task(bind=True, time_limit=3600, soft_time_limit=3500, max_retries=2)
def process_s3_folder_task(self, s3_bucket, s3_prefix):
    """
    批次處理 S3 資料夾：列出所有圖片並分派子任務。
    """
    task_label = f"Task[{self.request.id}]-BatchMain"
    logger.info(f"{task_label}: 開始掃描 s3://{s3_bucket}/{s3_prefix}")

    # 建立 BatchDetectionJob
    try:
        batch = BatchDetectionJob.objects.create(
            celery_task_id=self.request.id,
            s3_bucket_name=s3_bucket,
            s3_folder_prefix=s3_prefix,
            status=BatchDetectionJob.StatusChoices.PROCESSING
        )
        logger.info(f"{task_label}: 建立 BatchJob ID={batch.id}")
    except Exception as e:
        logger.error(f"{task_label}: 建立 BatchJob 失敗: {e}", exc_info=True)
        self.update_state(state='FAILURE', meta={'exc_type': type(e).__name__, 'exc_message': str(e)})
        return {'status': 'FAILURE', 'error': str(e)}

    # 列出 S3 圖片
    try:
        client = boto3.client(
            's3', aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
            config=boto3.session.Config(retries={'max_attempts': 3, 'mode': 'standard'})
        )
        prefix = s3_prefix.rstrip('/') + '/'
        paginator = client.get_paginator('list_objects_v2')
        keys = []
        for page in paginator.paginate(Bucket=s3_bucket, Prefix=prefix):
            for obj in page.get('Contents', []):
                key = obj['Key']
                if obj.get('Size', 0) > 0 and key.lower().endswith(('.jpg', '.png', '.webp')):
                    keys.append(key)
    except ClientError as err:
        logger.error(f"{task_label}: ListObjects 錯誤: {err}", exc_info=True)
        batch.status = BatchDetectionJob.StatusChoices.FAILED
        batch.error_message = str(err)
        batch.save()
        raise self.retry(exc=err, countdown=120)

    # 更新並觸發子任務
    batch.total_images_found = len(keys)
    batch.save()
    logger.info(f"{task_label}: 共找到 {len(keys)} 張圖片")

    if not keys:
        batch.status = BatchDetectionJob.StatusChoices.COMPLETED
        batch.summary_results = {"message": "No images found."}
        batch.save()
        return {'status': 'NO_IMAGES', 'batch_id': str(batch.id)}

    chord = group(
        process_s3_image_task.s(s3_bucket, k, batch.id) for k in keys
    ) | finalize_batch_processing_task.s(batch.id)
    res = chord.apply_async()
    logger.info(f"{task_label}: Chord dispatched ID={res.id}")
    return {'status': 'DISPATCHED', 'batch_id': str(batch.id), 'chord_id': res.id}
