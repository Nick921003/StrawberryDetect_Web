# detector/inference_utils.py

# --- ↓↓↓ 請從這裡開始完整複製 ↓↓↓ ---

import io
import cv2
import numpy as np
from PIL import Image
from django.conf import settings
from django.apps import apps
import logging

inference_logger = logging.getLogger(__name__)

class ImageDecodeError(Exception):
    """自定義異常，用於表示圖片解碼失敗。"""
    pass


def run_yolo_inference_on_image_data(image_bytes: bytes, confidence_threshold: float = 0.5) -> tuple:
    """
    對給定的圖片字節執行 YOLO 推論。

    Args:
        image_bytes: 圖片的二進位內容。
        confidence_threshold: 信心水準閾值。

    Returns:
        一個元組，包含：
        - annotated_image_array (np.ndarray): 帶有標註框的圖片陣列 (BGR 格式)，如果沒有偵測結果則為原始圖片陣列。
        - detections (list[dict]): 偵測結果的字典列表，每個字典包含 'class', 'confidence_float', 'confidence_str', 'box'。
    """
    try:
        pil_image = Image.open(io.BytesIO(image_bytes))
        if pil_image.mode != 'RGB':
            pil_image = pil_image.convert('RGB')
    except Exception as e:
        inference_logger.error(f"Pillow failed to decode image: {e}")
        raise ImageDecodeError(f"Failed to decode image: {e}")

    model = apps.get_app_config('detector').yolo_model
    if not model:
        inference_logger.critical("YOLO model is not loaded in the app config.")
        raise RuntimeError("YOLO model is not loaded.")

    try:
        results = model(pil_image, conf=confidence_threshold)
        result = results[0] if results else None

        rgb_image_array = np.array(pil_image)
        bgr_image_array = cv2.cvtColor(rgb_image_array, cv2.COLOR_RGB2BGR)

        if result is None or len(result.boxes) == 0:
            return bgr_image_array, []

        annotated_image_array = result.plot()

        detections = []
        boxes = result.boxes.xyxy.cpu().numpy()
        confs = result.boxes.conf.cpu().numpy()
        clss = result.boxes.cls.cpu().numpy()

        for i in range(len(boxes)):
            # --- 核心修正：產生前端樣板需要的 'confidence_float' 和 'confidence_str' ---
            conf_float = float(confs[i])
            detection_info = {
                'class': model.names[int(clss[i])],
                'confidence_float': conf_float,
                'confidence_str': f"{conf_float:.2f}", # 格式化為兩位小數的字串
                'box': [float(coord) for coord in boxes[i]]
            }
            detections.append(detection_info)

        return annotated_image_array, detections

    except Exception as e:
        inference_logger.error(f"An unexpected error occurred during YOLO inference: {e}", exc_info=True)
        raise RuntimeError(f"An error occurred during YOLO inference: {e}")
