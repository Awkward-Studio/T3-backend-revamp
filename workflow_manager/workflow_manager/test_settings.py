from .settings import *

MIDDLEWARE = [
    middleware
    for middleware in MIDDLEWARE
    if middleware != "whitenoise.middleware.WhiteNoiseMiddleware"
]

STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
