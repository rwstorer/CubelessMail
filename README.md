# CubelessMail

## Introduction

CubelessMail is my attempt to create a Python, Django, CSS3 version of RoundCube.

## Project Goals

- Modern web user interface
  - threaded emails (maybe)
  - right-click actions (maybe)
  - end users choose color scheme (maybe)
- IMAPS only
- SMTP (secure only)
  - Implicit TLS (SMTPS)
  - STARTTLS
- CALDAV calendar (eventually)
- Contact management (eventually)

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

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\Activate.ps1
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file in the project root directory with the required environment variables:
```bash
cp .env.example .env
```

### Environment Variables

The following environment variables **must** be configured in your `.env` file:

#### Required for Production
- **`MAIL_ENCRYPTION_KEY`** - Encryption key for storing IMAP credentials securely.
  - Generate a new key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  - Store the output in your `.env` file
  - **CRITICAL**: Change this value in production. Do not use the example key.

#### Optional
- `DEBUG` - Set to `False` in production (default: `True`)
- `SECRET_KEY` - Django secret key (change in production)
- `ALLOWED_HOSTS` - Comma-separated list of allowed hosts

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
