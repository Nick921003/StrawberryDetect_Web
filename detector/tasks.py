# detector/tasks.py
from celery import shared_task
from django.conf import settings
from django.db.models import F #  <-- 確保匯入 F
import logging
import os
import traceback
import boto3
from botocore.exceptions import ClientError

# --- 模型匯入 ---
from .models import BatchDetectionJob, DetectionRecord # DetectionRecord 現在會在這裡用到

# --- 服務和工具匯入 ---
from .services import process_image_bytes # 核心圖片處理服務
from .inference_utils import ImageDecodeError # 自訂的圖片解碼錯誤

logger = logging.getLogger(__name__)

MIN_VALID_IMAGE_SIZE_BYTES = 1024 # 最小有效圖片大小閾值 (位元組)，例如 1KB

@shared_task(bind=True, acks_late=True, time_limit=300, soft_time_limit=280)
def process_s3_image_task(self, s3_bucket_name, s3_object_key, batch_job_id=None): # batch_job_id 是新的參數
    """
    非同步處理 S3 中的單張圖片，並更新對應的 BatchDetectionJob 狀態。
    """
    task_id_log = f"Task {self.request.id} (BatchJob {batch_job_id if batch_job_id else 'N/A'})"
    logger.info(f"{task_id_log}: Starting processing for S3 object: s3://{s3_bucket_name}/{s3_object_key}")

    batch_job = None
    if batch_job_id:
        try:
            batch_job = BatchDetectionJob.objects.get(id=batch_job_id)
        except BatchDetectionJob.DoesNotExist:
            logger.error(f"{task_id_log}: BatchDetectionJob with ID {batch_job_id} does not exist. Cannot proceed for object {s3_object_key}.")
            # 這種情況下，任務無法將結果關聯到批次，可以選擇失敗或記錄後忽略
            self.update_state(state='FAILURE', meta={'exc_type': 'BatchJobNotFound', 'exc_message': f'BatchDetectionJob ID {batch_job_id} not found.'})
            return {'status': 'FAILURE', 's3_object_key': s3_object_key, 'error': f'BatchDetectionJob ID {batch_job_id} not found.'}
        except Exception as e: # 其他獲取 batch_job 的錯誤
            logger.error(f"{task_id_log}: Error fetching BatchDetectionJob ID {batch_job_id}: {e}", exc_info=True)
            raise self.retry(exc=e, countdown=60, max_retries=3) # 重試獲取 batch_job

    image_bytes = None
    record = None # 初始化 DetectionRecord 變數

    try:
        # 1. 從 S3 下載圖片
        s3_client = boto3.client('s3',
                                 aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                                 aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                                 region_name=settings.AWS_S3_REGION_NAME)
        try:
            s3_response_object = s3_client.get_object(Bucket=s3_bucket_name, Key=s3_object_key)
            image_bytes = s3_response_object['Body'].read()
            content_type = s3_response_object.get('ContentType', 'image/jpeg') # 獲取 ContentType
            actual_size = len(image_bytes)
            logger.info(f"{task_id_log}: Successfully downloaded {actual_size} bytes from S3 (s3://{s3_bucket_name}/{s3_object_key}). Content-Type: {content_type}")

            if actual_size < MIN_VALID_IMAGE_SIZE_BYTES:
                logger.warning(f"{task_id_log}: Image s3://{s3_bucket_name}/{s3_object_key} is too small ({actual_size} bytes). Skipping processing.")
                if batch_job: # 如果有關聯的批次任務，更新失敗計數
                    BatchDetectionJob.objects.filter(id=batch_job.id).update(images_failed_to_process=F('images_failed_to_process') + 1)
                self.update_state(state='FAILURE', meta={'exc_type': 'InvalidImageData', 'exc_message': f'Image too small ({actual_size} bytes).'})
                return {'status': 'FAILURE', 's3_object_key': s3_object_key, 'error': f'Image too small ({actual_size} bytes).'}

        except ClientError as e:
            logger.error(f"{task_id_log}: S3 GetObject error for s3://{s3_bucket_name}/{s3_object_key}: {e}", exc_info=True)
            if batch_job: # 如果有關聯的批次任務，更新失敗計數
                BatchDetectionJob.objects.filter(id=batch_job.id).update(images_failed_to_process=F('images_failed_to_process') + 1)
            raise self.retry(exc=e, countdown=60, max_retries=3)

        # 2. 確定檔案副檔名 (基於 S3 object key 或 ContentType)
        filename = os.path.basename(s3_object_key)
        file_extension = ".jpg" # 預設
        if '.' in filename:
            original_ext = filename.split('.')[-1].lower()
            if original_ext in ['jpeg', 'jpg', 'png', 'gif', 'webp', 'bmp', 'tiff']: # 擴展支援的格式
                 file_extension = f".{original_ext}"
        elif content_type: # 如果檔名沒有副檔名，嘗試從 ContentType 推斷
            if 'png' in content_type: file_extension = '.png'
            elif 'gif' in content_type: file_extension = '.gif'
            elif 'webp' in content_type: file_extension = '.webp'
            elif 'bmp' in content_type: file_extension = '.bmp'
            elif 'tiff' in content_type: file_extension = '.tiff'
            # jpeg 通常是預設或最常見的

        # 3. 呼叫核心的圖片處理服務
        # 注意：process_image_bytes 內部會創建 DetectionRecord 並儲存圖片和結果
        # 我們需要確保它能正確處理 batch_job 的關聯
        try:
            # 修改：將 batch_job 實例傳遞給 process_image_bytes，或者在 service 中根據 batch_job_id 獲取
            # 這裡我們假設 process_image_bytes 內部會處理 DetectionRecord 的創建和 batch_job 的關聯
            # 我們需要修改 services.py 中的 process_image_bytes 以接收 batch_job_id (或 batch_job 實例)
            # 現在，我們先直接在這裡創建 DetectionRecord，然後讓 services.py 更純粹地做圖片處理和YOLO推論
            
            # 先創建一個 DetectionRecord 實例，但不儲存圖片和結果數據
            record = DetectionRecord(
                batch_job=batch_job, # 關聯到批次任務
                # original_image 和 annotated_image 會在 process_image_bytes 中被賦值並儲存
                # results_data 也會被賦值
            )
            # record.save() # 先不儲存，等 process_image_bytes 處理完圖片和結果後一起儲存

            # 呼叫 process_image_bytes，它應該返回原始圖片檔名、標註圖片檔名和結果數據
            # 或者，讓 process_image_bytes 直接操作傳入的 record 實例
            # 我們採用後者，修改 services.py 中的 process_image_bytes
            
            # 調用服務，傳入 record 實例讓其填充
            # 注意：我們需要修改 services.py 中的 process_image_bytes 函式簽名和內部邏輯
            record = process_image_bytes(image_bytes=image_bytes, file_ext=file_extension, detection_record_instance=record)
            # process_image_bytes 內部會處理 record.save()，其中包含了 calculate_severity_score()

            if not record.id: # 確認 record 是否成功儲存 (並獲得了ID)
                raise ValueError("DetectionRecord was not saved properly by process_image_bytes service.")


            logger.info(f"{task_id_log}: Image processing completed for s3://{s3_bucket_name}/{s3_object_key}. Record ID: {record.id}")
            if batch_job: # 圖片處理成功，更新成功計數
                BatchDetectionJob.objects.filter(id=batch_job.id).update(images_processed_successfully=F('images_processed_successfully') + 1)
            
            return {
                'status': 'SUCCESS',
                'record_id': str(record.id),
                's3_object_key': s3_object_key,
                'original_image_url': record.original_image.url if record.original_image else None,
                'annotated_image_url': record.annotated_image.url if record.annotated_image else None,
                'results_data': record.results_data,
                'severity_score': record.severity_score
            }

        except ImageDecodeError as ide:
            logger.error(f"{task_id_log}: Failed to decode image data for s3://{s3_bucket_name}/{s3_object_key}: {ide}", exc_info=True)
            if batch_job: # 圖片解碼失敗，更新失敗計數
                BatchDetectionJob.objects.filter(id=batch_job.id).update(images_failed_to_process=F('images_failed_to_process') + 1)
            # 創建一個失敗的 DetectionRecord (可選，但有助於追蹤)
            if record and not record.pk: # 如果 record 尚未儲存
                record.results_data = {'error': f'Image decode error: {str(ide)}', 'original_s3_key': s3_object_key}
                # severity_score 可以設為最高或特定錯誤值
                record.severity_score = 1.0 # 或 None，或一個特殊值表示錯誤
                try:
                    record.save() # 儲存這個失敗的記錄
                    logger.info(f"{task_id_log}: Saved a failed DetectionRecord ID {record.id} for {s3_object_key} due to ImageDecodeError.")
                except Exception as save_err:
                    logger.error(f"{task_id_log}: Could not save failed DetectionRecord for {s3_object_key}: {save_err}", exc_info=True)

            self.update_state(state='FAILURE', meta={'exc_type': type(ide).__name__, 'exc_message': str(ide)})
            return {'status': 'FAILURE', 's3_object_key': s3_object_key, 'error': f'Image decode error: {str(ide)}'}
        
        except Exception as proc_e: # 處理 process_image_bytes 中可能發生的其他錯誤
            logger.error(f"{task_id_log}: Error during image processing service for s3://{s3_bucket_name}/{s3_object_key}: {proc_e}", exc_info=True)
            if batch_job: # 服務處理失敗，更新失敗計數
                BatchDetectionJob.objects.filter(id=batch_job.id).update(images_failed_to_process=F('images_failed_to_process') + 1)
            if record and not record.pk:
                record.results_data = {'error': f'Processing error: {str(proc_e)}', 'original_s3_key': s3_object_key}
                record.severity_score = 1.0 # 或 None
                try:
                    record.save()
                    logger.info(f"{task_id_log}: Saved a failed DetectionRecord ID {record.id} for {s3_object_key} due to processing error.")
                except Exception as save_err:
                    logger.error(f"{task_id_log}: Could not save failed DetectionRecord for {s3_object_key} (processing error): {save_err}", exc_info=True)
            
            # 這裡不直接 raise self.retry，因為可能是不可重試的錯誤（例如圖片本身有問題）
            # 而是將任務標記為失敗
            self.update_state(state='FAILURE', meta={'exc_type': type(proc_e).__name__, 'exc_message': str(proc_e)})
            return {'status': 'FAILURE', 's3_object_key': s3_object_key, 'error': f'Image processing service error: {str(proc_e)}'}


    except Exception as e: # 捕獲所有其他未預料的錯誤 (例如獲取 batch_job 失敗且未重試成功)
        logger.error(f"{task_id_log}: Unhandled error processing S3 image s3://{s3_bucket_name}/{s3_object_key}: {e}", exc_info=True)
        # 在這裡，如果 batch_job 存在，也應該更新失敗計數，但要小心重複計算
        # 之前的特定錯誤處理中已經更新了計數，這裡主要是針對未被捕獲的意外
        # 如果上面的 try 塊中已經更新了計數，這裡就不應再次更新，或者需要更細緻的邏輯
        # 為了安全，如果錯誤發生在核心處理邏輯之外，我們假設之前的計數更新可能未執行
        if batch_job and not record: # 如果 record 還沒創建，說明錯誤發生在處理前
             BatchDetectionJob.objects.filter(id=batch_job.id).update(images_failed_to_process=F('images_failed_to_process') + 1)

        formatted_traceback = traceback.format_exc()
        meta_info = {
            'exc_type': type(e).__name__,
            'exc_message': str(e),
            'traceback': formatted_traceback
        }
        try:
            self.update_state(state='FAILURE', meta=meta_info)
        except Exception as update_state_exc:
            logger.error(f"{task_id_log}: Failed to update task state: {update_state_exc}")
        return {'status': 'FAILURE', 's3_object_key': s3_object_key, 'error': 'Unhandled processing error.'}


