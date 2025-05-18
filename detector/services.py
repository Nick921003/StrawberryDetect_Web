## detector/services.py
import io
import uuid # 雖然檔名由 task 生成，但保留以防未來其他用途
import cv2 # OpenCV 用於影像處理
from PIL import Image # Pillow 用於影像格式轉換和儲存
from django.core.files.base import ContentFile # 用於將 bytes 轉換為 Django File Object
# --- 匯入 DetectionRecord 模型 ---
from .models import DetectionRecord
from .inference_utils import run_yolo_inference_on_image_data, ImageDecodeError # YOLO 推論工具
import logging
service_logger = logging.getLogger(__name__)


def process_image_bytes(image_bytes: bytes, 
                        file_ext: str = '.jpg', 
                        confidence: float = 0.5, 
                        detection_record_instance: DetectionRecord = None) -> DetectionRecord:
    """
    處理影像 bytes，執行 YOLO 推論，並將結果填充到傳入的 DetectionRecord 實例中。
    此函式負責儲存原始圖片、標註圖片（如果有的話）到 DetectionRecord 的 ImageField，
    並儲存文字結果，最後儲存 DetectionRecord 實例。

    Args:
        image_bytes: 圖片的二進位內容。
        file_ext: 原始圖片的檔案副檔名，如 '.jpg' 或 '.png'。
        confidence: YOLO 推論的信心水準閾值。
        detection_record_instance: 一個預先創建的 DetectionRecord 實例，
                                   此函式會填充其欄位並儲存它。

    Returns:
        處理完成並已儲存的 DetectionRecord 實例。

    Raises:
        ImageDecodeError: 如果圖片位元組無法被解碼。
        RuntimeError: 如果 YOLO 模型未載入或推論過程中發生其他嚴重錯誤。
        ValueError: 如果 detection_record_instance 未提供。
    """
    if detection_record_instance is None:
        # 理論上，呼叫此服務時應該總是提供一個 record 實例
        # 但為了防禦性程式設計，我們加上這個檢查
        service_logger.error("process_image_bytes called without a detection_record_instance.")
        raise ValueError("A DetectionRecord instance must be provided to process_image_bytes.")

    record = detection_record_instance # 使用傳入的實例

    try:
        # 1) 執行 YOLO 推論 (這部分邏輯與之前類似，但錯誤會向上拋出)
        # run_yolo_inference_on_image_data 內部會處理 ImageDecodeError
        annotated_image_array, text_results = run_yolo_inference_on_image_data(
            image_bytes, confidence_threshold=confidence
        )
        record.results_data = text_results # 設定辨識結果數據

    except ImageDecodeError as ide:
        service_logger.error(f"ImageDecodeError in service for record (to be created or existing with batch_job {record.batch_job_id if record.batch_job_id else 'N/A'}): {ide}")
        # 記錄錯誤到 record，但不儲存圖片
        record.results_data = {'error': f'Image decode error: {str(ide)}'}
        # severity_score 會在 record.save() 時被計算（可能為 None 或錯誤值）
        record.save() # 儲存包含錯誤訊息的記錄
        raise # 將 ImageDecodeError 重新拋出，讓 Celery task 捕獲並處理計數器

    except RuntimeError as rte: # 例如 YOLO 模型載入失敗
        service_logger.error(f"RuntimeError during YOLO inference in service for record (batch_job {record.batch_job_id if record.batch_job_id else 'N/A'}): {rte}")
        record.results_data = {'error': f'YOLO inference runtime error: {str(rte)}'}
        record.save()
        raise # 重新拋出

    # 2) 處理和儲存圖片檔案
    # 即使 YOLO 推論沒有任何結果 (annotated_image_array 為 None)，我們通常還是要儲存原始圖片。
    
    # 使用 uuid 生成唯一的基礎檔名，確保檔名不重複
    # Celery task 中傳入的 s3_object_key 已經是唯一的，這裡主要是為了 Django 的 ImageField
    # ImageField 的 upload_to 函式會接收原始檔名，我們需要給它一個基礎檔名
    # 這裡的 unique_base 和 file_ext 主要是為了 `save()` 方法中的 `name` 參數
    unique_base_filename = str(uuid.uuid4())
    original_image_name = f"{unique_base_filename}{file_ext}"
    annotated_image_name = f"annotated_{unique_base_filename}{file_ext}"

    # 儲存原始圖片到 S3 (透過 DetectionRecord 的 ImageField)
    try:
        record.original_image.save(original_image_name, ContentFile(image_bytes), save=False)
        # 注意：save=False 只是將檔案內容和名稱與 ImageField 關聯起來，
        # 實際的資料庫記錄儲存和檔案上傳會在最後的 record.save() 中發生。
    except Exception as e:
        service_logger.error(f"Error saving original image for record (batch_job {record.batch_job_id if record.batch_job_id else 'N/A'}): {e}", exc_info=True)
        record.results_data = {** (record.results_data if isinstance(record.results_data, dict) else {}),
                               'original_image_error': f'Failed to save original image: {str(e)}'}
        # 即使原始圖片儲存失敗，我們還是嘗試儲存 record (帶有錯誤訊息)
        # 但這種情況比較嚴重，可能需要標記為處理失敗


    # 若有標註結果 (annotated_image_array 不是 None 且有內容)，則儲存標註圖到 S3
    if annotated_image_array is not None and annotated_image_array.size > 0:
        try:
            # 將 OpenCV 的 BGR array 轉換為 RGB
            img_rgb = cv2.cvtColor(annotated_image_array, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb) # 轉換為 Pillow Image 物件
            
            buffer = io.BytesIO() # 在記憶體中建立一個二進位流
            # 根據原始副檔名決定儲存格式
            image_format_name = 'JPEG' if file_ext.lower() in ['.jpg', '.jpeg'] else 'PNG'
            if image_format_name == 'JPEG':
                pil_img.save(buffer, format=image_format_name, quality=90) # 對 JPEG 設定品質
            else: # PNG 等格式不接受 quality 參數
                pil_img.save(buffer, format=image_format_name)
            buffer.seek(0) # 重置流的指針到開頭

            record.annotated_image.save(annotated_image_name, ContentFile(buffer.getvalue()), save=False)
        except Exception as e:
            service_logger.error(f"Error saving annotated image for record (batch_job {record.batch_job_id if record.batch_job_id else 'N/A'}): {e}", exc_info=True)
            # 記錄錯誤，但不影響 record 的整體儲存
            record.results_data = {** (record.results_data if isinstance(record.results_data, dict) else {}),
                                   'annotated_image_error': f'Failed to save annotated image: {str(e)}'}
    else:
        # 如果沒有標註結果，確保 annotated_image 欄位為 None (或者它預設就是)
        record.annotated_image = None


    # 3) 最後，儲存 DetectionRecord 實例到資料庫
    # 這次的 save() 會觸發模型中定義的 save() 方法，進而呼叫 calculate_severity_score()
    # 同時，ImageField 中設定的 save=False 的檔案也會在這一步被實際提交和上傳
    try:
        record.save()
        service_logger.info(f"Successfully processed and saved DetectionRecord ID {record.id} (BatchJob {record.batch_job_id if record.batch_job_id else 'N/A'})")
    except Exception as e:
        service_logger.error(f"Critical error saving DetectionRecord ID (intended: {record.id}, BatchJob {record.batch_job_id if record.batch_job_id else 'N/A'}): {e}", exc_info=True)
        # 如果連 record.save() 都失敗了，這是一個嚴重的問題
        # Celery task 應該捕獲這個錯誤並將對應的圖片處理標記為失敗
        raise # 重新拋出，讓 Celery task 處理

    return record