# test_jetson_prod.py
# ---------------------------------------------
# 【生產環境測試腳本】
# 模擬 Jetson Nano，將本地圖片上傳至 S3
# 並呼叫「已部署的 ALB API」來觸發 Celery 批次處理
# ---------------------------------------------

import os
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
import requests
import sys  # 用於讀取環境變數

# =====================
# 設定區 (已為生產環境修改)
# =====================

# --- 1. AWS S3 相關設定 ---
# 【【修改點】】 根據您 EC2 日誌，使用您生產環境的 S3 儲存桶
S3_BUCKET_NAME = 'strawberry5' 
# 【【修改點】】 確保 S3 區域與您的儲存桶一致 (您日誌中顯示 us-east-1)
S3_REGION = 'us-east-1' 
# S3 儲存桶中的上傳基礎路徑 (位於 'media/' 之下)
S3_BASE_TARGET_PATH = 'media/test_jetson/' 

# --- 2. 本地圖片資料夾設定 ---
# 確保這個路徑相對於您執行此腳本的位置是正確的
LOCAL_BATCHES_PARENT_DIR = 'local_image_batches/' #
CURRENT_BATCH_FOLDER_NAME = 'batch02' #

# --- 3. API 端點設定 ---
# 【【【最關鍵的修改】】】
# 指向您已部署的 ALB API (包含我們修正後的所有路徑)
BACKEND_API_URL = 'https://api.strawberrydetect.com/api/process/process_s3_folder/'

# =====================
# S3 Client 初始化
# =====================
def get_s3_client():
    """
    初始化並返回一個 S3 client。
    """
    try:
        # 從環境變數讀取 AWS 憑證
        aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
        aws_secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')

        if not aws_access_key_id or not aws_secret_access_key:
            print("錯誤：環境變數 AWS_ACCESS_KEY_ID 或 AWS_SECRET_ACCESS_KEY 未設定。")
            print("請在執行此腳本前，先在您的終端機設定這些變數。")
            return None

        s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=S3_REGION
        )
        return s3_client
    except NoCredentialsError:
        print("錯誤：找不到 AWS 憑證。")
        return None
    except PartialCredentialsError:
        print("錯誤：AWS 憑證不完整。")
        return None
    except Exception as e:
        print(f"初始化 S3 client 時發生錯誤: {e}")
        return None

# =====================
# 上傳主功能 (與您原版一致)
# =====================
def upload_folder_to_s3(s3_client, local_folder_path, bucket_name, s3_target_folder):
    """
    將本地資料夾中的所有圖片檔案遞迴上傳到 S3 指定資料夾。
    """
    if not os.path.isdir(local_folder_path):
        print(f"錯誤：本地資料夾 '{local_folder_path}' 不存在。")
        return False

    if not s3_target_folder.endswith('/'):
        s3_target_folder += '/'

    print(f"\n準備將本地資料夾 '{local_folder_path}' 上傳到 S3 路徑 's3://{bucket_name}/{s3_target_folder}'...")

    all_successful = True
    for root, dirs, files in os.walk(local_folder_path):
        for filename in files:
            local_file_path = os.path.join(root, filename)
            # 僅上傳圖片檔案
            if not filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff')):
                continue
            
            relative_path = os.path.relpath(local_file_path, local_folder_path)
            s3_key = os.path.join(s3_target_folder, relative_path).replace("\\", "/")
            try:
                print(f"  正在上傳 {local_file_path} → s3://{bucket_name}/{s3_key} ...", end='')
                s3_client.upload_file(local_file_path, bucket_name, s3_key)
                print(" 成功")
            except ClientError as e:
                print(f"\n  錯誤：上傳檔案 {filename} 失敗: {e}")
                all_successful = False
            except FileNotFoundError:
                print(f"\n  錯誤：本地檔案 {local_file_path} 未找到。")
                all_successful = False
            except Exception as e:
                print(f"\n  上傳檔案 {filename} 發生未知錯誤: {e}")
                all_successful = False

    if all_successful:
        print(f"\n✅ 資料夾 '{local_folder_path}' 中所有圖片已成功上傳至 S3。\n")
    else:
        print(f"\n⚠️  部分圖片上傳失敗，請檢查上傳日誌。\n")
    return all_successful, s3_target_folder

# =====================
# 主程式流程 (已修改 API 呼叫)
# =====================
def main():
    """
    主函式：上傳批次資料夾到 S3，並呼叫 API 觸發處理。
    """
    print("\n=== 生產環境 API 測試腳本啟動 ===\n")

    local_current_batch_path = os.path.join(LOCAL_BATCHES_PARENT_DIR, CURRENT_BATCH_FOLDER_NAME)
    if not os.path.isdir(local_current_batch_path):
        print(f"錯誤：指定的本地批次資料夾 '{local_current_batch_path}' 不存在。")
        print("請確認您是從 'StrawberryDetect_Web' 專案根目錄執行此腳本。\n")
        return

    s3_client = get_s3_client()
    if not s3_client:
        print("無法初始化 S3 client，腳本終止。\n")
        return

    s3_full_target_folder = S3_BASE_TARGET_PATH.rstrip('/') + '/' + CURRENT_BATCH_FOLDER_NAME.strip('/') + '/'

    upload_successful, s3_path_used = upload_folder_to_s3(
        s3_client, local_current_batch_path, S3_BUCKET_NAME, s3_full_target_folder)

    if upload_successful:
        print(f"資料夾 '{CURRENT_BATCH_FOLDER_NAME}' 成功上傳到 S3。")
        
        # 【【【修改點】】】 呼叫生產環境的 API
        api_url = BACKEND_API_URL 
        
        # 【【交叉比對】】 
        # 您的 API (serializers.py & views.py)
        # 期待的 payload 是 's3_bucket_name' 和 's3_folder_prefix'。
        payload = {
            's3_bucket_name': S3_BUCKET_NAME,
            's3_folder_prefix': s3_path_used 
        }
        
        try:
            print(f"\n準備呼叫後端 API...")
            print(f"  端點: {api_url}")
            print(f"  Payload: {payload}")
            
            response = requests.post(api_url, json=payload, timeout=30) # 30 秒超時
            
            print(f"\nAPI 呼叫完成：")
            print(f"  狀態碼: {response.status_code}")
            print(f"  回應內容: {response.text}")
            
            # 您的 API (views.py) 在成功時會回傳 202 (Accepted)
            if response.status_code == 202: 
                print(f"\n✅ API 通知成功！後端 Celery 任務已觸發。")
                print("請立刻檢查您 EC2 上的 'celery_worker' 日誌。")
            else:
                print(f"\n⚠️  API 回應異常 (狀態碼 {response.status_code})。後端可能未觸發。")
                
        except requests.exceptions.RequestException as e:
            print(f"\n⚠️  發送 API 請求時發生錯誤: {e}")
            
    else:
        print(f"S3 上傳失敗，請檢查 S3 上傳日誌。\n")
        
    print("\n=== 腳本執行完畢 ===\n")


# =====================
# 執行入口
# =====================
if __name__ == '__main__':
    main()