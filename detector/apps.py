from django.apps import AppConfig
from ultralytics import YOLO
import os
from django.conf import settings # 匯入 Django settings 以便獲取 BASE_DIR

# 定義一個全局變數來儲存載入後的模型實例
yolo_model = None

class DetectorConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'detector'
    
    def ready(self):
        """
        Django App 準備就緒時會執行的函數。
        我們在這裡載入模型。
        """
        global yolo_model # 宣告我們要修改的是全局變數

        # 這個檢查是為了避免在開發伺服器自動重載時重複執行載入程式碼
        # if yolo_model is None and not os.environ.get('RUN_MAIN', False):
        if yolo_model is None:
            # --- 重要：設定你的模型檔案路徑 ---
            # 務必將下面的路徑換成你 'best.pt' 檔案的 **實際存放路徑**
            # 建議將模型檔案放在專案內的某個資料夾（例如根目錄下的 'ml_models' 資料夾）
            # 或者提供絕對路徑。

            # 範例 1: 模型放在專案根目錄下的 'ml_models' 資料夾中
            model_path = os.path.join(settings.BASE_DIR, 'yolo', 'best.pt')

            # 範例 2: 使用絕對路徑 (請根據你的實際情況修改)
            # model_path = "C:/Users/YourUser/path/to/runs/segment/trainXX/weights/best.pt"
            # model_path = "/home/youruser/projects/runs/segment/trainXX/weights/best.pt"

            # 範例 3: 如果模型就在專案根目錄下 (較不建議，容易混亂)
            # model_path = os.path.join(settings.BASE_DIR, 'best.pt')

            # --- 模型載入 ---
            print(f"------------------------------------")
            print(f"準備載入 YOLO 模型於: {model_path}")

            if os.path.exists(model_path):
                try:
                    # 載入 YOLO 模型
                    yolo_model = YOLO(model_path)
                    print(f">>> YOLO 模型載入成功! ({model_path})")
                except Exception as e:
                    print(f">>> 載入 YOLO 模型時發生嚴重錯誤: {e}")
                    yolo_model = None # 載入失敗，設為 None
            else:
                print(f">>> 錯誤：模型檔案未找到於 {model_path}")
                print(f">>> 請確認 'detector/apps.py' 中的 'model_path' 設定是否正確。")
                yolo_model = None # 檔案不存在，設為 None

            print(f"------------------------------------")

        # else: # 可選：如果 yolo_model 不是 None，表示已載入或在另一個進程載入
        #     print("YOLO model already loaded or loading in another process.")