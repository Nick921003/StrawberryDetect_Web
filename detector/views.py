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
from .models import DetectionRecord, BatchDetectionJob
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

            # 為手動上傳創建一個 DetectionRecord 實例 (batch_job 為 None)
            # 這個 record 實例還沒有儲存到資料庫，也沒有圖片或結果數據
            manual_record_instance = DetectionRecord() 
            # 注意：對於手動上傳，manual_record_instance.batch_job 會是 None，這是正確的。

            # 2. 使用 service 處理影像，並傳入我們創建的實例
            record = process_image_bytes(
                image_bytes=image_bytes, 
                file_ext=file_ext,
                # confidence 參數可以從 settings 或 request 中獲取，如果需要的話
                confidence=0.5, # 或者你希望手動上傳使用不同的信心閾值
                detection_record_instance=manual_record_instance # <-- 傳遞實例
            )
            # process_image_bytes 內部會填充這個 record 並儲存它

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
    """
    顯示手動上傳的辨識紀錄列表 (DetectionRecord 中 batch_job 為 NULL 的)。
    """
    # 只查詢 batch_job 為 NULL 的 DetectionRecord
    manual_records = DetectionRecord.objects.filter(batch_job__isnull=True).order_by('-uploaded_at')[:10]
    # 你可以保留或調整 [:10] 來限制數量

    context = {
        'records': manual_records,
        'page_title': "手動上傳辨識紀錄",
        'limit_notice': "僅顯示最近 10 筆手動上傳的辨識紀錄。" # 或者你希望顯示所有手動記錄
    }
    # 這個 View 應該繼續使用 'detector/history.html' 模板，
    # 或者你可以為它創建一個新的 'manual_history.html' 模板，如果內容差異很大。
    # 假設 'detector/history.html' 模板可以通用地顯示 DetectionRecord 列表。
    return render(request, 'detector/history.html', context)


def detection_detail_view(request, record_id):
    """
    顯示單張 DetectionRecord 的詳細辨識結果。
    """
    record = get_object_or_404(DetectionRecord, pk=record_id)
    
    # 從請求的 GET 參數中獲取 from_batch (如果有的話)
    from_batch_id = request.GET.get('from_batch') # 獲取查詢參數

    # 準備 class_names 給模板中的篩選器 (如果你的結果頁有類別篩選器的話)
    # 這部分邏輯你原本可能就有，如果 yolo_model 在 apps.py 中正確載入
    class_names_for_template = []
    try:
        from .apps import yolo_model # 確保 yolo_model 能被正確引用
        if yolo_model and hasattr(yolo_model, 'names') and isinstance(yolo_model.names, dict):
            class_names_for_template = list(yolo_model.names.values())
    except ImportError:
        view_logger.warning("YOLO model could not be imported for class_names in detection_detail_view.")
    except Exception as e:
        view_logger.error(f"Error getting class_names in detection_detail_view: {e}", exc_info=True)


    context = {
        'record': record, # 傳遞整個 record 物件，模板中可以訪問 record.original_image.url 等
        'uploaded_image_url': record.original_image.url if record.original_image else None,
        'annotated_image_url': record.annotated_image.url if record.annotated_image else None,
        'results': record.results_data or [],
        'record_id': record.id, # 雖然 record 物件裡有 id，但明確傳遞有時更方便
        'severity_score': record.severity_score, # <-- 新增：傳遞嚴重程度評分
        'class_names': class_names_for_template, # <-- 確保傳遞 class_names
        # 'limit_notice': "系統僅保留最近 10 筆辨識紀錄。", # 這個提示可能不再適用於單圖詳情頁
        'from_batch_id': from_batch_id, # <-- 新增：將 from_batch_id 傳遞給模板
        'page_title': f"辨識結果詳情 ({str(record.id)[:8]}...)",
    }
    return render(request, 'detector/detection_result.html', context)

