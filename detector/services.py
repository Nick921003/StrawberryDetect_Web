## detector/services.py
import io
import uuid
import cv2
from PIL import Image
from django.core.files.base import ContentFile
from .models import DetectionRecord
from .inference_utils import run_yolo_inference_on_image_data


def process_image_bytes(image_bytes: bytes, file_ext: str = '.jpg', confidence: float = 0.5) -> DetectionRecord:
    """
    處理影像 bytes，包裝從 YOLO 推論到 S3 上傳與 DB 紀錄全流程。

    Args:
        image_bytes: 圖片的二進位內容
        file_ext: 檔案副檔名，如 '.jpg' 或 '.png'
        confidence: 推論信心水準

    Returns:
        新建立並已儲存的 DetectionRecord 實例
    """
    # 1) 執行 YOLO 推論
    annotated_array, text_results = run_yolo_inference_on_image_data(
        image_bytes, confidence_threshold=confidence
    )

    # 2) 建立並儲存 record
    record = DetectionRecord(results_data=text_results)
    unique_base = str(uuid.uuid4())

    # 儲存原始圖片到 S3
    orig_name = f"{unique_base}{file_ext}"
    # record.original_image.save(orig_name, ContentFile(image_bytes), save=False)

    # 若有標註結果，儲存標註圖到 S3
    if annotated_array is not None and annotated_array.size:
        # BGR -> RGB
        img_rgb = cv2.cvtColor(annotated_array, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb)
        buffer = io.BytesIO()
        format_name = 'JPEG' if file_ext.lower() in ['.jpg', '.jpeg'] else 'PNG'
        pil_img.save(buffer, format=format_name, quality=90)
        buffer.seek(0)
        anno_name = f"result_{unique_base}{file_ext}"
        record.annotated_image.save(anno_name, ContentFile(buffer.read()), save=False)

    # 最後儲存 metadata & 檔案上傳
    record.save()
    return record
