### 1. IAM 許可 (IAM Policy)

IAM 政策用於授予您的應用程式（或其運行的 IAM 角色/使用者）存取 AWS 資源的權限。

* **範例檔案**：`docs/aws/iam_policy_example.json`
* **用途**：此政策允許應用程式在指定的 S3 儲存貯體中上傳、讀取、刪除物件，並有條件地列出特定目錄下的物件。

```json
// docs/aws/iam_policy_example.json
{
    "Version": "2012-10-17", // 指定政策語言的版本，通常固定為 "2012-10-17"
    "Statement": [ // 包含一個或多個陳述 (statement)，每個陳述定義一組權限
        {
            // 陳述 1: 允許對 S3 物件進行核心操作
            "Effect": "Allow", // 效果："Allow" (允許) 或 "Deny" (拒絕)
            "Action": [ // 允許執行的 AWS 操作 (API Call)
                "s3:PutObject",    // 允許上傳新物件或覆寫現有物件 (例如，儲存使用者上傳的圖片)
                "s3:GetObject",    // 允許讀取或下載物件 (例如，顯示已儲存的圖片給使用者)
                "s3:DeleteObject"  // 允許刪除物件 (例如，當辨識紀錄被刪除時，也刪除相關的 S3 圖片)
            ],
            "Resource": "arn:aws:s3:::your-s3-bucket-name/*" // 此權限適用的資源
                                                            // "arn:aws:s3:::your-s3-bucket-name" 是您的 S3 儲存貯體 ARN
                                                            // "/*" 表示此權限適用於該儲存貯體內的「所有物件」
        },
        {
            // 陳述 2: 允許有條件地列出儲存貯體內容
            "Sid": "AllowAppToListBucketContentsForSpecificPrefixes", // 陳述 ID (可選，用於標識此陳述)
            "Effect": "Allow",
            "Action": "s3:ListBucket", // 允許列出儲存貯體中的物件 (例如，某些 Django Storages 操作可能需要)
            "Resource": "arn:aws:s3:::your-s3-bucket-name", // 此權限作用於「儲存貯體本身」，而非物件
            "Condition": { // 附加條件，只有滿足條件時此陳述才生效
                "StringLike": { // 條件類型：字串相似匹配
                    "s3:prefix": [ // 請求中指定的物件前綴 (可以理解為資料夾路徑)
                        "media/*", // 允許列出 "media/" 目錄下的物件
                        "static/*" // 允許列出 "static/" 目錄下的物件 (如果您的靜態檔案也由 S3 托管)
                                   // 這樣限制可以避免應用程式意外列出整個儲存貯體的內容
                    ]
                }
            }
        }
    ]
}
```
### 2. S3儲存貯體政策 (Bucket Policy)

S3 儲存貯體政策直接附加到 S3 儲存貯體，用於控制對該儲存貯體及其物件的存取，通常用於設定更廣泛的存取規則或強制安全標準。

* **用途**：此政策強制所有上傳到儲存貯體的物件都必須使用 AES256 伺服器端加密，並且所有對 S3 的請求都必須透過HTTPS。