def batch_detection_history_view(request):
    """
    顯示所有批次辨識任務的歷史列表。
    """
    # 查詢所有的 BatchDetectionJob 記錄，按創建時間倒序排列 (最新的在前面)
    batch_jobs = BatchDetectionJob.objects.all().order_by('-created_at')
    
    # 也可以在這裡加入分頁邏輯，如果批次任務很多的話
    # from django.core.paginator import Paginator
    # paginator = Paginator(batch_jobs, 10) # 每頁顯示 10 個批次任務
    # page_number = request.GET.get('page')
    # page_obj = paginator.get_page(page_number)

    context = {
        'batch_jobs': batch_jobs, # 或者 page_obj 如果使用分頁
        'page_title': "批次辨識歷史紀錄", # 給模板一個頁面標題
        'limit_notice': "顯示所有已提交的批次辨識任務。" # 可以根據需要修改提示
    }
    return render(request, 'detector/batch_history.html', context)

def batch_detection_detail_view(request, batch_job_id):
    """
    顯示特定批次辨識任務的詳細結果。
    包括批次摘要和該批次下所有圖片的辨識記錄 (按嚴重程度排序)。
    """
    # 根據傳入的 batch_job_id 獲取 BatchDetectionJob 實例，如果不存在則返回 404
    batch_job = get_object_or_404(BatchDetectionJob, pk=batch_job_id)

    # 查詢所有與此 BatchDetectionJob 相關聯的 DetectionRecord 實例
    # 使用 related_name 'detection_records' 進行反向查詢
    # 並按照 severity_score 降序排列 (None 值排在後面或前面，取決於資料庫，通常 NULLS LAST)
    # 為了確保 None 值排在後面，可以這樣處理 (如果 severity_score 允許 NULL):
    # from django.db.models import F, Q, Func
    # detection_records = batch_job.detection_records.all().order_by(
    #     F('severity_score').desc(nulls_last=True)
    # )
    # 或者，如果 severity_score 不會有 NULL (例如預設為0)，可以直接：
    detection_records = batch_job.detection_records.all().order_by('-severity_score', '-uploaded_at')
    # 增加按上傳時間排序作為次要排序標準

    # (可選) 準備批次摘要數據，如果 summary_results 欄位還未被自動計算填充
    # 這裡的 summary_results 應該是由 Celery 任務在所有子任務完成後計算並填入 BatchDetectionJob 模型的
    # 如果還沒實現自動計算，這裡可以先顯示 "摘要正在生成中" 或顯示基本統計
    batch_summary = batch_job.summary_results
    if not batch_summary:
        # 如果 summary_results 為空，可以嘗試即時生成一個非常基礎的摘要
        # 注意：這部分邏輯最好是放在 Celery 任務中異步完成，避免請求超時
        # 這裡只做一個非常簡單的示例，不建議在 View 中做複雜計算
        num_healthy = 0
        num_angular_leaf_spot = 0
        for record in detection_records:
            if record.results_data and isinstance(record.results_data, list):
                for res in record.results_data:
                    if res.get('class') == 'healthy':
                        num_healthy +=1
                    elif res.get('class') == 'angular leaf spot':
                        num_angular_leaf_spot +=1
        
        if batch_job.total_images_found > 0:
            batch_summary = {
                "message": f"初步分析：共處理 {batch_job.total_images_found} 張圖片。",
                "stats": {
                    "檢測到健康植株的圖片數 (估計)": num_healthy, # 這不是圖片數，是檢測框數
                    "檢測到角斑病的圖片數 (估計)": num_angular_leaf_spot, # 同上
                    "成功處理圖片數": batch_job.images_processed_successfully,
                    "處理失敗圖片數": batch_job.images_failed_to_process,
                },
                "overall_status_guess": "多數健康" if num_healthy > num_angular_leaf_spot else "需注意病害情況"
            }
            # 實際上，summary_results 應該更複雜，例如：
            # batch_summary = {
            #     "overall_health_description": "田區整體健康狀況良好，僅少量植株出現角斑病初期症狀。",
            #     "disease_statistics": {
            #         "angular_leaf_spot": {"count": 5, "average_severity": 0.6},
            #         "healthy_plants_ratio": 0.85
            #     },
            #     "recommendations": "建議對檢測到角斑病的區域進行觀察，並考慮預防性措施。"
            # }
        else:
            batch_summary = {"message": "此批次沒有找到圖片或摘要尚未生成。"}


    context = {
        'batch_job': batch_job,
        'detection_records': detection_records,
        'batch_summary': batch_summary, # 傳遞批次摘要
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
