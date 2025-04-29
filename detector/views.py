# detector/views.py
from .models import DetectionRecord # 匯入模型
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
import os
import uuid
import cv2
import numpy as np
from .inference_utils import run_yolo_inference # 匯入接收路徑的推論函式
from .models import DetectionRecord # 匯入模型
from django.core.files.base import ContentFile # 用於從記憶體數據建立 Django 檔案物件
from django.core.files.storage import FileSystemStorage # 需要用來存暫存檔
import io
from PIL import Image

# (可選) 匯入 logging
# import logging
# logger = logging.getLogger(__name__)

def upload_detect_view(request):
    # 1. 初始化 context 字典
    context = {
        'uploaded_image_url': None,
        'annotated_image_url': None,
        'results': [],
        'error_message': None,
        'class_names': [],
        'record_id': None,
        'limit_notice': "系統僅保留最近 10 筆辨識紀錄。"
    }

    # 2. 嘗試獲取模型和類別名稱
    yolo_model = None
    try:
        from .apps import yolo_model
        if yolo_model is None:
            raise RuntimeError("YOLO model is not loaded.")
        if hasattr(yolo_model, 'names') and isinstance(yolo_model.names, dict):
            context['class_names'] = list(yolo_model.names.values())
        else:
            print("警告：無法從 yolo_model.names 獲取類別名稱。")
            context['class_names'] = [] # 確保是列表
    except Exception as e:
        error_message = f"載入模型或設定時出錯: {e}"
        print(error_message)
        context['error_message'] = error_message
        # 根據請求類型返回錯誤頁面
        return render(request, 'detector/upload_form.html', context)


    # 3. 處理 POST 請求
    if request.method == 'POST':
        # 再次檢查模型是否真的可用
        if yolo_model is None:
            context['error_message'] = "錯誤：辨識模型尚未成功載入。"
            return render(request, 'detector/upload_form.html', context)

        # 初始化變數
        uploaded_file = None
        new_record = None
        text_results = []
        annotated_array = None
        error_message = None
        uploaded_image_path_abs = None # 儲存暫存檔路徑
        unique_filename = ""         # 儲存唯一檔名 (不含路徑)

        # 4. 獲取並驗證上傳檔案
        if 'image_file' not in request.FILES:
            error_message = "錯誤：請求中未找到 'image_file'。"
            context['error_message'] = error_message; print(error_message)
            return render(request, 'detector/upload_form.html', context)

        uploaded_file = request.FILES['image_file']
        if not uploaded_file.content_type.startswith('image'):
            error_message = f"錯誤：請上傳圖片檔案，而非 {uploaded_file.content_type}。"
            context['error_message'] = error_message; print(error_message)
            return render(request, 'detector/upload_form.html', context)

        # --- 5. 先將上傳的圖片儲存到暫存位置 ---
        try:
            # 定義暫存資料夾路徑
            temp_upload_dir = os.path.join(settings.MEDIA_ROOT, 'temp_uploads')
            os.makedirs(temp_upload_dir, exist_ok=True) # 確保資料夾存在
            fs = FileSystemStorage(location=temp_upload_dir)

            # 產生唯一檔名
            file_ext = os.path.splitext(uploaded_file.name)[1]
            unique_filename = f"{uuid.uuid4()}{file_ext}"

            # 儲存暫存檔案，獲取基於 location 的相對名稱
            temp_saved_name = fs.save(unique_filename, uploaded_file)
            # 獲取暫存檔案的絕對路徑
            uploaded_image_path_abs = fs.path(temp_saved_name)
            print(f"圖片暫存於: {uploaded_image_path_abs}")

        except Exception as e:
            error_message = f"儲存臨時上傳檔案時發生錯誤: {e}"
            print(error_message); context['error_message'] = error_message
            # 即使暫存失敗也渲染結果頁面（會顯示錯誤）
            return render(request, 'detector/detection_result.html', context)

        # --- 6. 執行模型推論 (傳遞檔案路徑) ---
        try:
            print(f"開始執行推論 (檔案): {uploaded_image_path_abs}")
            confidence_threshold = 0.5 # 設定信心閾值
            # 呼叫接收路徑的推論函式
            annotated_array, text_results = run_yolo_inference(uploaded_image_path_abs, confidence_threshold)
            context['results'] = text_results # 先存入 context
            print(f"推論完成，偵測到 {len(text_results)} 個物件。")

        except RuntimeError as re: # 捕捉模型未載入錯誤
            error_message = f"模型推論錯誤: {re}"; print(error_message)
        except Exception as e:
            error_message = f"執行模型推論時發生錯誤: {e}"; print(error_message)

        # 如果推論出錯，設定錯誤訊息 (但不立刻 return，先執行 finally 刪除暫存檔)
        if error_message:
            context['error_message'] = error_message


        # --- 7. 建立並儲存資料庫記錄 ---
        # 無論推論是否成功，都嘗試儲存記錄 (如果 annotated_array 是 None 會存空值)
        # 但如果推論出錯，則不進行儲存DB這一步，直接跳到 finally 後渲染錯誤
        if not error_message:
            try:
                new_record = DetectionRecord()
                new_record.results_data = text_results

                # 從暫存路徑讀取原始檔案內容來儲存
                with open(uploaded_image_path_abs, 'rb') as f:
                    original_image_content = ContentFile(f.read())
                    # 使用之前產生的 unique_filename
                    new_record.original_image.save(unique_filename, original_image_content, save=False)

                # 儲存標註圖 (如果有的話)
                if annotated_array is not None:
                    img_rgb = cv2.cvtColor(annotated_array, cv2.COLOR_BGR2RGB)
                    pil_image = Image.fromarray(img_rgb)
                    buffer = io.BytesIO()
                    pil_image.save(buffer, format='JPEG', quality=90)
                    image_content = ContentFile(buffer.getvalue())
                    result_filename = f"result_{unique_filename}" # 檔名保持一致性
                    new_record.annotated_image.save(result_filename, image_content, save=False)

                new_record.save() # 儲存到資料庫
                print(f"新的辨識紀錄已儲存到資料庫，ID: {new_record.id}")
                context['record_id'] = new_record.id

                # 從 record 物件獲取 URL
                context['uploaded_image_url'] = new_record.original_image.url
                if new_record.annotated_image:
                    context['annotated_image_url'] = new_record.annotated_image.url

            except Exception as e:
                error_message = f"儲存辨識紀錄到資料庫時發生錯誤: {e}"; print(error_message)
                context['error_message'] = error_message
                # 即使儲存DB失敗，之前的 URL 可能已在 context 中，嘗試保留
                context['uploaded_image_url'] = context.get('uploaded_image_url')
                context['annotated_image_url'] = context.get('annotated_image_url')

        # --- 8. 自動清理舊紀錄 (在儲存成功 或 即使儲存失敗後都嘗試執行) ---
        # (如果希望只在儲存成功後清理，就把這段移入上面的 try)
        if not error_message: # 只在前面步驟沒錯時才嘗試清理
            try:
                records_to_keep = 10
                total_records = DetectionRecord.objects.count()

                if total_records > records_to_keep:
                    num_to_delete = total_records - records_to_keep
                    ids_to_delete = DetectionRecord.objects.order_by('uploaded_at').values_list('id', flat=True)[:num_to_delete]
                    records_to_delete = DetectionRecord.objects.filter(id__in=list(ids_to_delete))

                    print(f"紀錄超過 {records_to_keep} 筆，將刪除 {records_to_delete.count()} 筆最舊紀錄...")
                    count_deleted = 0
                    for record_to_delete in records_to_delete:
                        record_id_to_delete = record_to_delete.id
                        record_to_delete.delete()
                        count_deleted += 1
                        print(f"  已刪除紀錄 ID: {record_id_to_delete}")
                    print(f"舊紀錄清理完畢，共刪除 {count_deleted} 筆。")

            except Exception as e:
                print(f"警告：自動清理舊紀錄時發生錯誤: {e}")
                # 清理失敗通常不影響本次結果顯示

        # --- 9. 刪除暫存檔案 (使用 finally 確保執行) ---
        if uploaded_image_path_abs and os.path.exists(uploaded_image_path_abs):
            try:
                os.remove(uploaded_image_path_abs)
                print(f"已刪除暫存檔案: {uploaded_image_path_abs}")
            except Exception as e:
                print(f"刪除暫存檔案 {uploaded_image_path_abs} 時發生錯誤: {e}")


        # --- 10. 渲染結果頁面模板 ---
        # context 字典已包含所有需要的信息
        return render(request, 'detector/detection_result.html', context)

    # --- 處理 GET 請求 ---
    else: # request.method == 'GET'
        # 傳遞包含 limit_notice 和 可能存在的 class_names 的 context
        return render(request, 'detector/upload_form.html', context)
