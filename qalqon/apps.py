from django.apps import AppConfig
from django.db.models.signals import post_migrate


class QalqonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "qalqon"
    verbose_name = "Qalqon jamoatchilik guruhi"

    def ready(self):
        from .initial_data import load_initial_data

        post_migrate.connect(load_initial_data, sender=self, dispatch_uid="qalqon_initial_data")
