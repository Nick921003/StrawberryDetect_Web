## detector/views.py
import os
import uuid
import base64
import json
import traceback
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.core.files.base import ContentFile
from .models import DetectionRecord
from .services import process_image_bytes
import logging

view_logger = logging.getLogger(__name__)


def upload_detect_view(request):
    """使用者上傳網頁版流程：上傳檔案後呼叫 service 處理，再清理舊紀錄。"""
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

    if request.method == 'POST':
        try:
            if 'image_file' not in request.FILES:
                raise ValueError("請求中未找到 'image_file'.")
            uploaded_file = request.FILES['image_file']
            if not uploaded_file.content_type.startswith('image'):
                raise ValueError(f"請上傳圖片檔案, 而非 {uploaded_file.content_type}.")

            image_bytes = uploaded_file.read()
            file_ext = os.path.splitext(uploaded_file.name)[1].lower() or '.jpg'

            # 使用 service 處理影像
            record = process_image_bytes(image_bytes, file_ext)

            # 組成 context
            context.update({
                'record_id': record.id,
                'uploaded_image_url': record.original_image.url,
                'annotated_image_url': record.annotated_image.url if record.annotated_image else None,
                'results': record.results_data
            })

            # 清理舊紀錄
            records_to_keep = 10
            total = DetectionRecord.objects.count()
            if total > records_to_keep:
                old_ids = DetectionRecord.objects.order_by('uploaded_at') \
                    .values_list('id', flat=True)[:total - records_to_keep]
                DetectionRecord.objects.filter(id__in=old_ids).delete()

            return render(request, 'detector/detection_result.html', context)

        except Exception as e:
            view_logger.error(f"處理上傳請求時發生錯誤: {e}", exc_info=True)
            context['error_message'] = "處理上傳請求時發生錯誤，請稍後再試。"
            return render(request, 'detector/upload_form.html', context)

    return render(request, 'detector/upload_form.html', context)


@csrf_exempt 
def api_process_view(request):
    """API endpoint: 接收 base64 圖片，觸發 service 流程並回傳結果"""
    if request.method != 'POST':
        return HttpResponseBadRequest("只接受 POST 請求")
    try:
        payload = json.loads(request.body)
        img_b64 = payload.get('image_base64')
        if not img_b64:
            return HttpResponseBadRequest("缺少 image_base64 欄位")

        image_bytes = base64.b64decode(img_b64)
        record = process_image_bytes(image_bytes, file_ext='.jpg')

        return JsonResponse({
            'record_id': str(record.id),
            'orig_url': record.original_image.url,
            'annotated_url': record.annotated_image.url if record.annotated_image else None,
            'results': record.results_data
        }, status=201)
    except Exception as e:
        view_logger.error(f"API 處理失敗: {e}\n{traceback.format_exc()}")
        return JsonResponse({'error': str(e)}, status=500)


def detection_history_view(request):
    latest = DetectionRecord.objects.order_by('-uploaded_at')[:10]
    return render(request, 'detector/history.html', {'records': latest, 'limit_notice': "僅顯示最近 10 筆辨識紀錄。"})


def detection_detail_view(request, record_id):
    record = get_object_or_404(DetectionRecord, pk=record_id)
    context = {
        'uploaded_image_url': record.original_image.url if record.original_image else None,
        'annotated_image_url': record.annotated_image.url if record.annotated_image else None,
        'results': record.results_data or [],
        'record_id': record.id,
        'limit_notice': "系統僅保留最近 10 筆辨識紀錄。",
    }
    return render(request, 'detector/detection_result.html', context)
