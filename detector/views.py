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
from django.apps import apps # <-- 新增：匯入 Django apps 模組，這是標準做法
from .models import DetectionRecord, BatchDetectionJob
from .services import process_image_bytes
from .retention_manager import DataRetentionManager
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

    # --- ↓↓↓ 修改區塊開始 ↓↓↓ ---
    # 檢查 YOLO 模型是否載入
    try:
        # 修改：改用標準方式從 AppConfig 獲取模型
        yolo_model = apps.get_app_config('detector').yolo_model 
        
        if yolo_model is None:
            raise RuntimeError("YOLO model is not loaded.")
            
        if hasattr(yolo_model, 'names') and isinstance(yolo_model.names, dict):
            context['class_names'] = list(yolo_model.names.values())
            
    except Exception as e:
        view_logger.error(f"載入 YOLO 模型時出錯: {e}", exc_info=True)
        context['error_message'] = f"載入 YOLO 模型時出錯: {e}"
        return render(request, 'detector/upload_form.html', context)
    # --- ↑↑↑ 修改區塊結束 ↑↑↑ ---

    if request.method == 'POST':
        try:
            if 'image_file' not in request.FILES:
                raise ValueError("請求中未找到 'image_file'.")
            uploaded_file = request.FILES['image_file']
            if not uploaded_file.content_type.startswith('image'):
                raise ValueError(f"請上傳圖片檔案, 而非 {uploaded_file.content_type}.")

            image_bytes = uploaded_file.read()
            file_ext = os.path.splitext(uploaded_file.name)[1].lower() or '.jpg'

            # 為手動上傳創建一個 DetectionRecord 實例 (batch_job 為 None)
            manual_record_instance = DetectionRecord() 

            # 2. 使用 service 處理影像，並傳入我們創建的實例
            record = process_image_bytes(
                image_bytes=image_bytes, 
                file_ext=file_ext,
                confidence=0.5,
                detection_record_instance=manual_record_instance
            )
            
            context.update({
                'record_id': record.id,
                'uploaded_image_url': record.original_image.url,
                'annotated_image_url': record.annotated_image.url if record.annotated_image else None,
                'results': record.results_data
            })

            # 3. 清理舊的手動上傳記錄
            try:
                DataRetentionManager().run_immediate_manual_cleanup()
            except Exception as cleanup_exc:
                view_logger.error(f"在 View 中執行即時手動記錄清理時發生錯誤: {cleanup_exc}", exc_info=True)

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
        manual_record_instance = DetectionRecord()
        record = process_image_bytes(image_bytes, file_ext='.jpg', detection_record_instance=manual_record_instance)

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
    """
    顯示手動上傳的辨識紀錄列表 (DetectionRecord 中 batch_job 為 NULL 的)。
    """
    manual_records = DetectionRecord.objects.filter(batch_job__isnull=True).order_by('-uploaded_at')[:10]
    context = {
        'records': manual_records,
        'page_title': "手動上傳辨識紀錄",
        'limit_notice': "僅顯示最近 10 筆手動上傳的辨識紀錄。"
    }
    return render(request, 'detector/history.html', context)

def detection_detail_view(request, record_id):
    """
    顯示單張 DetectionRecord 的詳細辨識結果。
    """
    record = get_object_or_404(DetectionRecord, pk=record_id)
    from_batch_id = request.GET.get('from_batch')
    class_names_for_template = []
    
    # --- ↓↓↓ 修改區塊開始 ↓↓↓ ---
    try:
        # 修改：改用標準方式從 AppConfig 獲取模型
        yolo_model = apps.get_app_config('detector').yolo_model
        
        if yolo_model and hasattr(yolo_model, 'names') and isinstance(yolo_model.names, dict):
            class_names_for_template = list(yolo_model.names.values())
            
    except Exception as e:
        # 修改：移除了 ImportError，因為我們不再直接 import
        view_logger.error(f"Error getting class_names in detection_detail_view: {e}", exc_info=True)
    # --- ↑↑↑ 修改區塊結束 ↑↑↑ ---

    context = {
        'record': record,
        'uploaded_image_url': record.original_image.url if record.original_image else None,
        'annotated_image_url': record.annotated_image.url if record.annotated_image else None,
        'results': record.results_data or [],
        'record_id': record.id,
        'severity_score': record.severity_score,
        'class_names': class_names_for_template,
        'from_batch_id': from_batch_id,
        'page_title': f"辨識結果詳情 ({str(record.id)[:8]}...)",
    }
    return render(request, 'detector/detection_result.html', context)

def batch_detection_history_view(request):
    """
    顯示所有批次辨識任務的歷史列表。
    """
    batch_jobs = BatchDetectionJob.objects.all().order_by('-created_at')
    context = {
        'batch_jobs': batch_jobs,
        'page_title': "批次辨識歷史紀錄",
        'limit_notice': "顯示所有已提交的批次辨識任務。"
    }
    return render(request, 'detector/batch_history.html', context)

def batch_detection_detail_view(request, batch_job_id):
    """

    顯示特定批次辨識任務的詳細結果。
    """
    batch_job = get_object_or_404(BatchDetectionJob, pk=batch_job_id)
    detection_records = batch_job.detection_records.all().order_by('-severity_score', '-uploaded_at')

    batch_summary = batch_job.summary_results
    if not batch_summary:
        batch_summary = {"message": "摘要資訊正在生成中，請稍後重新整理頁面。"}

    context = {
        'batch_job': batch_job,
        'detection_records': detection_records,
        'batch_summary': batch_summary,
        'page_title': f"批次任務詳情 ({batch_job_id})",
    }
    return render(request, 'detector/batch_detail_result.html', context)

def history_landing_view(request):
    """
    顯示歷史紀錄的選擇頁面 (自走車批次 vs 手動上傳)。
    """
    context = {
        'page_title': "查看歷史紀錄"
    }
    return render(request, 'detector/history_landing.html', context)