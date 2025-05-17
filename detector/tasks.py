# detector/tasks.py
from celery import shared_task
from django.conf import settings
import logging
import re
import os
import io
import traceback
import boto3
from botocore.exceptions import ClientError

# 匯入你的服務和推論工具
from .services import process_image_bytes # 假設 process_image_bytes 會在圖片無效時回傳特定的標記或拋出異常
from .inference_utils import ImageDecodeError # 我們將在 inference_utils 中定義這個自訂異常

logger = logging.getLogger(__name__)

# 最小有效圖片大小閾值 (位元組)，例如 1KB
MIN_VALID_IMAGE_SIZE_BYTES = 1024

@shared_task(bind=True, acks_late=True, time_limit=300, soft_time_limit=280)
def process_s3_image_task(self, s3_bucket_name, s3_object_key):
    """
    非同步處理 S3 中的單張圖片。
    """
    try:
        logger.info(f"Task {self.request.id}: Starting processing for S3 object: s3://{s3_bucket_name}/{s3_object_key}")

        s3_client = boto3.client('s3',
                                 aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                                 aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                                 region_name=settings.AWS_S3_REGION_NAME)
        try:
            s3_response_object = s3_client.get_object(Bucket=s3_bucket_name, Key=s3_object_key)
            image_bytes = s3_response_object['Body'].read()
            content_type = s3_response_object.get('ContentType', 'image/jpeg')
            actual_size = len(image_bytes)
            logger.info(f"Task {self.request.id}: Successfully downloaded {actual_size} bytes from S3 (s3://{s3_bucket_name}/{s3_object_key}). Content-Type: {content_type}")

            if actual_size < MIN_VALID_IMAGE_SIZE_BYTES:
                logger.warning(f"Task {self.request.id}: Image s3://{s3_bucket_name}/{s3_object_key} is too small ({actual_size} bytes). Skipping processing.")
                self.update_state(state='FAILURE', meta={'exc_type': 'InvalidImageData', 'exc_message': f'Image too small ({actual_size} bytes).'})
                return {'status': 'FAILURE', 's3_object_key': s3_object_key, 'error': f'Image too small ({actual_size} bytes).'}

        except ClientError as e:
            logger.error(f"Task {self.request.id}: S3 GetObject error for s3://{s3_bucket_name}/{s3_object_key}: {e}", exc_info=True)
            # 讓 Celery 知道任務失敗並可能重試 (根據預設或自訂的重試策略)
            raise self.retry(exc=e, countdown=60, max_retries=3) # 例如：60秒後重試，最多3次

        filename = os.path.basename(s3_object_key)
        file_extension = ".jpg"
        if '.' in filename:
            original_ext = filename.split('.')[-1].lower()
            if original_ext in ['jpeg', 'jpg', 'png', 'gif', 'webp']:
                 file_extension = f".{original_ext}"
        elif 'png' in content_type:
            file_extension = '.png'
        # ... 其他副檔名邏輯 ...

        try:
            # 呼叫核心的圖片處理服務
            # 假設 process_image_bytes 現在會在圖片解碼失敗時拋出 ImageDecodeError
            record = process_image_bytes(image_bytes, file_ext=file_extension)

            # 檢查是否有有效的辨識結果，如果 annotated_image 和 results_data 都為空，可能表示處理雖未拋錯但無意義
            if not record.annotated_image and not record.results_data:
                 logger.warning(f"Task {self.request.id}: Processing for s3://{s3_bucket_name}/{s3_object_key} resulted in no annotations or data. Original image size: {actual_size} bytes. Record ID: {record.id}")
                 # 你可以選擇是否將這種情況也視為一種「軟」失敗或僅記錄
                 # 這裡我們仍然回傳 SUCCESS，但前端或後續分析可以注意這種情況

            logger.info(f"Task {self.request.id}: Image processing completed for s3://{s3_bucket_name}/{s3_object_key}. Record ID: {record.id}")
            return {
                'status': 'SUCCESS',
                'record_id': str(record.id),
                's3_object_key': s3_object_key,
                'original_image_url': record.original_image.url,
                'annotated_image_url': record.annotated_image.url if record.annotated_image else None,
                'results_data': record.results_data
            }
        except ImageDecodeError as ide: # 捕獲來自 process_image_bytes (間接來自 inference_utils) 的特定錯誤
            logger.error(f"Task {self.request.id}: Failed to decode image data for s3://{s3_bucket_name}/{s3_object_key}: {ide}", exc_info=True)
            self.update_state(state='FAILURE', meta={'exc_type': type(ide).__name__, 'exc_message': str(ide)})
            return {'status': 'FAILURE', 's3_object_key': s3_object_key, 'error': f'Image decode error: {ide}'}

    except Exception as e: # 捕獲所有其他未預料的錯誤
        logger.error(f"Task {self.request.id}: Unhandled error processing S3 image s3://{s3_bucket_name}/{s3_object_key}: {e}", exc_info=True)
        formatted_traceback = traceback.format_exc()
        # 確保 meta 中的內容是 JSON 可序列化的
        meta_info = {
            'exc_type': type(e).__name__,
            'exc_message': str(e),
            'traceback': formatted_traceback
        }
        try: # 嘗試更新狀態，如果 meta_info 不可序列化，則記錄錯誤但不讓任務本身崩潰
            self.update_state(state='FAILURE', meta=meta_info)
        except Exception as update_state_exc:
            logger.error(f"Task {self.request.id}: Failed to update task state: {update_state_exc}")
        return {'status': 'FAILURE', 's3_object_key': s3_object_key, 'error': 'Unhandled processing error.'}


