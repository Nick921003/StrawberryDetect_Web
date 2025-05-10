import os
import uuid
import cv2
import io
import traceback
from pathlib import Path
from PIL import Image
from django.shortcuts import render, get_object_or_404
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from .models import DetectionRecord
from .inference_utils import run_yolo_inference_on_image_data
import logging

view_logger = logging.getLogger(__name__)

# 上傳圖片並執行辨識的視圖函式
def upload_detect_view(request):
    view_logger.debug("--- 進入 upload_detect_view ---")
    context = {
        'uploaded_image_url': None,
        'annotated_image_url': None,
        'results': [],
        'error_message': None,
        'class_names': [],
        'record_id': None,
        'limit_notice': "系統僅保留最近 10 筆辨識紀錄。"
    }

    # 檢查 YOLO 模型是否載入
    try:
        from .apps import yolo_model
        if yolo_model is None:
            raise RuntimeError("YOLO model is not loaded.")
        if hasattr(yolo_model, 'names') and isinstance(yolo_model.names, dict):
            context['class_names'] = list(yolo_model.names.values())
    except Exception as e:
        view_logger.error(f"載入 YOLO 模型時出錯: {e}", exc_info=True)
        context['error_message'] = f"載入 YOLO 模型時出錯: {e}"
        return render(request, 'detector/upload_form.html', context)

    # 處理 POST 請求
    if request.method == 'POST':
        try:
            # 驗證上傳檔案
            if 'image_file' not in request.FILES:
                raise ValueError("請求中未找到 'image_file'。")
            uploaded_file = request.FILES['image_file']
            if not uploaded_file.content_type.startswith('image'):
                raise ValueError(f"請上傳圖片檔案，而非 {uploaded_file.content_type}。")

            # 讀取圖片內容
            original_filename = uploaded_file.name
            file_ext = os.path.splitext(original_filename)[1].lower() or '.jpg'
            unique_filename_base = str(uuid.uuid4())
            image_bytes_for_s3 = uploaded_file.read()

            # 執行 YOLO 推論
            annotated_array, text_results = run_yolo_inference_on_image_data(image_bytes_for_s3, confidence_threshold=0.5)
            context['results'] = text_results

            # 儲存圖片與結果到資料庫
            new_record = DetectionRecord()
            new_record.results_data = text_results

            # 儲存原始圖片
            s3_original_filename = f"{unique_filename_base}{file_ext}"
            original_image_content = ContentFile(image_bytes_for_s3, name=s3_original_filename)
            new_record.original_image.save(s3_original_filename, original_image_content, save=False)

            # 儲存標註圖片
            if annotated_array is not None and annotated_array.size > 0:
                img_rgb = cv2.cvtColor(annotated_array, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(img_rgb)
                buffer = io.BytesIO()
                pil_image_format = 'JPEG' if file_ext in ['.jpg', '.jpeg'] else 'PNG'
                pil_image.save(buffer, format=pil_image_format, quality=90)
                buffer.seek(0)
                s3_annotated_filename = f"result_{unique_filename_base}{file_ext}"
                annotated_image_content = ContentFile(buffer.getvalue(), name=s3_annotated_filename)
                new_record.annotated_image.save(s3_annotated_filename, annotated_image_content, save=False)

            new_record.save()
            context['record_id'] = new_record.id
            context['uploaded_image_url'] = new_record.original_image.url
            context['annotated_image_url'] = new_record.annotated_image.url if new_record.annotated_image else None

            # 清理舊紀錄
            records_to_keep = 10
            total_records = DetectionRecord.objects.count()
            if total_records > records_to_keep:
                ids_to_delete = DetectionRecord.objects.order_by('uploaded_at').values_list('id', flat=True)[:total_records - records_to_keep]
                DetectionRecord.objects.filter(id__in=ids_to_delete).delete()

            return render(request, 'detector/detection_result.html', context)

        except Exception as e:
            view_logger.error(f"處理上傳請求時發生錯誤: {e}", exc_info=True)
            context['error_message'] = "處理上傳請求時發生錯誤，請稍後再試。"
            return render(request, 'detector/upload_form.html', context)

    # 處理 GET 請求
    return render(request, 'detector/upload_form.html', context)

# 歷史紀錄列表視圖
def detection_history_view(request):
    latest_records = DetectionRecord.objects.order_by('-uploaded_at')[:10]
    context = {'records': latest_records, 'limit_notice': "僅顯示最近 10 筆辨識紀錄。"}
    return render(request, 'detector/history.html', context)

# 歷史紀錄詳情視圖
def detection_detail_view(request, record_id):
    record = get_object_or_404(DetectionRecord, pk=record_id)
    context = {
        'uploaded_image_url': record.original_image.url if record.original_image else None,
        'annotated_image_url': record.annotated_image.url if record.annotated_image else None,
        'results': record.results_data if record.results_data else [],
        'record_id': record.id,
        'limit_notice': "系統僅保留最近 10 筆辨識紀錄。",
    }
    return render(request, 'detector/detection_result.html', context)