@shared_task(bind=True, time_limit=3600, soft_time_limit=3500) # time_limit 可以根據實際情況調整
def process_s3_folder_task(self, s3_bucket_name, s3_folder_prefix):
    """
    非同步處理 S3 資料夾中的所有圖片。
    創建 BatchDetectionJob 記錄，並為每張圖片觸發 process_s3_image_task。
    """
    batch_job = None # 初始化 batch_job 變數
    try:
        logger.info(f"Task {self.request.id}: Starting batch processing for S3 folder: s3://{s3_bucket_name}/{s3_folder_prefix}")

        # 1. 創建 BatchDetectionJob 記錄
        try:
            batch_job = BatchDetectionJob.objects.create(
                celery_task_id=self.request.id, # 將 Celery 任務自身的 ID 存起來
                s3_bucket_name=s3_bucket_name,
                s3_folder_prefix=s3_folder_prefix,
                status=BatchDetectionJob.StatusChoices.PROCESSING # 初始狀態設為處理中
            )
            logger.info(f"Task {self.request.id}: Created BatchDetectionJob with ID: {batch_job.id}")
        except Exception as e:
            logger.error(f"Task {self.request.id}: Failed to create BatchDetectionJob for s3://{s3_bucket_name}/{s3_folder_prefix}: {e}", exc_info=True)
            # 如果連 BatchDetectionJob 都無法創建，任務無法繼續，直接拋出異常
            # Celery 會根據設定處理重試或標記為失敗
            self.update_state(state='FAILURE', meta={
                'exc_type': type(e).__name__,
                'exc_message': f"Failed to create BatchDetectionJob: {str(e)}",
                'traceback': traceback.format_exc()
            })
            # 這裡可以考慮是否要 raise e 讓 Celery 重試，或者直接返回失敗
            return {'status': 'FAILURE', 'error': f'Failed to create BatchDetectionJob: {str(e)}'}


        s3_client = boto3.client('s3',
                                 aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                                 aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                                 region_name=settings.AWS_S3_REGION_NAME)

        if not s3_folder_prefix.endswith('/'):
            s3_folder_prefix += '/' # 確保 folder_prefix 以 '/' 結尾

        image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp') # 你可以根據需要調整支援的副檔名
        images_to_process_keys = [] # 用來收集所有找到的圖片 key

        paginator = s3_client.get_paginator('list_objects_v2')
        try:
            for page in paginator.paginate(Bucket=s3_bucket_name, Prefix=s3_folder_prefix):
                if "Contents" in page:
                    for obj in page["Contents"]:
                        s3_object_key = obj["Key"]
                        # 檢查是否是檔案 (Size > 0), 副檔名符合, 且不是資料夾本身
                        if obj.get("Size", 0) > 0 and \
                           s3_object_key.lower().endswith(image_extensions) and \
                           s3_object_key != s3_folder_prefix:
                            images_to_process_keys.append(s3_object_key)
                        elif obj.get("Size", 0) == 0 and s3_object_key.endswith('/'):
                             logger.debug(f"Task {self.request.id} (Batch {batch_job.id if batch_job else 'N/A'}): Skipping directory object: {s3_object_key}")
                        else:
                            logger.debug(f"Task {self.request.id} (Batch {batch_job.id if batch_job else 'N/A'}): Skipping non-image or zero-size object: {s3_object_key} (Size: {obj.get('Size')})")
        
        except ClientError as e:
            logger.error(f"Task {self.request.id} (Batch {batch_job.id if batch_job else 'N/A'}): S3 ListObjects error for s3://{s3_bucket_name}/{s3_folder_prefix}: {e}", exc_info=True)
            if batch_job:
                batch_job.status = BatchDetectionJob.StatusChoices.FAILED
                batch_job.error_message = f"S3 ListObjects error: {str(e)}"
                batch_job.save()
            # 讓 Celery 知道任務失敗並可能重試 (根據預設或自訂的重試策略)
            raise self.retry(exc=e, countdown=120, max_retries=2) # 例如：2分鐘後重試，最多2次

        # 2. 更新 BatchDetectionJob 的 total_images_found
        if batch_job:
            batch_job.total_images_found = len(images_to_process_keys)
            batch_job.save() #儲存 total_images_found
            logger.info(f"Task {self.request.id} (Batch {batch_job.id}): Found {batch_job.total_images_found} images to process in s3://{s3_bucket_name}/{s3_folder_prefix}")

        # 3. 為每張找到的圖片觸發 process_s3_image_task
        image_tasks_triggered_count = 0
        for s3_key in images_to_process_keys:
            if batch_job: # 確保 batch_job 存在
                process_s3_image_task.delay(s3_bucket_name, s3_key, batch_job.id) # 傳遞 batch_job.id
                image_tasks_triggered_count += 1
            else: # 理論上不應該發生，因為 batch_job 在開始時就創建了
                logger.error(f"Task {self.request.id}: Cannot trigger process_s3_image_task for {s3_key} because BatchDetectionJob is None.")


        if image_tasks_triggered_count == 0 and batch_job and batch_job.total_images_found == 0 :
             logger.warning(f"Task {self.request.id} (Batch {batch_job.id}): No valid images found or triggered for processing in s3://{s3_bucket_name}/{s3_folder_prefix}")
             # 如果沒有找到任何圖片，可以直接將批次狀態更新為 COMPLETED (或一個特定的 "NO_IMAGES_FOUND" 狀態)
             batch_job.status = BatchDetectionJob.StatusChoices.COMPLETED # 或者你可以新增一個 "NO_IMAGES" 狀態
             batch_job.summary_results = {"message": "No images found matching the criteria."}
             batch_job.save()

        summary_message = f"Batch processing initiated for s3://{s3_bucket_name}/{s3_folder_prefix}. Batch Job ID: {batch_job.id if batch_job else 'N/A'}. Found {len(images_to_process_keys)} images, triggered {image_tasks_triggered_count} processing tasks."
        logger.info(f"Task {self.request.id}: {summary_message}")

        # 注意：此任務的主要職責是啟動子任務。
        # 批次的最終狀態 (COMPLETED, PARTIAL_COMPLETION) 會由子任務完成後更新，
        # 或者透過一個額外的匯總任務來判斷 (步驟 3.3)。
        # 目前，如果此任務成功執行到這裡，表示所有子任務都已 "派發"。
        # 我們可以暫時不改變 batch_job 的狀態，讓它保持 PROCESSING，
        # 等待子任務回報或後續的匯總任務來更新最終狀態。
        # 如果沒有任何圖片被觸發，且 total_images_found 為 0，上面已經將其設為 COMPLETED。

        return {'status': 'SUCCESS', 'message': summary_message, 'batch_job_id': str(batch_job.id) if batch_job else None, 'tasks_triggered': image_tasks_triggered_count}

    except Exception as e: # 捕獲所有其他未預料的錯誤
        logger.error(f"Task {self.request.id} (Batch {batch_job.id if batch_job else 'N/A'}): Unhandled error in batch processing S3 folder s3://{s3_bucket_name}/{s3_folder_prefix}: {e}", exc_info=True)
        formatted_traceback = traceback.format_exc()
        if batch_job: # 如果 batch_job 已經被創建，嘗試更新其狀態
            batch_job.status = BatchDetectionJob.StatusChoices.FAILED
            batch_job.error_message = f"Unhandled batch processing error: {str(e)}"
            batch_job.save()
        
        meta_info = {
            'exc_type': type(e).__name__,
            'exc_message': str(e),
            'traceback': formatted_traceback,
            's3_bucket': s3_bucket_name,
            's3_prefix': s3_folder_prefix
        }
        try:
            self.update_state(state='FAILURE', meta=meta_info)
        except Exception as update_state_exc:
            logger.error(f"Task {self.request.id}: Failed to update task state: {update_state_exc}")
        return {'status': 'FAILURE', 'error': 'Unhandled batch processing error.', 'batch_job_id': str(batch_job.id) if batch_job else None}