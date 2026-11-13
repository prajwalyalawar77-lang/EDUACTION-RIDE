import os, sqlite3, math
from werkzeug.security import generate_password_hash

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "education_ride.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS Admins(id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, password_hash TEXT, is_demo INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS Parents(id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, phone TEXT, password_hash TEXT, is_demo INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS Students(id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, password_hash TEXT, village TEXT, college TEXT,
  is_minor INTEGER DEFAULT 1, parent_id INTEGER REFERENCES Parents(id), parent_consent INTEGER DEFAULT 0, is_demo INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS Routes(id INTEGER PRIMARY KEY, name TEXT, origin TEXT, destination TEXT, distance_km REAL, is_demo INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS Bus_Stops(id INTEGER PRIMARY KEY, route_id INTEGER REFERENCES Routes(id) ON DELETE CASCADE, name TEXT, lat REAL, lng REAL, seq INTEGER);
CREATE TABLE IF NOT EXISTS Buses(id INTEGER PRIMARY KEY, number TEXT UNIQUE, route_id INTEGER REFERENCES Routes(id), depart_time TEXT, capacity INTEGER,
  seats_taken INTEGER DEFAULT 0, status TEXT DEFAULT 'running', is_demo INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS Transport_Providers(id INTEGER PRIMARY KEY, name TEXT, phone TEXT, base_village TEXT, verified INTEGER DEFAULT 0, is_demo INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS Vehicles(id INTEGER PRIMARY KEY, provider_id INTEGER REFERENCES Transport_Providers(id) ON DELETE CASCADE, reg_no TEXT UNIQUE,
  vehicle_type TEXT, seats INTEGER, rate_per_km REAL, available INTEGER DEFAULT 1, verified INTEGER DEFAULT 0, lat REAL, lng REAL, is_demo INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS Transport_Requests(id INTEGER PRIMARY KEY, student_id INTEGER REFERENCES Students(id), vehicle_id INTEGER REFERENCES Vehicles(id),
  village TEXT, college TEXT, travel_date TEXT, depart_time TEXT, num_students INTEGER, kind TEXT DEFAULT 'journey', est_fare REAL, status TEXT DEFAULT 'pending',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS Notifications(id INTEGER PRIMARY KEY, user_role TEXT, user_id INTEGER, message TEXT, is_read INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS Crisis_Demand(id INTEGER PRIMARY KEY, village TEXT, college TEXT, students INTEGER, exam_min INTEGER, is_demo INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS Crisis_Event(id INTEGER PRIMARY KEY, active INTEGER DEFAULT 0, surge_pct INTEGER, blocked_a TEXT, blocked_b TEXT, broken TEXT, started_at TEXT);
CREATE TABLE IF NOT EXISTS Travel_History(id INTEGER PRIMARY KEY, student_id INTEGER REFERENCES Students(id), village TEXT, college TEXT, travel_date TEXT,
  depart_time TEXT, students INTEGER, mode TEXT);
"""

# Approximate coordinates, demonstration only.
VILLAGES = {"Hosahalli": (13.28, 77.62), "Kanakapura Rural": (12.55, 77.42), "Maddur Village": (12.58, 77.05),
            "Channapatna Outskirts": (12.65, 77.21), "Doddaballapur Village": (13.30, 77.54), "Magadi Village": (12.96, 77.22)}
COLLEGES = {"Govt First Grade College, Ramanagara": (12.72, 77.28), "Govt Polytechnic, Tumakuru": (13.34, 77.10),
            "Bangalore University Campus": (12.94, 77.50)}

def haversine(a, b):
    r = 6371; p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(h))

def road_km(a, b):  # straight line x 1.3 road factor (estimate)
    return round(haversine(a, b) * 1.3, 1)

def get_db():
    c = sqlite3.connect(DB_PATH); c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); return c

def q(sql, args=(), one=False, commit=False):
    c = get_db()
    try:
        cur = c.execute(sql, args)
        if commit: c.commit(); return cur.lastrowid
        rows = cur.fetchall(); return (rows[0] if rows else None) if one else rows
    finally:
        c.close()

def init_db(seed=True):
    c = get_db(); c.executescript(SCHEMA); c.commit()
    if seed and not c.execute("SELECT 1 FROM Admins").fetchone():
        pw = generate_password_hash("demo1234")
        c.execute("INSERT INTO Admins(name,email,password_hash,is_demo) VALUES('Demo Admin','admin@demo.local',?,1)", (pw,))
        c.execute("INSERT INTO Parents(name,email,phone,password_hash,is_demo) VALUES('Demo Parent','parent@demo.local','0000000000',?,1)", (pw,))
        c.execute("INSERT INTO Students(name,email,password_hash,village,college,is_minor,parent_id,parent_consent,is_demo) VALUES('Demo Student','student@demo.local',?,?,?,1,1,1,1)",
                  (pw, "Hosahalli", "Bangalore University Campus"))
        for v, col in [("Hosahalli", "Bangalore University Campus"), ("Kanakapura Rural", "Bangalore University Campus"),
                       ("Maddur Village", "Govt First Grade College, Ramanagara"), ("Channapatna Outskirts", "Govt First Grade College, Ramanagara")]:
            d = road_km(VILLAGES[v], COLLEGES[col])
            rid = c.execute("INSERT INTO Routes(name,origin,destination,distance_km,is_demo) VALUES(?,?,?,?,1)", (f"{v} to {col.split(',')[0]}", v, col, d)).lastrowid
            c.execute("INSERT INTO Bus_Stops(route_id,name,lat,lng,seq) VALUES(?,?,?,?,1)", (rid, v+" Stop", *VILLAGES[v]))
            c.execute("INSERT INTO Bus_Stops(route_id,name,lat,lng,seq) VALUES(?,?,?,?,2)", (rid, col+" Gate", *COLLEGES[col]))
            for i, (t, cap, taken, st) in enumerate([("07:00", 50, 48 if i_ok(v) else 20, "running"), ("08:30", 50, 10, "cancelled" if v == "Maddur Village" else "running")]):
                c.execute("INSERT INTO Buses(number,route_id,depart_time,capacity,seats_taken,status,is_demo) VALUES(?,?,?,?,?,?,1)",
                          (f"KA-DEMO-{rid}{i}", rid, t, cap, taken, st))
        c.execute("INSERT INTO Transport_Providers(name,phone,base_village,verified,is_demo) VALUES('Demo Village Transport Co-op','0000000001','Hosahalli',1,1)")
        c.execute("INSERT INTO Transport_Providers(name,phone,base_village,verified,is_demo) VALUES('Demo Unverified Operator','0000000002','Magadi Village',0,1)")
        for pid, reg, vt, seats, rate, ver, vil in [(1, "KA-01-DEMO-1001", "Shared van", 10, 9, 1, "Hosahalli"), (1, "KA-01-DEMO-1002", "Mini-bus", 24, 7, 1, "Kanakapura Rural"),
                                                   (1, "KA-01-DEMO-1003", "Shared van", 8, 10, 1, "Maddur Village"), (2, "KA-01-DEMO-2001", "Shared van", 10, 8, 0, "Magadi Village")]:
            la, ln = VILLAGES[vil]
            c.execute("INSERT INTO Vehicles(provider_id,reg_no,vehicle_type,seats,rate_per_km,verified,lat,lng,is_demo) VALUES(?,?,?,?,?,?,?,?,1)", (pid, reg, vt, seats, rate, ver, la, ln))
        c.commit()
    if seed and not c.execute("SELECT 1 FROM Crisis_Demand").fetchone():
        B, R, P = "Bangalore University Campus", "Govt First Grade College, Ramanagara", "Govt Polytechnic, Tumakuru"
        for v, col, n, ex in [("Hosahalli", B, 30, 130), ("Kanakapura Rural", B, 25, 150), ("Maddur Village", R, 28, 210),
                              ("Channapatna Outskirts", R, 20, 180), ("Doddaballapur Village", P, 15, 140), ("Magadi Village", B, 12, None)]:
            c.execute("INSERT INTO Crisis_Demand(village,college,students,exam_min,is_demo) VALUES(?,?,?,?,1)", (v, col, n, ex))
        c.commit()
    c.close()

def i_ok(v): return v == "Hosahalli"
