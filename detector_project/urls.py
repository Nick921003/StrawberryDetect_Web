"""
URL configuration for detector_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.urls import path, include
from django.conf import settings      # <-- 新增匯入 settings
from django.conf.urls.static import static  # <-- 新增匯入 static


urlpatterns = [
    path('admin/', admin.site.urls),
    # 當使用者訪問的網址是以 'detector/' 開頭時，
    # 就把網址後面剩下的部分交給 'detector.urls' (也就是 detector/urls.py) 去處理
    path('detector/', include('detector.urls')),
]
# *** 新增以下區塊，用於在開發模式下提供媒體檔案 ***
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
