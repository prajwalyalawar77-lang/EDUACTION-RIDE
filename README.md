Education Ride

No Bus, No Barrier. Every Student Deserves a Ride.

An AI-assisted rural student transportation platform. It shows bus availability, predicts demand, finds verified alternative rides when a government bus fails, groups students into shared rides, and re-plans everything during an exam-day crisis.

All seeded records (students, buses, vehicles, villages, exam groups) are demonstration data, flagged is_demo=1 in the database.

1. Features
Area	What it does
Student portal	Register, log in, save a daily route, plan journeys, request alternative rides, view history and notifications
Journey planner	Lists buses with departure, estimated arrival, seats left and fare, plus a demand prediction
Demand prediction	Compares students to seats and explains the shortage (rule-based)
Emergency ride finder	Ranks verified vehicles by distance, seats and fare; request needs admin approval
Shared ride matching	Groups students from nearby villages heading to the same college into one vehicle
Live map	Leaflet + OpenStreetMap; villages, colleges, routes, vehicles, closed roads
Parent portal	Ride details and alerts, only for students who gave parental consent
Admin dashboard	Counts, request approval, bus / route / stop / provider / vehicle management
Crisis mode	Bus breakdowns, demand surge and a flooded road; exam-first reallocation with before/after numbers
Offline support	Installable app (PWA), cached pages, low-bandwidth toggle
2. Tech stack

Python 3 · Flask · SQLite · Bootstrap 5 · Leaflet.js · OpenStreetMap · Chart.js · Gunicorn (Render)

3. Project structure
EDUCATION-RIDE/
├── app.py            # routes, auth, roles, admin and crisis actions
├── database.py       # schema, demo data, distance helpers
├── ai_engine.py      # demand prediction, vehicle matching, crisis planner
├── requirements.txt
├── Procfile
├── templates/        # index, login, register, dashboards, planner,
│                     # emergency_ride, bus_tracking, analytics, crisis
├── static/           # css, js, manifest.json, sw.js, images
└── tests/test_app.py
4. Run locally (Windows PowerShell)
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py

Open http://127.0.0.1:5000. Run dir first and confirm app.py and requirements.txt are in the current folder.

Demo logins (password demo1234): student@demo.local, parent@demo.local, admin@demo.local.

Tests: pip install pytest then pytest tests.

5. Crisis mode (Exam-Day Crisis)

Log in as admin, open Crisis plan, click Activate crisis. Defaults: 2 buses broken, 40% demand surge, Maddur Village to Channapatna Outskirts road closed.

How the planner works:

Demand per group is multiplied by the surge factor.
Groups are sorted by time until their exam (most urgent first).
Each group uses surviving buses on its route first, then the smallest verified van that fits.
A vehicle is used only if its arrival fits before the exam minus a 15-minute buffer.
Villages on the closed road get a detour route via the best other village.
The page compares seated students before (surviving buses only) and after the plan, and recommends extra vehicles for anyone still stranded.

Assumptions: vehicles dispatch immediately, 35 km/h average speed, 10 minutes boarding, one van serves one group, distances are straight-line x 1.3.

6. Prompts that produced accurate results

Strong prompts name the role, the exact output, the rules, and what must not be claimed. Reuse these.

6.1 Master build prompt
ROLE: Senior full-stack engineer (Flask, SQLite, Leaflet) and UI designer.
TASK: Build "Education Ride", a rural student transport web app that runs locally.
STACK: Flask, SQLite, Bootstrap 5, Leaflet + OpenStreetMap, Chart.js.
ROLES: student, parent, admin, each with its own dashboard and access limits.
MUST WORK (no decorative buttons): registration, login/logout, journey planner
saved to the database, emergency ride request needing admin approval, bus CRUD,
request approve/reject, notifications, map, analytics.
AI PARTS: demand prediction, vehicle matching, route estimate, each with a
plain-language explanation. If no training data exists, use explainable rules.
RULES:
- Do NOT claim a model was trained. Label rule-based logic as rule-based.
- Label simulated GPS and demo data clearly.
- Hash passwords, check roles server-side, use parameterised SQL, add CSRF tokens.
- Students under 18 need parental consent before a parent sees any data.
OUTPUT: create the files, run the app, run tests, fix every error, then list
what is complete and what is not.
6.2 Crisis adaptation prompt (Prompt Battle: Exam Day Crisis)
CONTEXT: Existing Flask app "Education Ride" (files: app.py, database.py,
ai_engine.py, templates/). Do not rebuild it; extend it.
SCENARIO: Exam day. Two buses break down, demand rises 40%, one road between
two villages is flooded, several students have exams within two hours.
ADD: a Crisis page where the admin sets (a) number of broken buses,
(b) surge percentage, (c) the blocked road (village A to village B).
ALGORITHM (explainable, not ML):
1. Multiply each student group by the surge factor.
2. Sort groups by minutes until exam, most urgent first.
3. Fill from surviving buses on the route, then the smallest verified van that fits.
4. Accept a vehicle only if arrival time <= exam time - 15 min buffer.
5. For villages on the blocked road, compute a detour via the best other village.
6. Report seated vs stranded, before vs after the plan, and extra vehicles needed.
ALSO: notify affected students and parents, draw the closed road on the map,
let the admin add or remove student groups and re-plan instantly.
CONSTRAINTS: admin-only controls, input validation, tests, and state every
assumption on the page. Report honestly if students remain stranded.
6.3 Debugging prompt
My Flask app fails. Here is the full error text: <paste everything>.
Folder I am in: <output of dir>. Python version: <python --version>.
Explain the cause in one sentence, give the exact fix as numbered steps for
Windows PowerShell, and tell me how to confirm it worked.
6.4 Accuracy guardrails (add to any prompt)
- Verify before claiming: run the app and the tests, then report real results.
- Never invent data sources, trained models, live GPS or sent SMS messages.
- Mark all sample data as demonstration data.
- If something is unfinished, say so and list it.
- Give numbers from the running system, not estimates from memory.
7. Deploy
Push to GitHub from the folder that contains app.py (the repo root must show app.py and requirements.txt):
   git init
   git add .
   git commit -m "Education Ride"
   git branch -M main
   git remote add origin https://github.com/<user>/<repo>.git
   git push -u origin main
Render: New > Web Service > connect the repo.
Language: Python 3
Build: pip install -r requirements.txt
Start: gunicorn app:app
Environment: SECRET_KEY (long random text), RENDER=1, PYTHON_VERSION=3.12.3
Free-tier storage is wiped on redeploy. For persistence, add a disk at /data and set DB_PATH=/data/education_ride.db.
8. Honest limitations
Demand prediction, matching and crisis planning are rule-based; no model is trained. scikit-learn is reserved for a future model once real travel records exist.
Map positions are simulated from schedules, not GPS. Distances are estimates.
SMS and IVR are not connected; notifications are in-app only.
PostgreSQL is not implemented; SQLite is used.
One van serves one group in crisis mode, so some seats stay empty.
Not built: password reset, rate limiting, live vehicle tracking hardware.
