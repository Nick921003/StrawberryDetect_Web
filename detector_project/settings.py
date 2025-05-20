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

# ... (您原有的 SECRET_KEY, DEBUG, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS 等設定) ...
SECRET_KEY = os.environ.get('SECRET_KEY', 'your-default-secret-key')
DEBUG = os.environ.get('DEBUG', '0') == '1'
allowed_hosts_str = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1')
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_str.split(',') if host.strip()]
CSRF_TRUSTED_ORIGINS = os.environ.get('CSRF_TRUSTED_ORIGINS', 'http://localhost:8000,http://127.0.0.1:8000').split(',')


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
]

# ... (您原有的 TEMPLATES, MIDDLEWARE, ROOT_URLCONF, WSGI_APPLICATION, DATABASES, AUTH_PASSWORD_VALIDATORS 等設定) ...
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'detector_project.urls'
WSGI_APPLICATION = 'detector_project.wsgi.application'

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
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- 全域 AWS 設定 ---
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME')
AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME')
AWS_S3_ENDPOINT_URL = os.environ.get('AWS_S3_ENDPOINT_URL') # 主要用於 MinIO 等相容服務

AWS_S3_OBJECT_PARAMETERS = {
    'ServerSideEncryption': 'AES256',
}
AWS_DEFAULT_ACL = 'private' # 或 'public-read' 如果您希望檔案預設公開，但通常 'private' 更好
AWS_S3_SECURE_URLS = True       # 使用 https
AWS_QUERYSTRING_AUTH = True     # 生成簽名 URL (如果 ACL 是 private)
AWS_QUERYSTRING_EXPIRE = 3600   # 簽名 URL 過期時間 (秒)
AWS_LOCATION = 'media'          # S3 儲存桶中媒體檔案的子目錄
AWS_S3_FILE_OVERWRITE = False   # 不覆蓋同名檔案 (False 會在檔名後附加隨機字元)

STORAGES = {
    'default': {
        'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
        'OPTIONS': {
            'object_parameters': AWS_S3_OBJECT_PARAMETERS,
            # 'bucket_name': AWS_STORAGE_BUCKET_NAME, # 通常 django-storages 會從全域設定讀取
            # 'region_name': AWS_S3_REGION_NAME,
            # 'endpoint_url': AWS_S3_ENDPOINT_URL,
        },
    },
    'staticfiles': { # 靜態檔案通常不由 S3 託管，除非您有特定需求
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

if AWS_STORAGE_BUCKET_NAME:
    if AWS_S3_ENDPOINT_URL: # MinIO or other S3-compatible
        MEDIA_URL = f"{AWS_S3_ENDPOINT_URL.rstrip('/')}/{AWS_STORAGE_BUCKET_NAME}/{AWS_LOCATION.strip('/')}/"
    elif AWS_S3_REGION_NAME: # AWS S3
        MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/{AWS_LOCATION.strip('/')}/"
    else: # Fallback or error if region is also missing for AWS S3
        MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{AWS_LOCATION.strip('/')}/" # Default if region somehow not set but bucket is
        print(f"Warning: AWS_S3_REGION_NAME is not set. MEDIA_URL might be incorrect if bucket is not in us-east-1 or requires region in URL.")
    print(f"MEDIA_URL configured to: {MEDIA_URL}")
else:
    MEDIA_URL = '/media_default_local_error/' # 或者您的本地 MEDIA_URL
    print("Warning: AWS_STORAGE_BUCKET_NAME is not set. MEDIA_URL is set to a local path or error placeholder.")
    # 如果不使用 S3，您應該設定本地的 MEDIA_ROOT
    # MEDIA_ROOT = BASE_DIR / 'media'


# --- Celery 設定 ---
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = 'django-db'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE # 【重要】讓 Celery 和 Django 使用相同的時區
CELERY_TASK_TRACK_STARTED = True

# --- Celery Beat 設定 ---
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler' # <-- 【修改點】啟用資料庫排程器
CELERY_BEAT_SCHEDULE = {
    'cleanup-every-night': {
        'task': 'detector.tasks.cleanup_old_detection_data_task',  # 指向我們在 tasks.py 中定義的任務
        'schedule': crontab(hour=13, minute=27),  # 例如：每天凌晨 2:30 執行
        # 'args': (some_arg, another_arg), # 如果您的清理任務需要參數，可以在這裡提供
    },
}

# --- 清理任務參數設定 ---
# MANUAL_RECORDS_TO_KEEP_IMMEDIATE = 5  # 手動上傳記錄保留數量(即時)
MANUAL_RECORDS_TO_KEEP = 2  # 手動上傳記錄保留數量(數量)
DAYS_TO_KEEP_MANUAL_RECORDS = 0  # 手動上傳記錄保留天數(時間)
DAYS_TO_KEEP_BATCHES = 0   # 批次任務記錄保留天數(時間)
BATCH_JOBS_TO_KEEP_BY_COUNT = 2 # 批次任務記錄保留數量(數量)

# ... (您原有的 LOGGING 設定) ...
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
            'level': 'DEBUG' if DEBUG else 'INFO', # 開發時 DEBUG，生產時 INFO
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
        'django.db.backends': { # 資料庫查詢日誌，生產環境建議 WARNING
            'handlers': ['console'],
            'level': 'WARNING', #  DEBUG 時可以設為 INFO 或 DEBUG 來看 SQL
            'propagate': False,
        },
        'celery': { # Celery 自身的日誌
            'handlers': ['console'],
            'level': 'INFO', # DEBUG 時可以設為 DEBUG
            'propagate': True, # Propagate to root logger
        },
        'detector': { # 您 detector app 的日誌
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        # 可以為其他第三方庫設定日誌級別
        'boto3': {'handlers': ['console'],'level': 'WARNING','propagate': False,},
        'botocore': {'handlers': ['console'],'level': 'WARNING','propagate': False,},
        's3transfer': {'handlers': ['console'],'level': 'WARNING','propagate': False,},
        'urllib3': {'handlers': ['console'],'level': 'WARNING','propagate': False,},
        'storages': {'handlers': ['console'],'level': 'INFO','propagate': False,},
    },
    'root': { # Root logger
        'handlers': ['console'],
        'level': 'INFO', # 生產環境的基礎日誌級別
    }
}