@shared_task(bind=True, time_limit=3600, soft_time_limit=3500)
def process_s3_folder_task(self, s3_bucket_name, s3_folder_prefix):
    """
    非同步處理 S3 資料夾中的所有圖片。
    """
    try:
        logger.info(f"Task {self.request.id}: Starting batch processing for S3 folder: s3://{s3_bucket_name}/{s3_folder_prefix}")
        s3_client = boto3.client('s3',
                                 aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                                 aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                                 region_name=settings.AWS_S3_REGION_NAME)

        if not s3_folder_prefix.endswith('/'):
            s3_folder_prefix += '/'

        image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
        image_tasks_triggered = 0
        
        paginator = s3_client.get_paginator('list_objects_v2')
        try:
            for page in paginator.paginate(Bucket=s3_bucket_name, Prefix=s3_folder_prefix):
                if "Contents" in page:
                    for obj in page["Contents"]:
                        s3_object_key = obj["Key"]
                        # 檢查是否是檔案且副檔名符合，並且檔案大小大於0 (S3中資料夾的Size為0)
                        if obj.get("Size", 0) > 0 and s3_object_key.lower().endswith(image_extensions) and s3_object_key != s3_folder_prefix:
                            logger.info(f"Task {self.request.id}: Triggering individual processing for S3 object: {s3_object_key} (Size: {obj.get('Size')})")
                            process_s3_image_task.delay(s3_bucket_name, s3_object_key)
                            image_tasks_triggered += 1
                        elif obj.get("Size", 0) == 0 and s3_object_key.endswith('/'):
                             logger.debug(f"Task {self.request.id}: Skipping directory object: {s3_object_key}")
                        else:
                            logger.debug(f"Task {self.request.id}: Skipping non-image or zero-size object: {s3_object_key} (Size: {obj.get('Size')})")
        except ClientError as e:
            logger.error(f"Task {self.request.id}: S3 ListObjects error for s3://{s3_bucket_name}/{s3_folder_prefix}: {e}", exc_info=True)
            raise self.retry(exc=e, countdown=120, max_retries=2)


        if image_tasks_triggered == 0:
             logger.warning(f"Task {self.request.id}: No valid images found or triggered for processing in s3://{s3_bucket_name}/{s3_folder_prefix}")

        summary_message = f"Batch processing initiated for s3://{s3_bucket_name}/{s3_folder_prefix}. Triggered {image_tasks_triggered} image processing tasks."
        logger.info(f"Task {self.request.id}: {summary_message}")
        return {'status': 'SUCCESS', 'message': summary_message, 'tasks_triggered': image_tasks_triggered}

    except Exception as e:
        logger.error(f"Task {self.request.id}: Error in batch processing S3 folder s3://{s3_bucket_name}/{s3_folder_prefix}: {e}", exc_info=True)
        formatted_traceback = traceback.format_exc()
        meta_info = {
            'exc_type': type(e).__name__,
            'exc_message': str(e),
            'traceback': formatted_traceback
        }
        try:
            self.update_state(state='FAILURE', meta=meta_info)
        except Exception as update_state_exc:
            logger.error(f"Task {self.request.id}: Failed to update task state: {update_state_exc}")
        return {'status': 'FAILURE', 'error': 'Unhandled batch processing error.'}
