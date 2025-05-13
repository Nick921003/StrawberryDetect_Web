import base64
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from ..services import process_image_bytes
from .serializers import ProcessImageSerializer

class DetectionViewSet(viewsets.ViewSet):
    """
    使用 ViewSet，把多個 related actions 都放一起。
    """

    @action(detail=False, methods=['post'])
    def process(self, request):
        """
        POST /api/process/process/
        body: { "image_base64": "…" }
        """
        # 1. 驗證輸入
        serializer = ProcessImageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 2. 解碼 Base64
        img_b64 = serializer.validated_data['image_base64']
        try:
            image_bytes = base64.b64decode(img_b64)
        except Exception:
            return Response(
                {"error": "無效的 Base64 圖片字串"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. 呼叫 service 執行推論、存檔、存 DB
        record = process_image_bytes(image_bytes, file_ext='.jpg')

        # 4. 回傳結果
        return Response({
            'record_id': str(record.id),
            'orig_url': record.original_image.url,
            'annotated_url': record.annotated_image.url,
            'results': record.results_data,
        }, status=status.HTTP_201_CREATED)
