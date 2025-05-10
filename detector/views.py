# detector/views.py
from pathlib import Path
from .models import DetectionRecord # 匯入模型
from django.shortcuts import render, get_object_or_404 # redirect 可能不再需要，視您的流程而定
from django.conf import settings
import os
import uuid
import cv2
# import numpy as np # 似乎沒有直接使用 np，除非 run_yolo_inference 回傳的 annotated_array 需要特別處理
from .inference_utils import run_yolo_inference # 匯入接收路徑的推論函式
# from .models import DetectionRecord # 重複匯入了，移除一個
from django.core.files.base import ContentFile # 用於從記憶體數據建立 Django 檔案物件
from django.core.files.storage import FileSystemStorage # 需要用來存暫存檔
import io
from PIL import Image
import traceback # 用於捕捉和打印錯誤的詳細資訊

from django.core.files.storage import default_storage # 用於檢查 default_storage
import logging
view_logger = logging.getLogger(__name__) # Logger 名稱會是 'detector.views'

# 上傳圖片並執行辨識的視圖函式
def upload_detect_view(request):
    view_logger.debug("--- 進入 upload_detect_view ---")
    # 以下檢查 default_storage 的日誌，在確認 S3 設定正確後，可以考慮移除或設為更低級別
    view_logger.debug(f"當前 default_storage 類型: {type(default_storage)}")
    view_logger.debug(f"當前 default_storage 類別名稱: {default_storage.__class__.__name__}")
    if hasattr(default_storage, 'bucket_name'):
        view_logger.debug(f"Default storage bucket_name: {default_storage.bucket_name}")
    if hasattr(default_storage, 'location'):
        view_logger.debug(f"Default storage location: {default_storage.location}")
    # --- 「極簡儲存測試」區塊已移除 ---

    context = {
        'uploaded_image_url': None,
        'annotated_image_url': None,
        'results': [],
        'error_message': None,
        'class_names': [],
        'record_id': None,
        'limit_notice': "系統僅保留最近 10 筆辨識紀錄。"
    }

    try:
        from .apps import yolo_model # 嘗試從 app config 獲取已載入的模型
        if yolo_model is None:
            # 這種情況理論上不應該發生，因為 apps.py 的 ready() 應該已經載入
            # 但如果發生，這是一個嚴重的配置問題
            view_logger.error("YOLO 模型實例在 .apps 中未找到或為 None。")
            raise RuntimeError("YOLO model is not loaded.")
        if hasattr(yolo_model, 'names') and isinstance(yolo_model.names, dict):
            context['class_names'] = list(yolo_model.names.values())
        else:
            view_logger.warning("無法從 yolo_model.names 獲取類別名稱，或格式不正確。")
            context['class_names'] = []
    except Exception as e:
        error_message_init = f"載入 YOLO 模型或設定時出錯: {e}"
        view_logger.error(error_message_init, exc_info=True) # 記錄錯誤及 traceback
        context['error_message'] = error_message_init
        return render(request, 'detector/upload_form.html', context)

    if request.method == 'POST':
        uploaded_file = None
        new_record = None
        text_results = []
        annotated_array = None
        uploaded_image_path_abs = None
        unique_filename_base = ""
        file_ext = ""

        try:
            # yolo_model 在 POST 開始時應已確認載入，這裡不再重複檢查以簡化流程

            if 'image_file' not in request.FILES:
                context['error_message'] = "錯誤：請求中未找到 'image_file'。"
                view_logger.warning(context['error_message'])
                return render(request, 'detector/upload_form.html', context)

            uploaded_file = request.FILES['image_file']
            if not uploaded_file.content_type.startswith('image'):
                context['error_message'] = f"錯誤：請上傳圖片檔案，而非 {uploaded_file.content_type}。"
                view_logger.warning(context['error_message'])
                return render(request, 'detector/upload_form.html', context)

            # --- 5. 先將上傳的圖片儲存到本地暫存位置 ---
            temp_upload_dir_name = 'temp_uploads'
            base_dir_path = Path(settings.BASE_DIR) # settings.BASE_DIR 應該已經是 Path 物件
            temp_upload_dir_abs_str = str(base_dir_path / temp_upload_dir_name)

            os.makedirs(temp_upload_dir_abs_str, exist_ok=True)
            fs = FileSystemStorage(location=temp_upload_dir_abs_str)

            original_filename = uploaded_file.name
            file_ext = os.path.splitext(original_filename)[1].lower()
            unique_filename_base = str(uuid.uuid4())
            unique_temp_filename = f"{unique_filename_base}{file_ext}"

            temp_saved_name = fs.save(unique_temp_filename, uploaded_file)
            uploaded_image_path_abs = fs.path(temp_saved_name)
            view_logger.debug(f"圖片已暫存於本地: {uploaded_image_path_abs}")

            # --- 6. 執行模型推論 ---
            view_logger.info(f"開始對圖片 {unique_filename_base}{file_ext} 進行YOLO推論。")
            confidence_threshold = 0.5 # 或從 settings/request 獲取
            annotated_array, text_results = run_yolo_inference(uploaded_image_path_abs, confidence_threshold)
            context['results'] = text_results
            view_logger.info(f"YOLO推論完成，偵測到 {len(text_results)} 個物件。")

            # --- 7. 建立並儲存資料庫記錄 (檔案會上傳到 S3) ---
            new_record = DetectionRecord()
            new_record.results_data = text_results

            s3_original_filename = f"{unique_filename_base}{file_ext}"
            with open(uploaded_image_path_abs, 'rb') as f_original:
                original_image_content = ContentFile(f_original.read(), name=s3_original_filename)
                # ImageField 的 save 方法會處理上傳到 S3 (如果 default_storage 是 S3)
                new_record.original_image.save(s3_original_filename, original_image_content, save=False)
            view_logger.debug(f"原始圖片 '{s3_original_filename}' 已準備好，將透過 ImageField.save() 上傳到 S3。")

            if annotated_array is not None and annotated_array.size > 0:
                img_rgb = cv2.cvtColor(annotated_array, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(img_rgb)
                buffer = io.BytesIO()
                annotated_file_ext = file_ext if file_ext in ['.jpg', '.jpeg', '.png'] else '.jpg'
                pil_image_format = 'JPEG' if annotated_file_ext in ['.jpg', '.jpeg'] else 'PNG'
                pil_image.save(buffer, format=pil_image_format, quality=90)
                
                s3_annotated_filename = f"result_{unique_filename_base}{annotated_file_ext}"
                annotated_image_content = ContentFile(buffer.getvalue(), name=s3_annotated_filename)
                new_record.annotated_image.save(s3_annotated_filename, annotated_image_content, save=False)
                view_logger.debug(f"標註圖片 '{s3_annotated_filename}' 已準備好，將透過 ImageField.save() 上傳到 S3。")
            else:
                view_logger.info("沒有標註結果陣列或陣列為空，不儲存標註圖片。")

            new_record.save() # 實際儲存到資料庫，並觸發 S3 上傳 (由 ImageField 的 save 方法完成)
            view_logger.info(f"新的辨識紀錄已儲存 (ID: {new_record.id})，相關檔案應已上傳到 S3。")
            view_logger.debug(f"S3 Original Image URL from Django: {new_record.original_image.url}")
            if new_record.annotated_image and new_record.annotated_image.name:
                view_logger.debug(f"S3 Annotated Image URL from Django: {new_record.annotated_image.url}")
            
            context['record_id'] = new_record.id
            context['uploaded_image_url'] = new_record.original_image.url
            if new_record.annotated_image:
                context['annotated_image_url'] = new_record.annotated_image.url

            # --- 8. 自動清理舊紀錄 ---
            records_to_keep = 10 # 或從 settings 獲取
            total_records = DetectionRecord.objects.count()
            if total_records > records_to_keep:
                num_to_delete = total_records - records_to_keep
                ids_to_delete = DetectionRecord.objects.order_by('uploaded_at').values_list('id', flat=True)[:num_to_delete]
                view_logger.info(f"紀錄超過 {records_to_keep} 筆，準備刪除 {len(ids_to_delete)} 筆最舊紀錄...")
                count_deleted = 0
                for record_id_to_delete in ids_to_delete:
                    try:
                        record_to_del = DetectionRecord.objects.get(id=record_id_to_delete)
                        record_to_del.delete() # 這會觸發模型 delete 方法，進而刪除 S3 檔案
                        count_deleted += 1
                        view_logger.debug(f"  已刪除紀錄 ID: {record_id_to_delete} 及其 S3 檔案。")
                    except DetectionRecord.DoesNotExist:
                        view_logger.warning(f"  嘗試刪除紀錄 ID: {record_id_to_delete} 時發現其不存在。")
                    except Exception as del_ex:
                        view_logger.error(f"  刪除紀錄 ID: {record_id_to_delete} 時發生錯誤: {del_ex}", exc_info=True)
                view_logger.info(f"舊紀錄清理完畢，共刪除 {count_deleted} 筆。")

            return render(request, 'detector/detection_result.html', context)

        except Exception as e:
            view_logger.error(f"處理上傳請求時發生未預期錯誤: {e}", exc_info=True) # 記錄完整 traceback
            context['error_message'] = f"處理上傳請求時發生內部錯誤，請稍後再試或聯繫管理員。" # 給使用者的通用錯誤訊息
            
            # 根據錯誤發生的階段，決定返回哪個頁面
            if uploaded_file is None or (hasattr(uploaded_file, 'content_type') and not uploaded_file.content_type.startswith('image')):
                return render(request, 'detector/upload_form.html', context)
            else:
                return render(request, 'detector/detection_result.html', context)
        finally:
            # 清理本地暫存檔案
            if uploaded_image_path_abs and os.path.exists(uploaded_image_path_abs):
                try:
                    os.remove(uploaded_image_path_abs)
                    view_logger.debug(f"已刪除本地暫存檔案: {uploaded_image_path_abs}")
                except Exception as e_remove:
                    view_logger.error(f"刪除本地暫存檔案 {uploaded_image_path_abs} 時發生錯誤: {e_remove}", exc_info=True)

    else: # request.method == 'GET'
        return render(request, 'detector/upload_form.html', context)

# 歷史紀錄列表視圖
def detection_history_view(request):
    view_logger.debug("--- 進入 detection_history_view ---")
    latest_records = DetectionRecord.objects.order_by('-uploaded_at')[:10]
    context = {
        'records': latest_records,
        'limit_notice': "僅顯示最近 10 筆辨識紀錄。"
    }
    return render(request, 'detector/history.html', context)

# 歷史紀錄詳情視圖
def detection_detail_view(request, record_id):
    view_logger.debug(f"--- 進入 detection_detail_view (record_id: {record_id}) ---")
    record = get_object_or_404(DetectionRecord, pk=record_id)
    context = {
        'uploaded_image_url': record.original_image.url if record.original_image else None,
        'annotated_image_url': record.annotated_image.url if record.annotated_image else None,
        'results': record.results_data if record.results_data else [],
        'error_message': None,
        'record_id': record.id,
        'limit_notice': "系統僅保留最近 10 筆辨識紀錄。",
        'class_names': [],
        'record_timestamp': record.uploaded_at
    }
    try:
        from .apps import yolo_model
        if yolo_model and hasattr(yolo_model, 'names') and isinstance(yolo_model.names, dict):
            context['class_names'] = list(yolo_model.names.values())
    except Exception as e:
        view_logger.warning(f"獲取類別名稱時發生錯誤 (Detail View for record {record_id}): {e}", exc_info=True)
    return render(request, 'detector/detection_result.html', context)
