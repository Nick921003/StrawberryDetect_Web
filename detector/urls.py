from django.urls import path
from . import views # 從當前資料夾匯入 views.py

# 定義 App 的命名空間，方便在模板中引用 URL
app_name = 'detector'

urlpatterns = [
    # 將 App 的根路徑 (例如 未來可能是 /detector/) 對應到 upload_detect_view 函式
    # 我們給這個 URL pattern 取名為 'upload_detect'
    # 這樣在模板中就可以用 {% url 'detector:upload_detect' %} 來找到它
    path('', views.upload_detect_view, name='upload_detect'),
    # 歷史紀錄列表頁面
    path('history/', views.detection_history_view, name='detection_history'),
    # 單筆歷史紀錄詳情頁面
    # 使用 <uuid:record_id> 來捕捉 URL 中的 UUID 字串
    # Django 會自動將 URL 中這部分的值作為名為 record_id 的參數傳遞給視圖函式
    path('history/<uuid:record_id>/', views.detection_detail_view, name='detection_detail'),
]