# detector/api/serializers.py
from rest_framework import serializers

class S3FolderProcessRequestSerializer(serializers.Serializer):
    """
    驗證 S3 資料夾處理請求的欄位。
    """
    s3_bucket_name = serializers.CharField(
        max_length=255,
        required=True,
        help_text="AWS S3 儲存桶的名稱。"
    )
    s3_folder_prefix = serializers.CharField(
        max_length=1024,
        required=True,
        help_text="S3 儲存桶中圖片所在資料夾的路徑/前綴 (例如 'uploads/batch1/')。"
    )
    # 你可以根據需要加入其他欄位，例如 batch_id, rover_id 等
    # batch_id = serializers.CharField(max_length=100, required=False)

    def validate_s3_folder_prefix(self, value):
        """
        可選的驗證：確保 prefix 看起來像一個資料夾路徑。
        """
        # 例如，可以檢查它是否不包含非法字元，或者是否以 '/' 結尾 (雖然 task 中會處理)
        if value and not value.endswith('/'):
            # 可以在此處附加 '/' 或在 task 中處理
            # return value + '/'
            pass # 我們的 task 會自動處理結尾的 '/'
        return value