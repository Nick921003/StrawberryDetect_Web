# detector/admin.py
from django.contrib import admin
from .models import DetectionRecord, BatchDetectionJob # 確保匯入模型

@admin.register(DetectionRecord)
class DetectionRecordAdmin(admin.ModelAdmin):
    list_display = ('id', 'batch_job', 'uploaded_at', 'severity_score', 'original_image_preview', 'annotated_image_preview') # 您想在列表頁看到的欄位
    list_filter = ('batch_job', 'uploaded_at', 'severity_score') # 可以用來篩選的欄位
    search_fields = ('id', 'batch_job__id', 'results_data') # 可以搜尋的欄位
    readonly_fields = ('uploaded_at', 'id', 'original_image_preview', 'annotated_image_preview') # 通常這些欄位是唯讀的
    # date_hierarchy = 'uploaded_at' # 增加日期層級導覽

    # 為了在 Admin 中預覽圖片 (可選，但很方便)
    def original_image_preview(self, obj):
        from django.utils.html import format_html
        if obj.original_image:
            return format_html('<a href="{0}" target="_blank"><img src="{0}" width="100" /></a>', obj.original_image.url)
        return "(No image)"
    original_image_preview.short_description = '原始圖片預覽'

    def annotated_image_preview(self, obj):
        from django.utils.html import format_html
        if obj.annotated_image:
            return format_html('<a href="{0}" target="_blank"><img src="{0}" width="100" /></a>', obj.annotated_image.url)
        return "(No image)"
    annotated_image_preview.short_description = '標註圖片預覽'

@admin.register(BatchDetectionJob)
class BatchDetectionJobAdmin(admin.ModelAdmin):
    list_display = ('id', 's3_folder_prefix', 'status', 'total_images_found', 'images_processed_successfully', 'created_at', 'updated_at')
    list_filter = ('status', 'created_at', 's3_bucket_name')
    search_fields = ('id', 's3_folder_prefix', 'celery_task_id')
    readonly_fields = ('id', 'celery_task_id', 'created_at', 'updated_at')
    # date_hierarchy = 'created_at'
    