# CubelessMail

## Introduction

CubelessMail is my attempt to use AI to create a Python, Django, CSS3 version of RoundCube.

## Project Goals

- Learn to prompt AI
- Modern web user interface
  - threaded emails (maybe)
  - right-click actions (unlikely)
  - themes: dark or light mode only
- IMAPS only
- SMTP (secure only)
  - Implicit TLS (SMTPS)
  - STARTTLS
- CALDAV calendar (unlikely)
- Contact management (eventually)
- Django PAM modules e.g. django_pam for local auth (eventually)

## Next Up TODO

- Folder Management
  - Sub-folders
  - expand and collapse
- Compose
  - Create new messages (done)
  - Reply (done)
  - Reply All (working)
  - Forward (done)
  - Use an HTML editor for composition (used Quill. Done.)

## Setup & Configuration

### Prerequisites

- Python 3.9+
- pip or conda

### Installation

1. Clone the repository:

```bash
git clone <repository-url>
cd CubelessMail
```

1. Create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\Activate.ps1
```

1. Install dependencies:

```bash
pip install -r requirements.txt
```

1. Create a `.env` file in the project root directory with the required environment variables:

```bash
cp .env.example .env
```

### Environment Variables

The following environment variables **must** be configured in your `.env` file:

#### Required for Production

- **`DJANGO_ENV`** - Set to `production` for deployed environments. Use `local` for development.
- **`DJANGO_SECRET_KEY`** - Strong Django secret key, unique per environment.
- **`ALLOWED_HOSTS`** - Comma-separated public hostnames (for example: `mail.example.com,www.mail.example.com`).
- **`MAIL_ENCRYPTION_KEY`** - Encryption key for storing IMAP credentials securely.
  - Generate a new key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  - Store the output in your `.env` file
  - **CRITICAL**: Change this value in production. Do not use the example key.

#### Optional

- `DEBUG` - Explicit override. Defaults to `True` in local mode and `False` in production mode.
- `CSRF_TRUSTED_ORIGINS` - Comma-separated HTTPS origins for deployments behind domain/proxy.
- `TRUST_PROXY_SSL_HEADER` - Set `True` only behind a trusted reverse proxy that sets `X-Forwarded-Proto`.
- `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS` - Optional overrides.
- `SESSION_COOKIE_SAMESITE`, `CSRF_COOKIE_SAMESITE` - Cookie cross-site policy (default: `Lax`).
- `SECURE_REFERRER_POLICY` - Referrer leakage policy (default: `strict-origin-when-cross-origin`).
- `SECURE_CROSS_ORIGIN_OPENER_POLICY` - Cross-origin opener isolation policy (default: `same-origin`).
- `X_FRAME_OPTIONS` - Clickjacking protection header (default: `DENY`).
- `AXES_ENABLED` - Enables login lockout protection (default: `False` local, `True` production).
- `AXES_FAILURE_LIMIT` - Number of failed login attempts allowed before lockout (default: `5`).
- `AXES_COOLOFF_MINUTES` - Lockout cooldown in minutes (default: `30`).
- `AXES_RESET_ON_SUCCESS` - Reset failure counter after successful login (default: `True`).
- `ADMIN_IP_ALLOWLIST_ENABLED` - Restrict `/admin/` to trusted IPs/CIDRs (default: `False` local, `True` production).
- `ADMIN_IP_ALLOWLIST` - Comma-separated IPs/CIDRs allowed to access `/admin/`.
- `ADMIN_IP_ALLOWLIST_TRUST_X_FORWARDED_FOR` - Set `True` only when a trusted proxy sets `X-Forwarded-For` correctly.
- `COMPOSE_MAX_RECIPIENTS` - Maximum combined To/CC/BCC recipients per send request (default: `50`).
- `COMPOSE_MAX_SUBJECT_LEN` - Maximum subject length (default: `255`).
- `COMPOSE_MAX_BODY_LEN` - Maximum text or HTML body length (default: `200000`).
- `COMPOSE_MAX_ATTACHMENT_SIZE` - Max bytes per attachment (default: `10485760`, 10MB).
- `COMPOSE_MAX_TOTAL_ATTACHMENT_SIZE` - Max total bytes across attachments (default: `26214400`, 25MB).

### Local-Safe vs Production-Safe Defaults

CubelessMail now uses environment-aware security defaults:

- Local (`DJANGO_ENV=local`): avoids breaking local HTTP development (`runserver` works on `http://127.0.0.1:8000`).
- Production (`DJANGO_ENV=production`): enables secure-cookie and HTTPS-oriented settings by default.

This means you can use one `settings.py` for both local and deployed environments without manual edits.

### Database Migrations

After configuring environment variables, initialize the database:

```bash
python manage.py migrate
```

This command will:

- Create the SQLite database file (`db.sqlite3`) if it doesn't exist
- Set up all required tables and schemas
- No additional database server setup needed

### Creating a Superuser

```bash
python manage.py createsuperuser
```

### Running the Development Server

```bash
python manage.py runserver
```

Visit `http://localhost:8000` in your browser.

## Security

- All IMAP credentials are encrypted at rest using Fernet symmetric encryption
- The encryption key is stored in the environment (`MAIL_ENCRYPTION_KEY`) and never committed to version control
- All endpoints require authentication
- Django's CSRF protection is enabled
- Login brute-force protection is available through django-axes (enabled by default in production)
- Admin access can be restricted to trusted IP ranges through an environment-driven allowlist