# 歷史紀錄列表視圖 
def detection_history_view(request):
    """
    顯示最近 10 筆辨識紀錄的列表。
    """
    # 從資料庫中查詢紀錄：
    # - DetectionRecord.objects：代表資料庫中所有 DetectionRecord 記錄
    # - .order_by('-uploaded_at')：依照 uploaded_at 欄位「降序」排列 (新的在前)
    # - [:10]：只選取查詢結果的前 10 筆
    latest_records = DetectionRecord.objects.order_by('-uploaded_at')[:10]

    # 準備要傳遞給模板的資料
    context = {
        'records': latest_records,
        'limit_notice': "僅顯示最近 10 筆辨識紀錄。" # 也可以在這裡傳遞提示
    }
    # 渲染結果頁面模板 detector/history.html 
    return render(request, 'detector/history.html', context)
# 歷史紀錄詳情視圖 
def detection_detail_view(request, record_id):
    """
    顯示單筆指定的辨識紀錄詳情。
    """
    # 嘗試根據從 URL 傳來的 record_id (UUID) 從資料庫獲取對應的紀錄
    # 如果找不到，get_object_or_404 會自動回傳 404 Not Found 頁面
    record = get_object_or_404(DetectionRecord, pk=record_id)

    # 準備要傳遞給模板的資料
    context = {
        # 從 record 物件的欄位獲取 URL
        'uploaded_image_url': record.original_image.url if record.original_image else None,
        'annotated_image_url': record.annotated_image.url if record.annotated_image else None,
        # 從 record 物件的 JSONField 獲取結果列表
        'results': record.results_data if record.results_data else [],
        'error_message': None, # 假設查看歷史紀錄時沒有錯誤
        'record_id': record.id,
        'limit_notice': "系統僅保留最近 10 筆辨識紀錄。",
        'class_names': [], # 預設為空，下面嘗試從模型獲取
        'record_timestamp': record.uploaded_at # 傳遞記錄的時間戳
    }

    # 嘗試獲取類別名稱 (如果模型已載入)
    try:
        from .apps import yolo_model
        if yolo_model and hasattr(yolo_model, 'names') and isinstance(yolo_model.names, dict):
            context['class_names'] = list(yolo_model.names.values())
    except Exception as e:
        print(f"獲取類別名稱時發生錯誤 (Detail View): {e}")
        # 即使獲取失敗，也要繼續渲染頁面

    # *** 重用 detection_result.html 模板來顯示詳情 ***
    return render(request, 'detector/detection_result.html', context)

