# Red Lifeline - Blood Bank Management System

A full-stack blood bank management platform for managing donors, hospitals, blood requests, donations, and inventory with role-based access control.

## Features

- Role-based dashboards for:
  - `SUPER_ADMIN`
  - `BLOOD_BANK_ADMIN`
  - `STAFF_MEMBER`
  - `HOSPITAL_USER`
  - `DONOR`
- Donor lifecycle management:
  - Add, update, deactivate/reactivate donors
  - Donor profile and availability updates
  - Donation frequency and eligibility insights
- Hospital management and request tracking
- Blood request workflow:
  - Create, approve, reject, cancel
  - Batch-aware inventory deduction and validation
- Batch-based blood inventory with expiry tracking
- Donation recording with automatic inventory updates
- RBAC user/role management
- Password change, forgot password, and reset flow
- Audit logs for privileged actions
- Health endpoint for deployment checks (`/healthz`)

## Tech Stack

- Backend: Python, Flask
- Server: Uvicorn + ASGI adapter (`WsgiToAsgi`)
- Database: MySQL
- Auth/Security: Session auth + RBAC + password hashing
- Frontend: Jinja2 templates + static assets

## Project Structure

```text
BBMS/
|- app.py                     # Main Flask application + routes
|- main.py                    # ASGI entrypoint for production
|- user_routes.py             # User/role/dashboard admin routes
|- transaction_routes.py      # Request approval/rejection APIs
|- transaction_lock_handler.py# Concurrency-safe inventory logic
|- db_config.py               # DB config from environment variables
|- schema.sql                 # Base schema and SQL procedures
|- templates/                 # Jinja HTML pages
|- static/                    # CSS/JS/uploads
|- requirements.txt
|- Procfile
```

## Prerequisites

- Python 3.10+
- MySQL Server 8+
- Git

## Local Setup

1. Clone the repository

```bash
git clone https://github.com/issacjefrin12/blood-bank-system.git
cd blood-bank-system
```

2. Create and activate a virtual environment

```bash
python -m venv venv
```

Windows (PowerShell):

```powershell
.\venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source venv/bin/activate
```

3. Install dependencies

```bash
pip install -r requirements.txt
```

4. Configure environment variables

Create a `.env` file in the project root:

```env
# App
BBMS_SECRET_KEY=change-this-in-production
BBMS_SESSION_COOKIE_SECURE=false
BBMS_MAX_UPLOAD_MB=5
BBMS_AUTO_INIT_DB=true

# Database (Option A: explicit fields)
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=blood_bank_db

# Database (Option B: single URL)
# DB_URL=mysql://root:your_mysql_password@localhost:3306/blood_bank_db

# Seed/default account passwords used during bootstrap
BBMS_ADMIN_PASSWORD=admin123
BBMS_STAFF_PASSWORD=staff123
```

5. Run the app (development)

```bash
python app.py
```

App URL: `http://localhost:5000`

## Production/Cloud Run

This project includes a `Procfile`:

```text
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

For platforms like Render/Railway/Heroku-style deploys:

- Set required DB environment variables.
- Keep `BBMS_AUTO_INIT_DB=true` if you want schema/bootstrap checks on startup.
- Ensure `BBMS_SECRET_KEY` is strong and unique.

## Default Login Notes

On first run, the app seeds default operational users (if missing). Update these credentials immediately in real deployments:

- Admin username: `admin`
- Admin password: value of `BBMS_ADMIN_PASSWORD` (default: `admin123`)
- Staff username: `staff`
- Staff password: value of `BBMS_STAFF_PASSWORD` (default: `staff123`)

## Key Routes

- `GET /` - Landing page / redirects to dashboard when logged in
- `GET|POST /login` - Authentication
- `GET /admin/dashboard` - Role-based dashboard
- `GET /donors` - Donor listing and filters
- `GET /inventory` - Inventory view
- `GET /requests` - Blood request management
- `GET /healthz` - Health check

## Security Checklist Before Sharing

- Never commit `.env` or DB credentials
- Rotate default passwords
- Set `BBMS_SESSION_COOKIE_SECURE=true` in HTTPS deployments
- Use a strong `BBMS_SECRET_KEY`

## Troubleshooting

- MySQL connection errors:
  - Verify `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
  - Confirm MySQL service is running and reachable
- Cloud error about localhost DB:
  - Set remote DB host values (`DB_HOST`/`DB_PORT`) for cloud runtime
- Missing tables:
  - Keep `BBMS_AUTO_INIT_DB=true` or run `schema.sql` manually

## Screenshots of Red Lifeline

<img width="1919" height="1025" alt="Screenshot 2026-03-18 190801" src="https://github.com/user-attachments/assets/26c2257c-ab11-4254-82aa-9f72ddca8e32" />
<img width="1919" height="1031" alt="Screenshot 2026-03-18 190529" src="https://github.com/user-attachments/assets/1e040352-9821-47d2-8846-2d6ab40faa31" />


## Developed By

Jefrin
