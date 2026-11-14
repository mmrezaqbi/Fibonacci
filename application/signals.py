from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from .activity import A, log_activity


@receiver(user_logged_in)
def _log_login(sender, request, user, **kwargs):
    log_activity(request, A.LOGIN, user=user)


@receiver(user_logged_out)
def _log_logout(sender, request, user, **kwargs):
    if user is not None:
        log_activity(request, A.LOGOUT, user=user)
