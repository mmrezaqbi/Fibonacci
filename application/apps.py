from django.apps import AppConfig


class ApplicationConfig(AppConfig):
    name = 'application'

    def ready(self):
        from . import signals  # noqa: F401  (ثبت لاگ ورود و خروج)
