# Education Ride
No Bus, No Barrier. Every Student Deserves a Ride.

Flask + SQLite app for rural student transport: journey planner, rule-based demand prediction, emergency ride finder with shared-ride matching, Leaflet map, parent portal, admin dashboard, PWA.

## Run locally
    pip install -r requirements.txt
    python app.py          # http://127.0.0.1:5000
    pip install pytest && pytest tests

Demo logins (password `demo1234`): student@demo.local, parent@demo.local, admin@demo.local. All seeded records are marked demo (`is_demo=1`).

## Honest limitations
- Demand prediction and matching are explainable **rule-based** engines. No ML model is trained; scikit-learn is listed for a future model once real travel history exists.
- Map positions are **simulated** from schedules, not GPS. Coordinates and distances are approximate (straight line x 1.3).
- SMS/IVR is not connected. Add a provider (e.g. Twilio) behind `notify()` in `app.py`; until then notifications are in-app only.
- Not built yet: a PostgreSQL backend, rate limiting, password reset, per-student ride completion tracking.

## Deploy
1. `git init && git add . && git commit -m "Education Ride" && git remote add origin <repo-url> && git push -u origin main`
2. On Render: New > Web Service > connect the repo. Build: `pip install -r requirements.txt`. Start: `gunicorn app:app`.
3. Environment: `SECRET_KEY` (long random string), `RENDER=1`.
4. SQLite on Render's free tier is wiped on redeploy. Add a persistent disk mounted at `/data` and set `DB_PATH=/data/education_ride.db`, or move to Render PostgreSQL (requires porting `database.py`).
