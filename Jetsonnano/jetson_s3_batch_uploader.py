# jetson_s3_batch_uploader.py
# ---------------------------------------------
# Jetson Nano 圖片批次上傳腳本
# 將指定本地資料夾內所有圖片上傳至 AWS S3 指定路徑
# ---------------------------------------------

import os
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
import requests  

# =====================
# 設定區
# =====================
# AWS S3 相關設定
S3_BUCKET_NAME = 'strawberrydetect2'  # S3 儲存桶名稱
S3_BASE_TARGET_PATH = 'media/test/'   # S3 儲存桶中的基礎路徑 (如 'test/' 或 'rover_uploads/')
# Jetson Nano 本地圖片資料夾設定
LOCAL_BATCHES_PARENT_DIR = 'local_image_batches/'  # 批次資料夾上層目錄
CURRENT_BATCH_FOLDER_NAME = 'batch02'              # 要上傳的批次資料夾名稱

# =====================
# S3 Client 初始化
# =====================
def get_s3_client():
    """
    初始化並返回一個 S3 client。
    若憑證有誤會給出明確提示。
    """
    try:
        # 直接使用預設憑證鏈 (IAM role > env vars > shared credentials)
        s3_client = boto3.client('s3')
        return s3_client
    except NoCredentialsError:
        print("錯誤：找不到 AWS 憑證。請設定環境變數、AWS credentials 檔案或 IAM 角色。")
        return None
    except PartialCredentialsError:
        print("錯誤：AWS 憑證不完整。請檢查 access key 和 secret key。")
        return None
    except Exception as e:
        print(f"初始化 S3 client 時發生錯誤: {e}")
        return None

# =====================
# 上傳主功能
# =====================
def upload_folder_to_s3(s3_client, local_folder_path, bucket_name, s3_target_folder):
    """
    將本地資料夾中的所有圖片檔案遞迴上傳到 S3 指定資料夾。

    參數:
        s3_client: boto3 S3 client 物件
        local_folder_path (str): 本地資料夾路徑
        bucket_name (str): S3 儲存桶名稱
        s3_target_folder (str): S3 目標資料夾路徑 (需以 '/' 結尾)
    返回:
        bool: 全部成功回傳 True，否則 False
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
            if not filename.lower().endswith((
                '.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff')):
                continue
            # S3 上的相對路徑
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
    return all_successful

# =====================
# 主程式流程
# =====================
def main():
    """
    主函式：上傳指定本地批次資料夾到 S3。
    """
    print("\n=== Jetson Nano S3 圖片批次上傳腳本啟動 ===\n")

    local_current_batch_path = os.path.join(LOCAL_BATCHES_PARENT_DIR, CURRENT_BATCH_FOLDER_NAME)
    if not os.path.isdir(local_current_batch_path):
        print(f"錯誤：指定的本地批次資料夾 '{local_current_batch_path}' 不存在。\n請檢查 LOCAL_BATCHES_PARENT_DIR 和 CURRENT_BATCH_FOLDER_NAME 設定。\n")
        return

    s3_client = get_s3_client()
    if not s3_client:
        print("無法初始化 S3 client，腳本終止。\n")
        return

    # 組合 S3 目標資料夾路徑 (如 'media/test/batch02/')
    s3_full_target_folder = S3_BASE_TARGET_PATH.rstrip('/') + '/' + CURRENT_BATCH_FOLDER_NAME.strip('/') + '/'

    # 執行上傳
    upload_successful = upload_folder_to_s3(
        s3_client, local_current_batch_path, S3_BUCKET_NAME, s3_full_target_folder)

    if upload_successful:
        print(f"資料夾 '{CURRENT_BATCH_FOLDER_NAME}' 成功上傳到 S3。\n")
        api_url = 'http://localhost:8000/api/process/process_s3_folder/'
        payload = {
            's3_bucket_name': S3_BUCKET_NAME,
            's3_folder_prefix': s3_full_target_folder
        }
        try:
            print(f"通知 API: {api_url}，資料: {payload}")
            response = requests.post(api_url, json=payload, timeout=10)
            print(f"API 狀態碼: {response.status_code}")
            print(f"API 回應內容: {response.text}")
            if response.status_code == 202:
                print(f"✅ API 通知成功")
            else:
                print(f"⚠️  API 回應異常 (status {response.status_code})")
        except Exception as e:
            print(f"⚠️  發送 API 請求時發生錯誤: {e}")
    else:
        print(f"S3 上傳失敗，請檢查 S3 上傳日誌。\n")
    print("=== 腳本執行完畢 ===\n")


# =====================
# 執行入口
# =====================
if __name__ == '__main__':
    main()
