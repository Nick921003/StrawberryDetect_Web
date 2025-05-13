from rest_framework import serializers

class ProcessImageSerializer(serializers.Serializer):
    """
    驗證外部傳來的欄位：
      - image_base64: 圖片的 Base64 編碼字串
    """
    image_base64 = serializers.CharField(
        help_text="將圖片轉成 Base64, 並以字串形式傳遞"
    )
