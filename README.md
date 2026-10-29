# Gather & Co. — Event Inventory & Reservations

Gather & Co. is a responsive Django application for event-rental inventory, reservation requests, customer support, and owner operations. Customers can browse equipment and request rentals for a date range; owners maintain their collection and approve or decline requests.

> **Demo-only credentials:** `demo_owner / Owner@12345` and `demo_customer / Customer@12345` are for local evaluation only. Change or remove these accounts before deploying a public instance.

**Live Demo:** [ADD_DEPLOYED_URL_HERE]

## Features

- Customer registration, login, dashboards, reservation history, and support tickets.
- Owner dashboard with inventory, reservations, estimated rental totals, and support ticket status.
- Inventory search and category filters, image upload or image URL, daily rate, and per-item deposit.
- Date-aware reservation checks that prevent overlapping requests from exceeding available stock.
- Reservation approval, rejection, completion, and customer cancellation before the event date.
- SQL-backed FAQs and owner management interface.
- Site-wide assistant with optional AI provider, FAQ-based fallback, human-ticket escalation, MongoDB chat logs, and feedback.
- Friendly error pages, request timing logs, health check, and a weather-provider endpoint with timeout/fallback.
- JSON APIs for inventory, FAQs, health, assistant, feedback, and weather.
- Mobile navigation, responsive layouts, and reduced-motion support.

## Technology

- Python 3.10+
- Django 5.1+
- SQLite by default; PostgreSQL supported via `DATABASE_URL`
- MongoDB (optional) for assistant conversation logs and feedback
- HTML, responsive CSS, and vanilla JavaScript

## Architecture

```text
config/                 Django settings, root URLs, ASGI/WSGI
rentals/                Domain models, forms, views, APIs, assistant, admin
rentals/management/     Repeatable demo-data command
templates/rentals/      Server-rendered pages and shared chat widget
static/css, static/js   Responsive frontend styles and interactions
media/                  User-uploaded item photos (local development)
```

Inventory, users, reservations, FAQs, error codes, and support tickets use Django ORM relational models. Reservation availability is computed from active overlapping requests; a stored availability counter is deliberately avoided. MongoDB is used only when `MONGODB_URI` is configured.

## Environment variables

Copy `.env.example` to `.env` and set values for your environment. `.env` is ignored by Git.

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django signing key; development generates a temporary key if missing/placeholder, while production requires a unique configured value |
| `DEBUG` | Enable Django debug mode locally only |
| `ALLOWED_HOSTS` | Comma-separated hostnames |
| `DATABASE_URL` | SQLite URL by default; a PostgreSQL URL can be supplied for production |
| `MONGODB_URI` | Optional MongoDB connection string for chat logs and assistant feedback |
| `MONGODB_DATABASE` | MongoDB database name |
| `AI_API_KEY` | Optional server-side key for an OpenAI-compatible chat-completions API |
| `AI_API_URL` | AI endpoint URL; defaults to OpenAI chat completions |
| `AI_MODEL` | Model identifier sent to the configured endpoint |
| `SECURE_SSL_REDIRECT` | Enforce HTTPS when `DEBUG=False` |
| `CACHE_BACKEND` | Django cache backend used for basic rate limiting |

Never put credentials in frontend JavaScript or commit `.env`.

## Install and run locally

From the project directory:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py makemigrations rentals
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open `http://127.0.0.1:8000/`. If `py` is not available, use `python` to create the virtual environment. Set `DEBUG=True` only for local development.

## Demo accounts

The seed command creates these accounts if they do not already exist. Existing passwords are not overwritten.

| Role | Username | Password |
|---|---|---|
| Owner | `demo_owner` | `Owner@12345` |
| Customer | `demo_customer` | `Customer@12345` |

The demo owner is granted the application owner role, not Django superuser access. Do not retain these credentials on a public deployment.

## Database and seed data

Run migrations after changing models:

```powershell
python manage.py makemigrations rentals
python manage.py migrate
```

Load repeatable sample data:

```powershell
python manage.py seed_demo
```

It creates two demo accounts, multiple categories, 14 inventory items, at least 10 FAQs, common error codes, an example reservation, and an example ticket. It uses `get_or_create`/`update_or_create` and is safe to run again.

## Main pages

