# detector/tests.py

import base64
from django.test import TestCase
from rest_framework.test import APIClient
import os

class DetectionAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.api_url = '/api/process/process/'

    def test_process_image_api(self):
        # 1. 讀取本地圖片
        image_path = os.path.join(os.path.dirname(__file__), 'test.png')
        with open(image_path, 'rb') as img_file:
            image_bytes = img_file.read()
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')

        # 2. 組成請求 payload
        payload = {
            "image_base64": image_b64
        }

        # 3. 發送 POST 請求
        response = self.client.post(self.api_url, data=payload, format='json')

        # 4. 驗證回傳狀態與資料
        self.assertEqual(response.status_code, 201)
        self.assertIn("record_id", response.data)
        self.assertIn("results", response.data)
        print("✅ 測試成功：辨識結果如下：", response.data)
