# detector_project/settings.py
import os
from pathlib import Path
from dotenv import load_dotenv
from celery.schedules import crontab # 新增匯入 crontab

# 1. BASE_DIR 定義
BASE_DIR = Path(__file__).resolve().parent.parent

# 2. 載入 .env 檔案
dotenv_path = os.path.join(BASE_DIR, '.env')
if os.path.exists(dotenv_path):
    print(f"Loading .env file from: {dotenv_path}")
    load_dotenv(dotenv_path)
else:
    print(f"Warning: .env file not found at {dotenv_path}.")

# 3. 基礎安全性設定
SECRET_KEY = os.environ.get('SECRET_KEY', 'your-default-secret-key')
DEBUG = os.environ.get('DEBUG', '0') == '1'

# --- (優化) 主機與來源設定 (使用 .strip() 增強強健性) ---
allowed_hosts_str = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1')
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_str.split(',') if host.strip()]

csrf_trusted_origins_str = os.environ.get('CSRF_TRUSTED_ORIGINS', 'http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000,http://127.0.0.1:3000')
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in csrf_trusted_origins_str.split(',') if origin.strip()]

# --- (新增) CORS 設定 (允許您的前端訪問 API) ---
# 預設允許 .env 中的設定，或本地開發的前端 (port 3000)
cors_allowed_origins_str = os.environ.get('CORS_ALLOWED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000')
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in cors_allowed_origins_str.split(',') if origin.strip()]
# 如果您在開發中希望允許所有來源 (不建議在生產環境使用)
# if DEBUG:
#     CORS_ALLOW_ALL_ORIGINS = True




INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'detector',
    'storages',
    'django_cleanup.apps.CleanupConfig',
    'rest_framework',
    'django_celery_results',
    'django_celery_beat', 
    'corsheaders', # CORS App
]

# --- (優化) MIDDLEWARE 順序 ---
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware', # <-- (優化) 移至 CommonMiddleware 之前
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.messages',
                'django.contrib.messages.context_processors.messages'
            ],
        },
    },
]

ROOT_URLCONF = 'detector_project.urls'
WSGI_APPLICATION = 'detector_project.wsgi.application'

# 檢查是否在 Google Cloud Run 環境中運行
if 'K_SERVICE' in os.environ:
    # 在 Cloud Run 環境中：透過 Unix Socket 連接到 Cloud SQL
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'HOST': f"/cloudsql/{os.environ.get('CLOUDSQL_CONNECTION_NAME')}",
            'USER': os.environ.get('POSTGRES_USER'),
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD'),
            'NAME': os.environ.get('POSTGRES_DB'),
        }
    }
else:
    # 在本地或 Docker Compose 環境中：透過 TCP 連線
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('POSTGRES_DB'),
            'USER': os.environ.get('POSTGRES_USER'),
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD'),
            'HOST': os.environ.get('DATABASE_HOST'),
            'PORT': os.environ.get('DATABASE_PORT'),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Taipei'
USE_I18N = True
USE_TZ = True # Celery Beat 和 Django 的時區處理依賴此設定

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles' # collectstatic S3
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- 全域 AWS S3 設定 ---
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME')
AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME')
AWS_S3_ENDPOINT_URL = os.environ.get('AWS_S3_ENDPOINT_URL') # 主要用於 MinIO

AWS_S3_OBJECT_PARAMETERS = {
    'ServerSideEncryption': 'AES256',
}
AWS_DEFAULT_ACL = 'private' # 檔案預設為私有
AWS_S3_SECURE_URLS = True       # 使用 https
AWS_QUERYSTRING_AUTH = True     # 生成簽名 URL (因為 ACL 是 private)
AWS_QUERYSTRING_EXPIRE = 3600   # 簽名 URL 過期時間 (秒)
AWS_LOCATION = 'media'          # S3 儲存桶中媒體檔案的子目錄
AWS_S3_FILE_OVERWRITE = False   # 不覆蓋同名檔案

STORAGES = {
    'default': { # 媒體檔案 (MEDIA_ROOT) 使用 S3
        'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
        'OPTIONS': {
            'object_parameters': AWS_S3_OBJECT_PARAMETERS,
        },
    },
    'staticfiles': { # 靜態檔案 (STATIC_ROOT) 使用 WhiteNoise
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# 根據 S3 設定動態產生 MEDIA_URL
if AWS_STORAGE_BUCKET_NAME:
    if AWS_S3_ENDPOINT_URL: # MinIO or other S3-compatible
        MEDIA_URL = f"{AWS_S3_ENDPOINT_URL.rstrip('/')}/{AWS_STORAGE_BUCKET_NAME}/{AWS_LOCATION.strip('/')}/"
    elif AWS_S3_REGION_NAME: # AWS S3
        MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/{AWS_LOCATION.strip('/')}/"
    else: # Fallback
        MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{AWS_LOCATION.strip('/')}/"
        print(f"Warning: AWS_S3_REGION_NAME is not set. MEDIA_URL might be incorrect.")
    print(f"MEDIA_URL configured to: {MEDIA_URL}")
else:
    MEDIA_URL = '/media/' # 如果不使用 S3，使用本地路徑
    MEDIA_ROOT = BASE_DIR / 'media' # 並設定本地 MEDIA_ROOT
    print("Warning: AWS_STORAGE_BUCKET_NAME is not set. Using local media storage.")


# --- Celery 設定 ---
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = 'django-db' # 將結果儲存在 Django 資料庫
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE # 【重要】讓 Celery 和 Django 使用相同的時區
CELERY_TASK_TRACK_STARTED = True
CELERY_RESULT_EXTENDED = True # <-- (優化) 在 Admin 中儲存任務參數，方便除錯

# --- Celery Beat 設定 ---
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
CELERY_BEAT_SCHEDULE = {
    'cleanup-every-night': {
        'task': 'detector.tasks.cleanup_old_detection_data_task',
        'schedule': crontab(hour=13, minute=27), # (您設定的時間)
    },
}

# --- 自訂清理任務參數 ---
MANUAL_RECORDS_TO_KEEP = 2
DAYS_TO_KEEP_MANUAL_RECORDS = 0
DAYS_TO_KEEP_BATCHES = 0
BATCH_JOBS_TO_KEEP_BY_COUNT = 2

# --- LOGGING 設定 ---
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
        'verbose': {
            'format': '[{asctime}] {levelname} [{name}:{lineno}] {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG' if DEBUG else 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
        'detector': { # 您的 app
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        # 關閉吵雜的第三方庫日誌
        'boto3': {'handlers': ['console'],'level': 'WARNING','propagate': False,},
        'botocore': {'handlers': ['console'],'level': 'WARNING','propagate': False,},
        's3transfer': {'handlers': ['console'],'level': 'WARNING','propagate': False,},
        'urllib3': {'handlers': ['console'],'level': 'WARNING','propagate': False,},
        'storages': {'handlers': ['console'],'level': 'INFO','propagate': False,},
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    }
}