| URL | Description |
|---|---|
| `/` | Landing page and featured inventory |
| `/inventory/` | Searchable event-rental collection |
| `/inventory/<slug>/` | Item details and reservation entry |
| `/dashboard/` | Customer or owner dashboard |
| `/faqs/` | Database-backed help articles |
| `/support/` | Create and track support tickets |
| `/about/` | About and contact entry point |
| `/health/` | JSON dependency health status |
| `/admin/` | Django admin for staff users |

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/inventory/` | Active inventory JSON |
| `GET` | `/api/inventory/<slug>/` | Inventory JSON filtered to one item |
| `GET` | `/api/faqs/` | Active FAQ JSON |
| `GET` / `POST` | `/api/reservations/` | List accessible reservations or create an authenticated customer's reservation |
| `POST` | `/api/chat/` | Assistant response and support escalation |
| `POST` | `/api/feedback/` | Save assistant feedback to configured MongoDB |
| `POST` | `/api/support/tickets/` | Create an authenticated support ticket |
| `GET` | `/api/weather/?city=...` | Weather endpoint with timeout and graceful fallback |
| `GET` | `/health/` | SQL and optional MongoDB health |

POST endpoints require the Django CSRF token. Reservation creation is authenticated and performs the same date availability check as the website form.

## Assistant, MongoDB, and third-party API

The assistant first tries the optional AI API using only FAQ context, then falls back to local FAQ matching. If no answer can be found, it creates a SQL support ticket. The API key remains on the server. Chat events and feedback are written to MongoDB when configured; without MongoDB, chat still responds but persistent chat history/feedback is unavailable.

The weather endpoint uses the public Open-Meteo forecast API with a five-second timeout. Provider errors return a friendly JSON fallback instead of breaking the site. Its sample coordinates are Bengaluru; location-specific geocoding is a future enhancement.

## Error codes and handling

The demo seed command inserts `400`, `401`, `403`, `404`, `429`, `500`, `503`, and the application-specific `EVT-001` (inventory unavailable) into SQL. Friendly HTML error pages are provided for 400, 403, 404, 429, 500, and 503. They do not expose stack traces and include a link/button to open the assistant.

Sensitive login, registration, support-ticket, and assistant paths have a simple per-IP cache limiter. The default local-memory cache is process-local; use a shared production cache such as Redis when deploying multiple workers.

## Logging and security

Request logging records method, path, status, and response time; it does not record submitted form bodies, passwords, API keys, or tokens. Django password hashing, CSRF middleware, role checks, server-side form validation, safe ORM queries, secure cookie flags in production, and HTTPS redirection are configured.

Before deploying, set a unique `SECRET_KEY`, `DEBUG=False`, a restrictive `ALLOWED_HOSTS`, a persistent database/cache, HTTPS, and production media storage. Review the Django deployment checklist and remove demo credentials/data.

## Tests

Run the Django test suite:

```powershell
python manage.py test
```

Tests cover account flows, role permissions, date availability and overbooking, FAQ retrieval, assistant escalation, error pages, health, and weather fallback.

## Deploy a free demo on Render

The repository includes a Render Blueprint in `render.yaml`. To deploy:

1. Push the latest `main` branch to GitHub.
2. Sign in at [Render](https://dashboard.render.com/) and choose **New → Blueprint**.
3. Connect the GitHub repository `jkishoresubha-crypto/Gather-Co..` and apply the `render.yaml` blueprint. Render builds the app, collects static files, runs database migrations at startup, and uses `/health/` as the health check.
4. Wait for the first deploy to finish and open the `.onrender.com` URL Render shows for the service.
5. In the Render service's **Shell**, create your own administrator/owner account with `python manage.py createsuperuser`. Use that account to add inventory, FAQs, and error codes in Django admin (`/admin/`).

### Important limitations of the free demo

- The blueprint uses SQLite on the free web service's ephemeral filesystem. **Data can be lost when the service restarts, sleeps, or redeploys.** Do not use this configuration for real reservations or customer data. Move to a managed PostgreSQL database before accepting real customers.
- Uploaded item files also live on ephemeral storage in this setup and can disappear. Use persistent object storage for production uploads; item image URLs can be used for a demo.
- Free web services may sleep when idle and take time to wake up. Availability and free-tier terms can change; review Render's current plan and pricing before applying the blueprint.
- Do not run `python manage.py seed_demo` on a public deployment: it creates accounts with documented demo passwords. Create a unique admin account instead.
- MongoDB chat persistence and AI API answers remain optional. Configure `MONGODB_URI` and/or `AI_API_KEY` through the Render service's environment settings if needed; never put secrets in `render.yaml`.

### Production deployment checklist

For a real public service, use persistent PostgreSQL, a shared production cache such as Redis for rate limits, durable object storage for uploads, a unique secret key, restricted allowed hosts, and appropriate backups. Configure `DATABASE_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and provider secrets in Render's environment settings. Verify `/health/` and test registration, reservations, cancellations, support, static assets, and backups before sharing the site with customers.

## GitHub

This project is already initialized on `main` and connected to its GitHub repository. To publish later changes:

```powershell
git add .
git status
git commit -m "Describe your change"
git push
```

If you intentionally want to publish this project to a different repository, create that repository first, then update the `origin` remote with its clone URL. Before committing, confirm `.env`, database files, uploaded media, and credentials are not staged. The `.gitignore` excludes local secrets and generated files.

## Proposed Future Improvement

Future versions could include online payment integration and automated email/SMS notifications for reservation approval and reminders.
