# CampusPro — Final-Year Project Management System

CampusPro is a Flask + MySQL web application with student, faculty, and administrator dashboards.

## Requirements
- Python 3.10 or newer
- MySQL Server (or compatible MariaDB)
- pip

## Quick Setup
1. Extract zip contents into a folder.
2. Create `.env` file based on `.env.example`.
3. Create & activate a virtual environment and install requirements:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. Run app:
   ```bash
   python app.py
   ```
5. Access app at `http://127.0.0.1:5000`

Default Admin Login:
- Email: `admin@campuspro.local`
- Password: `Admin@123`
