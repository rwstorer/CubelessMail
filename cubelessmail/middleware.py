from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponseForbidden
from ipaddress import ip_address, ip_network


class AdminIPAllowlistMiddleware:
    """Restrict /admin/ access to configured source IP addresses/CIDRs."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.enabled = bool(getattr(settings, 'ADMIN_IP_ALLOWLIST_ENABLED', False))
        self.trust_x_forwarded_for = bool(
            getattr(settings, 'ADMIN_IP_ALLOWLIST_TRUST_X_FORWARDED_FOR', False)
        )
        self.allowed_networks = self._build_allowed_networks()

    def __call__(self, request):
        if self.enabled and request.path_info.startswith('/admin/'):
            client_ip = self._get_client_ip(request)
            if client_ip is None or not self._is_allowed(client_ip):
                return HttpResponseForbidden('Access denied.')
        return self.get_response(request)

    def _build_allowed_networks(self):
        if not self.enabled:
            return []

        raw_entries = getattr(settings, 'ADMIN_IP_ALLOWLIST', [])
        if not raw_entries:
            raise ImproperlyConfigured(
                'ADMIN_IP_ALLOWLIST_ENABLED is true but ADMIN_IP_ALLOWLIST is empty.'
            )

        networks = []
        for raw_entry in raw_entries:
            try:
                entry = raw_entry.strip()
                if '/' in entry:
                    networks.append(ip_network(entry, strict=False))
                else:
                    ip = ip_address(entry)
                    cidr_suffix = 32 if ip.version == 4 else 128
                    networks.append(ip_network(f'{entry}/{cidr_suffix}', strict=False))
            except ValueError as exc:
                raise ImproperlyConfigured(
                    f'Invalid ADMIN_IP_ALLOWLIST entry: {raw_entry}'
                ) from exc
        return networks

    def _get_client_ip(self, request):
        if self.trust_x_forwarded_for:
            forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
            if forwarded_for:
                return forwarded_for.split(',')[0].strip()
        return (request.META.get('REMOTE_ADDR') or '').strip() or None

    def _is_allowed(self, client_ip):
        try:
            ip_obj = ip_address(client_ip)
        except ValueError:
            return False
        return any(ip_obj in network for network in self.allowed_networks)


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