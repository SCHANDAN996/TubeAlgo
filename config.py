# config.py

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Base configuration class."""
    
    SECRET_KEY = os.environ.get('SECRET_KEY', 'a-default-secret-key-for-local-dev')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    MEASUREMENT_ID = os.environ.get('MEASUREMENT_ID')
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

    # Database
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = DATABASE_URL or 'sqlite:///local_dev.db'

    # Cashfree
    CASHFREE_APP_ID = os.environ.get('CASHFREE_APP_ID')
    CASHFREE_SECRET_KEY = os.environ.get('CASHFREE_SECRET_KEY')
    CASHFREE_ENV = os.environ.get('CASHFREE_ENV', 'PROD')

    # *** UPDATED: Celery Configuration ***
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
    
    # Connection retry settings
    CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
    CELERY_BROKER_CONNECTION_RETRY = True
    CELERY_BROKER_CONNECTION_MAX_RETRIES = 10
    CELERY_TASK_IGNORE_RESULT = True
