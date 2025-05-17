from django.urls import path
from django.urls import include # 用於包含其他 URLconf
from . import views # 從當前資料夾匯入 views.py


# 定義 App 的命名空間，方便在模板中引用 URL
app_name = 'detector'

urlpatterns = [
    path('', views.upload_detect_view, name='upload_detect'),

    # 1. 歷史紀錄的主入口頁面 (選擇頁面)
    path('history/', views.history_landing_view, name='detection_history_landing'), # 或者你喜歡的 name

    # 2. 自走車批次辨識歷史列表頁面
    path('batch-history/', views.batch_detection_history_view, name='batch_detection_history'),

    # 3. 手動上傳辨識歷史列表頁面
    # 我們需要一個 View 來處理這個，可以修改舊的 detection_history_view
    # 或者創建一個新的 view_manual_history。
    # 假設我們修改舊的 detection_history_view，使其只顯示手動上傳的記錄。
    path('manual-history/', views.detection_history_view, name='manual_detection_history'),
    
    # 4. 單筆"手動上傳"歷史紀錄詳情頁面 (保持不變，因為它接收 record_id)
    # 它的連結會從 manual-history 頁面過來
    path('manual-history/<uuid:record_id>/', views.detection_detail_view, name='detection_detail'), # 注意 URL name 保持為 detection_detail

    # 5. 我們下一步 (2.2) 要創建的「批次辨識結果詳情」頁面的 URL，先預留 name
    path('batch-result/<uuid:batch_job_id>/', views.batch_detection_detail_view, name='batch_detection_detail'),

]