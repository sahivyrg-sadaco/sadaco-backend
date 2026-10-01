"""
Django settings for SADACO ERP/CRM.

Single settings file, env-driven via django-environ.
See .env.example for required variables.
"""
from pathlib import Path
from datetime import timedelta
import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / '.env')

SECRET_KEY    = env('SECRET_KEY', default='dev-secret-key-change-me')
DEBUG         = env.bool('DEBUG', default=False)
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['*'])

# ── Applications ──────────────────────────────────────────────────────────────
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
]

LOCAL_APPS = [
    'apps.accounts',
    'apps.clients',
    'apps.suppliers',
    'apps.deals',
    'apps.quotes',
    'apps.documents',
    'apps.payments',
    'apps.inventory',
    'apps.notifications',
    'apps.analytics',
    'apps.core',
    'apps.logistics',
    'apps.costs',
    'apps.rfqs',
    'apps.finance',
    'apps.clientquotes',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'sadaco.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'sadaco.wsgi.application'
ASGI_APPLICATION = 'sadaco.asgi.application'

# ── Database ──────────────────────────────────────────────────────────────────
DATABASES = {
    'default': env.db(
        'DATABASE_URL',
        default='sqlite:///' + str(BASE_DIR / 'db.sqlite3'),
    ),
}

# ── Custom user ───────────────────────────────────────────────────────────────
AUTH_USER_MODEL    = 'accounts.User'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 8}},
]

# ── DRF + JWT ─────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PAGINATION_CLASS': None,
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS':  True,
    'AUTH_HEADER_TYPES':      ('Bearer',),
    'USER_ID_FIELD':          'id',
    'USER_ID_CLAIM':          'user_id',
}

# ── CORS ──────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = env.list(
    'CORS_ALLOWED_ORIGINS',
    default=['http://localhost:5173', 'http://127.0.0.1:5173'],
)
CORS_ALLOWED_ORIGIN_REGEXES = [
    r'^https://.*\.vercel\.app$',
]
CORS_ALLOW_CREDENTIALS = True

# ── i18n / timezone ───────────────────────────────────────────────────────────
LANGUAGE_CODE = 'es-ve'
TIME_ZONE     = 'America/New_York'
USE_I18N      = True
USE_TZ        = True

# ── Static files ──────────────────────────────────────────────────────────────
STATIC_URL  = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# ── Google Drive service account ──────────────────────────────────────────────
GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE = env('GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE', default='')
GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON = env('GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON', default='')
GOOGLE_DRIVE_ROOT_FOLDER_ID       = env('GOOGLE_DRIVE_ROOT_FOLDER_ID', default='')

# ── Business constants ────────────────────────────────────────────────────────
PIPELINE_STAGES = [
    'Quoting', 'Negotiating', "Client's PO Received",
    'PO Sent', 'Invoiced', 'Delivered', 'Closed', 'Cancelled',
]
CURRENCIES    = ['USD', 'EUR', 'VES', 'COP', 'BRL']
# Incoterms 2020 (ICC). Deals saved with older terms such as DDU keep them.
INCOTERMS     = ['EXW', 'FCA', 'FAS', 'FOB', 'CFR', 'CIF', 'CPT', 'CIP', 'DAP', 'DPU', 'DDP']
PAYMENT_TERMS = [
    '100% Prepagado', '50% anticipado / 50% contra entrega',
    '30% anticipado / 70% contra entrega',
    'Net 30', 'Net 60', 'Letter of Credit (Carta de Crédito)',
]
LOCATIONS = [
    'Miami, Florida', 'La Guaira, Venezuela',
    'Puerto Cabello, Venezuela', 'Puerto Ordaz, Venezuela', 'Su almacen',
]
UNITS = [
    'Kg', 'MT (TM)', 'lbs', 'in', 'ft', 'mm', 'm',
    'liters (litros)', 'gal',
    'Box of 25 (Caja de 25)', 'Box of 50 (Caja de 50)',
    'Box of 100 (Caja de 100)', 'Unit (Unid)',
]
SELLER_ENTITIES = {
    'SADACO INTERNATIONAL LLC': {
        'address_line1': '7950 NW 53rd Street - Suite #244',
        'address_line2': 'Miami, FL 33166', 'country': 'USA',
        'bank_accounts': {
            'USD': {'beneficiary': 'SADACO INTERNATIONAL LLC', 'bank': '', 'swift': '', 'account': ''},
            'EUR': {'beneficiary': 'SADACO INTERNATIONAL LLC', 'bank': '', 'swift': '', 'account': ''},
        },
    },
    'SADACO, C.A. (J-31077567)': {
        'address_line1': 'Av. Las Americas. Torre Loreto II. Piso 1. Ofic: 102.',
        'address_line2': 'Puerto Ordaz, Bolívar, Venezuela', 'country': 'Venezuela',
        'bank_accounts': {
            'USD': {'beneficiary': 'SADACO C.A.', 'bank': '', 'swift': '', 'account': ''},
            'EUR': {'beneficiary': 'SADACO C.A.', 'bank': '', 'swift': '', 'account': ''},
        },
    },
    'SADACO INDUSTRIES LTD': {
        'address_line1': '18C-3107 av. Des Hôtels',
        'address_line2': 'Québec (Québec) G1W 4W5, Canada', 'country': 'Canada',
        'bank_accounts': {
            'USD': {'beneficiary': 'SADACO INDUSTRIES LTD', 'bank': 'BANESCO',
                    'swift': 'BANSPAPAXXX', 'account': '221021280085'},
            'EUR': {'beneficiary': 'SADACO INDUSTRIES LTD', 'bank': '', 'swift': '', 'account': ''},
        },
    },
}

# ── Logging ───────────────────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {'handlers': ['console'], 'level': 'INFO'},
}
