# detector/inference_utils.py
import cv2
import numpy as np
import os
from .apps import yolo_model

# *** 修改函式簽名，改回接收 image_path ***
def run_yolo_inference(image_path, confidence_threshold=0.5):
    """
    使用預先載入的 YOLO 模型對指定路徑的圖片執行推論。

    Args:
        image_path (str): 輸入圖片在伺服器上的檔案路徑。 # <-- 改回文件說明
        confidence_threshold (float): 信心閾值。

    Returns:
        tuple: (annotated_image_array, text_results)
            - annotated_image_array (np.ndarray | None): 標註圖陣列或 None。
            - text_results (list[dict]): 結果列表或空列表。
    """
    if yolo_model is None:
        print("錯誤：YOLO 模型尚未成功載入。")
        raise RuntimeError("YOLO model is not loaded.")

    # 讀取圖片
    try:
        img = cv2.imread(image_path)
        if img is None:
            print(f"錯誤：無法從路徑讀取圖片： {image_path}")
            return None, []
        print(f"成功讀取圖片進行推論: {image_path} (尺寸: {img.shape})") # <-- 修改 print 訊息
    except Exception as e:
        print(f"讀取圖片時發生錯誤 ({image_path}): {e}")
        return None, []
    # *** 結束加入 ***

    annotated_image_array = None
    text_results = []
    try:
        # *** 使用內部讀取的 img 進行推論 ***
        results = yolo_model(img, conf=confidence_threshold) # <-- 使用 img 而不是 image_array

        if results and results[0] and results[0].boxes is not None:
            if len(results[0].boxes) > 0:
                print(f"偵測到 {len(results[0].boxes)} 個物件 (信心度 > {confidence_threshold})")
                annotated_image_array = results[0].plot()
                names = yolo_model.names
                for box in results[0].boxes:
                    # ... (提取 text_results 的邏輯不變) ...
                    class_id = int(box.cls.item())
                    conf = box.conf.item()
                    class_name = names.get(class_id, f"未知類別 {class_id}")
                    text_results.append({
                        'class': class_name,
                        'confidence_str': f"{conf:.2f}",
                        'confidence_float': conf
                    })
            else:
                print(f"在此圖片上未偵測到信心度高於 {confidence_threshold} 的物件。")
        else:
            print("模型推論結果格式異常或為空。")

    except Exception as e:
        print(f"執行 YOLO 推論或處理結果時發生錯誤: {e}")
        annotated_image_array = None
        text_results = []

    return annotated_image_array, text_results