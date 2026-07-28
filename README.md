# Orchard Lodge Accounting Portal

A private Django application for managing resident accounts at Orchard Lodge. It brings resident records, invoices, council remittances, bank payments, statements of account, and payment reconciliation into one browser-based workflow.

The repository includes a completely synthetic development environment so the application can be explored without using production resident or financial data.

## Features

- Maintain current, former, council-funded, and privately funded resident records.
- Import Sefton remittance advice and generate resident invoices.
- Download Santander statements and import incoming payments.
- Match payments to residents using reusable description filters.
- Compare invoices, resident payments, and Sefton payment totals.
- Generate statements of account and optional cover letters.
- Convert statements to PDF when LibreOffice is available, with DOCX fallback.
- Draft invoice emails in Gmail via IMAP.
- Retrieve Sefton action items and display their conversation history.
- Export current resident details to Excel.

## Technology

- Python 3 and Django 5
- SQLite
- pandas and openpyxl for spreadsheet processing
- python-docx and pypdf for account documents
- Selenium with Chrome and Firefox for Santander and Sefton automation
- Bootstrap 4 and django-crispy-forms
- WhiteNoise for static files

## Quick start

### 1. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

On Windows, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

### 2. Create the synthetic development environment

```bash
python3 backend/create_dev_data.py --produce-files
```

This command:

- recreates `Dev data/db.sqlite3`;
- runs all database migrations;
- adds synthetic residents, invoices, payments, Sefton payments, and action items;
- generates dummy invoices, statements, remittance advice, and secret files; and
- creates the development administrator.

> **Warning:** the command deletes and recreates the development database. Do not point the development settings at production data.

To seed only the database without regenerating files:

```bash
python3 backend/create_dev_data.py
```

### 3. Start Django

```bash
python3 manage.py runserver --settings=OrchardLodge.settings.development
```

Open <http://127.0.0.1:8000/>.

### Development login

These credentials are deliberately public and work only with the synthetic database created above:

```text
Username: orchard-dev
Password: orchard-dev-password
```

## Running checks

Run the test suite and Django configuration checks explicitly against development settings:

```bash
python3 manage.py test --settings=OrchardLodge.settings.development
python3 manage.py check --settings=OrchardLodge.settings.development
```

## Application workflow

1. **Residents** are created and maintained through the resident dashboard.
2. **Sefton remittance advice** is downloaded or read from CSV.
3. The remittance data is converted into invoice database rows and local DOCX files.
4. **Santander statements** are downloaded and combined with the local payment workbook.
5. New payments are stored and matched to residents using description filters.
6. Resident pages combine invoices, payments, and Sefton totals.
7. Statements of account and cover letters can be generated from the stored templates.

The database and local accounting files form one workflow. When changing invoice or statement behavior, keep the corresponding database rows and files synchronized.

## Configuration

The project has separate settings modules:

| Module | Purpose |
| --- | --- |
| `OrchardLodge.settings.base` | Shared Django configuration |
| `OrchardLodge.settings.development` | Repository-local synthetic data under `Dev data/` |
| `OrchardLodge.settings.production` | External production data and secrets |

Always select a settings module explicitly:

```bash
python3 manage.py <command> --settings=OrchardLodge.settings.development
```

For production:

```bash
python3 manage.py <command> --settings=OrchardLodge.settings.production
```

### Production settings

Production paths are installation-specific and are currently defined in `OrchardLodge/settings/production.py`. Review them before deployment.

`Production_settings.json`, located under the configured production media root, must provide:

```json
{
  "ALLOWED_HOSTS": ["accounting.example.internal"],
  "SECRET_KEY": "replace-with-a-unique-production-secret"
}
```

Never reuse the development secret key in production.

### Santander configuration

`Santander_login.json` lives under `SECRET_MEDIA_ROOT`:

```json
{
  "SANTANDER_COOKIE_DIR": "Santander cookies",
  "AGENT_STRING": "browser user agent",
  "BANK_DETAILS": {
    "PID": "personal identifier",
    "SECURITY_NUMBER": "security number"
  }
}
```

Santander automation requires Chrome. The matching ChromeDriver is obtained by `webdriver_manager`.

### Email configuration

`Email_details.json` also lives under `SECRET_MEDIA_ROOT`:

```json
{
  "EMAIL_ADDRESS": "finance@example.com",
  "EMAIL_PASSWORD": "application password",
  "CC": "accounts@example.com",
  "BCC": "audit@example.com"
}
```

The email workflow connects to Gmail over IMAP and saves messages to the Drafts mailbox rather than sending them automatically.

### Sefton configuration

Sefton login details are stored in the `sefton_login_details` database row. Sefton automation requires Firefox; `webdriver_manager` obtains GeckoDriver.

Both bank and council automation depend on third-party page structure and may need maintenance when those websites change.

## Document templates

Development templates are stored in:

```text
Dev data/Invoices/Templates/
```

The application expects:

- `INVOICE TEMPLATE.docx`
- `STATEMENT OF ACCOUNT TEMPLATE.docx`
- the numbered statement cover-letter templates

LibreOffice is optional. When it is available, statements can be converted to PDF; otherwise the application returns DOCX files or a ZIP containing the statement and cover letter.

## Useful scripts

| Command | Purpose |
| --- | --- |
| `python3 backend/create_dev_data.py --produce-files` | Rebuild all synthetic development data and files |
| `python3 backend/export_current_residents.py` | Export current residents to `Current residents.xlsx` |
| `python3 backend/draft_emails.py` | Create Gmail drafts for the latest invoice batch |
| `python3 backend/statement_of_account.py` | Generate statements of account |

Scripts that use Django should be run with the intended `DJANGO_SETTINGS_MODULE` selected. The development-data and resident-export scripts select development settings themselves.

## Project structure

```text
OrchardLodge/       Django project, URL configuration, and settings
main/               Models, forms, views, templates, migrations, and tests
backend/            Accounting, document, scraper, email, and export workflows
static/             Source CSS and images
Dev data/           Synthetic database, media, templates, and generated files
requirements.txt    Python dependencies
```

## Data and security

This application handles resident, financial, and authentication data.

- Never commit production databases, invoices, statements, bank exports, cookies, or secret JSON files.
- Keep production media and secrets outside the repository.
- Use unique production credentials and rotate anything that may have been exposed.
- Review generated files before sharing them.
- Back up both the production database and its associated accounting files.

All names, identifiers, credentials, transactions, invoices, and action items produced by `create_dev_data.py` are synthetic.
