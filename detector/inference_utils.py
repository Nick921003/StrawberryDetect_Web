# detector/inference_utils.py
import cv2
import numpy as np
import os
import logging # <-- 新增 logging
from .apps import yolo_model

# 設定此模組的 logger
inference_logger = logging.getLogger(__name__) #或者 'detector.inference_utils'

class ImageDecodeError(Exception):
    """自訂異常，用於表示圖片解碼失敗。"""
    pass

def run_yolo_inference_on_image_data(image_bytes, confidence_threshold=0.5):
    """
    使用預先載入的 YOLO 模型對記憶體中的圖片數據執行推論。
    """
    if yolo_model is None:
        inference_logger.error("YOLO 模型尚未成功載入 (inference_utils)。")
        raise RuntimeError("YOLO model is not loaded.")

    annotated_image_array = None
    text_results = []

    if not image_bytes:
        inference_logger.warning("傳入的 image_bytes 為空 (inference_utils)。")
        raise ImageDecodeError("Input image_bytes is empty.")

    inference_logger.debug(f"Attempting to decode image_bytes of length: {len(image_bytes)}")

    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            inference_logger.error(f"無法從位元組數據解碼圖片 (cv2.imdecode returned None). Bytes length: {len(image_bytes)} (inference_utils).")
            # 拋出一個更特定的錯誤，而不是僅僅回傳 None, []
            raise ImageDecodeError(f"cv2.imdecode failed for image_bytes of length {len(image_bytes)}.")
        
        inference_logger.info(f"成功從位元組數據解碼圖片進行推論 (尺寸: {img.shape})")

        results = yolo_model(img, conf=confidence_threshold)

        if results and results[0] and results[0].boxes is not None:
            if len(results[0].boxes) > 0:
                inference_logger.info(f"偵測到 {len(results[0].boxes)} 個物件 (信心度 > {confidence_threshold})")
                annotated_image_array = results[0].plot() 
                
                names = yolo_model.names
                for box in results[0].boxes:
                    class_id = int(box.cls.item())
                    conf = box.conf.item()
                    class_name = names.get(class_id, f"未知類別 {class_id}")
                    text_results.append({
                        'class': class_name,
                        'confidence_str': f"{conf:.2f}",
                        'confidence_float': conf
                    })
            else:
                inference_logger.info(f"在此圖片上未偵測到信心度高於 {confidence_threshold} 的物件。")
        else:
            inference_logger.warning("模型推論結果格式異常或為空。")

    except ImageDecodeError: # 直接重新拋出我們自訂的解碼錯誤
        raise
    except Exception as e:
        inference_logger.error(f"執行 YOLO 推論或處理結果時發生錯誤: {e}", exc_info=True)
        # 對於其他未知錯誤，也可以考慮將其包裝或直接拋出
        # 這裡我們讓它作為一個通用錯誤被上層捕獲
        raise RuntimeError(f"YOLO inference processing error: {e}")

    return annotated_image_array, text_results