```json
// docs/aws/s3_bucket_policy_example.json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            // 陳述 1: 拒絕未使用 AES256 加密標頭或使用錯誤加密標頭的上傳請求
            // 目標：確保所有上傳物件都明確使用 AES256 伺服器端加密
            "Sid": "DenyIncorrectEncryptionHeader",
            "Effect": "Deny", // 效果：拒絕
            "Principal": "*", // 主體："*" 表示適用於所有請求者 (匿名或已驗證)
            "Action": "s3:PutObject", // 操作：上傳物件
            "Resource": "arn:aws:s3:::your-s3-bucket-name/*", // 適用於儲存貯體內的所有物件
            "Condition": { // 條件
                "StringNotEquals": { // 條件類型：字串不等於
                                     // "s3:x-amz-server-side-encryption" 是上傳請求中指定的伺服器端加密方法
                    "s3:x-amz-server-side-encryption": "AES256" // 如果加密標頭存在但「不是」AES256，則拒絕
                                                                // 這與 Django settings.py 中 AWS_S3_OBJECT_PARAMETERS 的設定相輔相成
                }
            }
        },
        {
            // 陳述 2: 拒絕沒有提供加密標頭的上傳請求
            // 目標：確保上傳時必須指定加密方式，防止未加密上傳
            "Sid": "DenyUnEncryptedObjectUploads",
            "Effect": "Deny",
            "Principal": "*",
            "Action": "s3:PutObject",
            "Resource": "arn:aws:s3:::your-s3-bucket-name/*",
            "Condition": {
                "Null": { // 條件類型：檢查標頭是否存在 (Null 為 true 表示標頭不存在)
                    "s3:x-amz-server-side-encryption": "true" // 如果 "s3:x-amz-server-side-encryption" 標頭「不存在」(為 null)，則拒絕
                }
            }
        },
        {
            // 陳述 3: 強制所有 S3 存取都必須透過 SSL/TLS (HTTPS)
            // 目標：保護傳輸中的資料安全
            "Sid": "ForceSSLOnlyAccess",
            "Effect": "Deny",
            "Principal": "*",
            "Action": "s3:*", // 適用於所有 S3 操作 (GetObject, PutObject, ListBucket 等)
            "Resource": [ // 適用於儲存貯體本身及其所有物件
                "arn:aws:s3:::your-s3-bucket-name/*", // 所有物件
                "arn:aws:s3:::your-s3-bucket-name"  // 儲存貯體本身
            ],
            "Condition": {
                "Bool": { // 條件類型：布林值比較
                          // "aws:SecureTransport" 是一個 AWS 全局條件鍵，"true" 表示請求是透過 HTTPS
                    "aws:SecureTransport": "false" // 如果請求「不是」透過 HTTPS (即 aws:SecureTransport 為 false)，則拒絕
                }
            }
        }
    ]
}
```
### 3. S3 CORS (跨來源資源共享) 設定

CORS 設定允許在一個網域執行的 Web 應用程式（例如您的 Django 網站）存取另一個網域（例如 S3）上的資源。

* **用途** : 允許您的 Django 應用程式前端（通常是瀏覽器）直接從 S3 獲取圖片等資源來顯示。

```JSON
// docs/aws/s3_cors_example.json
[ // CORS 組態是一個規則列表，可以有多個規則物件
    {
        "AllowedHeaders": [ // 允許在實際跨來源請求中使用的 HTTP 標頭
                            // 瀏覽器在發送實際請求前，可能會透過預檢請求 (OPTIONS) 詢問伺服器是否接受這些標頭
            "Authorization",   // 例如，如果請求需要授權
            "Content-Type",    // 例如，用於 POST 或 PUT 請求指定內容類型
            "X-Amz-Date",      // AWS 請求簽名相關標頭
            "X-Amz-Security-Token", // AWS 臨時憑證相關標頭
            "X-Amz-User-Agent", // AWS SDK 使用者代理標頭
            "*"                // "*" 表示允許所有標頭，開發時方便，生產環境建議列出具體需要的標頭
        ],
        "AllowedMethods": [ // 允許的 HTTP 方法
            "GET",  // 主要用於從 S3 獲取物件 (例如，顯示圖片)
            "HEAD"  // 用於獲取物件的元數據 (例如，檔案大小、類型)，而不下載整個物件
                    // 注意：此範例不包含 PUT/POST，表示不允許直接從瀏覽器上傳。
                    // 檔案上傳應由 Django 後端處理，更安全。
        ],
        "AllowedOrigins": [ // 允許發起跨來源請求的來源 (網域)
                            // 必須包含協議 (http/https)、主機名和端口 (如果非標準端口)
            "http://localhost:8000",         // 本地 Django 開發伺服器
            "[http://127.0.0.1:8000](http://127.0.0.1:8000)",       // 本地 Django 開發伺服器 (另一種訪問方式)
            "[https://your-production-domain.com](https://your-production-domain.com)" // 【請替換】您應用程式部署後的實際生產環境域名
                                                 // 例如 "[https://www.example.com](https://www.example.com)"
        ],
        "ExposeHeaders": [ // 允許瀏覽器的 JavaScript 程式碼存取的來自伺服器端的回應標頭
                           // 預設情況下，瀏覽器只能存取一小部分「安全」的回應標頭
            "ETag",               // 物件的實體標籤，可用於快取驗證
            "x-amz-version-id"    // 如果啟用了物件版本控制，這是物件的版本 ID
        ],
        "MaxAgeSeconds": 3000 // 預檢請求 (OPTIONS request) 結果可以被瀏覽器快取的時間 (秒)
                              // 3000 秒 = 50 分鐘。在此期間，瀏覽器對相同類型的請求無需重複發送預檢請求。
    }
]
```
