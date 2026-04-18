from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.views import redirect_to_login


class LoginRequiredMiddleware:
    """Require authentication for all routes except explicit allowlisted paths."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._exempt_prefixes = self._build_exempt_prefixes()

    def __call__(self, request):
        if request.user.is_authenticated or self._is_exempt(request.path_info):
            return self.get_response(request)

        return redirect_to_login(
            request.get_full_path(),
            settings.LOGIN_URL,
            REDIRECT_FIELD_NAME,
        )

    def _is_exempt(self, path):
        return any(path.startswith(prefix) for prefix in self._exempt_prefixes)

    def _build_exempt_prefixes(self):
        login_url = str(getattr(settings, 'LOGIN_URL', '/accounts/login/')).rstrip('/')
        login_prefix = f"{login_url}/"

        return (
            f"{login_url}",
            login_prefix,
            '/accounts/',
            '/admin/',
            '/static/',
            '/media/',
            '/favicon.ico',
        )