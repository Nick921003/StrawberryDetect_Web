# detector/inference_utils.py
import cv2
import numpy as np # 確保匯入 numpy
import os
from .apps import yolo_model # yolo_model 應該是從 apps.py 載入的

# 原有的函式可以保留，或者如果您不再需要基於路徑的推論，可以移除或註解掉
# def run_yolo_inference(image_path, confidence_threshold=0.5):
#     """
#     使用預先載入的 YOLO 模型對指定路徑的圖片執行推論。
#     ... (原函式內容) ...
#     """

def run_yolo_inference_on_image_data(image_bytes, confidence_threshold=0.5):
    """
    使用預先載入的 YOLO 模型對記憶體中的圖片數據執行推論。

    Args:
        image_bytes (bytes): 圖片的原始位元組數據。
        confidence_threshold (float): 信心閾值。

    Returns:
        tuple: (annotated_image_array, text_results)
            - annotated_image_array (np.ndarray | None): 標註後的 OpenCV 圖片陣列 (BGR格式) 或 None。
            - text_results (list[dict]): 結果列表或空列表。
    """
    if yolo_model is None:
        print("錯誤：YOLO 模型尚未成功載入 (inference_utils)。") # 或者使用 logging
        raise RuntimeError("YOLO model is not loaded.")

    annotated_image_array = None
    text_results = []

    try:
        # 1. 從位元組數據解碼圖片為 OpenCV 格式 (NumPy array)
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR) # BGR 格式

        if img is None:
            print("錯誤：無法從位元組數據解碼圖片 (inference_utils)。") # 或 logging
            return None, []
        
        print(f"成功從位元組數據解碼圖片進行推論 (尺寸: {img.shape})") # 或 logging

        # 2. 執行 YOLO 推論 (YOLOv11 模型可以直接接受 NumPy array)
        results = yolo_model(img, conf=confidence_threshold)

        if results and results[0] and results[0].boxes is not None:
            if len(results[0].boxes) > 0:
                print(f"偵測到 {len(results[0].boxes)} 個物件 (信心度 > {confidence_threshold})") # 或 logging
                # results[0].plot() 會回傳一個 NumPy array (BGR 格式)
                annotated_image_array = results[0].plot() 
                
                names = yolo_model.names # 獲取類別名稱
                for box in results[0].boxes:
                    class_id = int(box.cls.item())
                    conf = box.conf.item()
                    class_name = names.get(class_id, f"未知類別 {class_id}")
                    text_results.append({
                        'class': class_name,
                        'confidence_str': f"{conf:.2f}",
                        'confidence_float': conf  # 保留浮點數用於可能的後續處理
                    })
            else:
                print(f"在此圖片上未偵測到信心度高於 {confidence_threshold} 的物件。") # 或 logging
        else:
            print("模型推論結果格式異常或為空。") # 或 logging

    except Exception as e:
        print(f"執行 YOLO 推論或處理結果時發生錯誤 (inference_utils): {e}") # 或 logging
        # 可以考慮加入更詳細的錯誤記錄，例如 traceback.print_exc()
        annotated_image_array = None # 確保出錯時回傳 None
        text_results = []

    return annotated_image_array, text_results