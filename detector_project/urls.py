# detector_project/urls.py (修正後的版本)

from django.contrib import admin
from django.urls import path, include
from django.conf import settings 
# 匯入 settings 是為了讀取 DEBUG 狀態
from django.conf.urls.static import static 
# 匯入 static 是為了在本地開發時能正確處理 MEDIA 檔案

urlpatterns = [
    # 1. Django 管理後台 (標準設定)
    path('admin/', admin.site.urls),
    
    # 2. (方案一 核心) 
    #    這會告訴 Django，所有開頭是 'api/' 的網址請求，
    #    都去 'detector/api/urls.py' 檔案裡找對應的 'view'。
    path('api/', include('detector.api.urls')),

    # 3. (重要) 
    #    確保您「沒有」 'path('', include('detector.urls'))' 這一行，
    #    因為 'detector/urls.py' 是空的，會導致錯誤。
]

# --- 本地開發 (DEBUG=1) 模式下的重要設定 ---
# 
# 這段程式碼非常關鍵：
# 它允許您的本地開發伺服器 (runserver)
# 在 DEBUG=1 模式下，能正確提供您上傳的媒體檔案 (media files)。
#
# 這在您的 settings.py 中有 'else' 邏輯：
# 如果您在本地 .env "沒有" 設定 AWS_STORAGE_BUCKET_NAME，
# MEDIA_URL 會是 '/media/'，MEDIA_ROOT 會指向本地資料夾。
# 這行程式碼就是用來處理這種本地測試情境的。
#
# 這在生產環境 (DEBUG=0) 中會被自動忽略。
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)