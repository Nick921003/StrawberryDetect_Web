from django.db import models
import uuid # 用於產生不會重複的 ID


class DetectionRecord(models.Model):
    """
    用於儲存每一次草莓病蟲害辨識紀錄的模型。
    """
    # 欄位定義:

    # 主鍵 (Primary Key): 使用 UUID 確保每個紀錄有獨一無二且不易猜測的 ID
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # 原始圖片:
    # ImageField 會處理檔案上傳到 MEDIA_ROOT 下的 'uploads/年/月/日/' 資料夾
    # 資料庫欄位只會儲存相對路徑字串，例如 'uploads/2025/04/28/xxxx.jpg'
    # upload_to 可以指定子資料夾和檔名格式（這裡用年月日子資料夾）
    original_image = models.ImageField(
        upload_to='uploads/%Y/%m/%d/',
        verbose_name="原始圖片" # 在 Admin 後台顯示的名稱
    )

    # 標註後的結果圖片:
    # 同樣使用 ImageField 處理，儲存到 'results/年/月/日/'
    # null=True, blank=True 表示允許這個欄位是空的（因為可能沒有偵測到任何物件）
    annotated_image = models.ImageField(
        upload_to='results/%Y/%m/%d/',
        null=True, blank=True,
        verbose_name="標註結果圖"
    )

    # 辨識結果數據 (文字列表):
    # 使用 JSONField 可以直接將 Python 的列表或字典存入資料庫 (需要 PostgreSQL)
    # null=True, blank=True 允許為空
    results_data = models.JSONField(
        null=True, blank=True,
        verbose_name="辨識結果數據"
    )

    # 上傳時間:
    # auto_now_add=True 表示在記錄被建立時，自動將欄位設為當下時間
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="上傳時間"
    )

    # 讓物件在後台或 print 時顯示更有意義的名稱
    def __str__(self):
        return f"辨識紀錄 ({self.uploaded_at.strftime('%Y-%m-%d %H:%M:%S')})"

    # 設定在 Admin 後台顯示時的排序方式（可選）
    class Meta:
        ordering = ['-uploaded_at'] # 依照上傳時間倒序排列 (最新的在前面)
        verbose_name = "辨識紀錄"
        verbose_name_plural = "辨識紀錄"

    # (重要) 覆寫 delete 方法，以便在刪除資料庫記錄時，也刪除對應的圖片檔案
    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
