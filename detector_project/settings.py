# settings.py

import os
from pathlib import Path
from dotenv import load_dotenv

# 1. BASE_DIR 定義
BASE_DIR = Path(__file__).resolve().parent.parent

# 2. 載入 .env 檔案
dotenv_path = os.path.join(BASE_DIR, '.env')
if os.path.exists(dotenv_path):
    print(f"Loading .env file from: {dotenv_path}")
    load_dotenv(dotenv_path)
else:
    print(f"Warning: .env file not found at {dotenv_path}.")

# 3. 基本 Django 設定
SECRET_KEY = os.environ.get('SECRET_KEY', 'your-default-secret-key')
DEBUG = os.environ.get('DEBUG', '0') == '1'
allowed_hosts_str = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1')
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_str.split(',') if host.strip()]
CSRF_TRUSTED_ORIGINS = ['http://localhost:8000', 'http://127.0.0.1:8000']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'detector',
    'storages',
]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',  # 必須為 DjangoTemplates
        'DIRS': [BASE_DIR / 'templates'],  # 放置自訂模板的資料夾
        'APP_DIRS': True,                  # 啟用每個 app 下的 templates/ 資料夾
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',            # admin sidebar 需要
                'django.contrib.auth.context_processors.auth',           # 認證資料
                'django.contrib.messages.context_processors.messages',   # 訊息 framework
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
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- 全域 AWS 設定 ---
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME')
AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME')
AWS_S3_ENDPOINT_URL = os.environ.get('AWS_S3_ENDPOINT_URL')

# 強制所有上傳啟用 SSE-S3
AWS_S3_OBJECT_PARAMETERS = {
    'ServerSideEncryption': 'AES256',
}

# 這些設定給 django-storages 使用
AWS_DEFAULT_ACL = 'private'
AWS_S3_SECURE_URLS = True
AWS_QUERYSTRING_AUTH = True
AWS_QUERYSTRING_EXPIRE = 3600
AWS_LOCATION = 'media'
AWS_S3_FILE_OVERWRITE = False

# --- Django 4.2+ STORAGES 設定 ---
STORAGES = {
    'default': {
        'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
        'OPTIONS': {
            'object_parameters': AWS_S3_OBJECT_PARAMETERS,
        },
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

# MEDIA_URL 生成
if AWS_STORAGE_BUCKET_NAME and AWS_S3_REGION_NAME:
    if AWS_S3_ENDPOINT_URL:
        MEDIA_URL = f"{AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/{AWS_LOCATION}/"
    else:
        MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/{AWS_LOCATION}/"
    print(f"MEDIA_URL = {MEDIA_URL}")
else:
    MEDIA_URL = '/media_default_local_error/'
    print("Warning: MEDIA_URL may not be set correctly due to missing S3 settings.")

# LOGGING 設定
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            # 在開發時，可以保持 'DEBUG' 以便看到自己 app 的 debug 訊息
            # 在生產時，通常會設為 'INFO' 或 'WARNING'
            'level': 'INFO', # 或者 'DEBUG' 如果您還想看 app 的 debug 訊息
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': { # Django 自身的 logger
            'handlers': ['console'],
            'level': 'INFO', # Django 訊息通常設為 INFO
            'propagate': False,
        },
        'django.server': { # runserver 的日誌
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # 如果不需要詳細的資料庫查詢日誌，可以將 django.db.backends 的級別設高或移除
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'WARNING', # 或者 'INFO'
            'propagate': False,
        },
        # 將 boto3, botocore, s3transfer, urllib3 的日誌級別調高，以減少雜訊
        'boto3': {
            'handlers': ['console'],
            'level': 'WARNING', # 或 'INFO'
            'propagate': False,
        },
        'botocore': {
            'handlers': ['console'],
            'level': 'WARNING', # 或 'INFO'
            'propagate': False,
        },
        's3transfer': {
            'handlers': ['console'],
            'level': 'WARNING', # 或 'INFO'
            'propagate': False,
        },
        'urllib3': {
            'handlers': ['console'],
            'level': 'WARNING', # 或 'INFO'
            'propagate': False,
        },
        'storages': { # django-storages 自身的 logger
            'handlers': ['console'],
            'level': 'INFO', # 或 'WARNING'
            'propagate': False,
        },
        'detector': { # 您自己 app 的 logger
            'handlers': ['console'],
            'level': 'INFO', # 開發時可以保持 DEBUG，方便調試您自己的 app
            'propagate': False,
        },
    },
    # Root logger 的級別也應該相應調整
    'root': {
        'handlers': ['console'],
        'level': 'INFO', # 或 'WARNING'
    }
}
