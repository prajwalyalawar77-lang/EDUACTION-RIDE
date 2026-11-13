import os, re, secrets, json
from datetime import date, datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort
from werkzeug.security import generate_password_hash, check_password_hash
from database import q, init_db, VILLAGES, COLLEGES, road_km
import ai_engine as ai

app = Flask(__name__)
app.config.update(SECRET_KEY=os.environ.get("SECRET_KEY", secrets.token_hex(16)), SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")))
init_db()
TABLE = {"student": "Students", "parent": "Parents", "admin": "Admins"}
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def csrf():
    session.setdefault("csrf", secrets.token_hex(16)); return session["csrf"]
app.jinja_env.globals.update(csrf=csrf, villages=list(VILLAGES), colleges=list(COLLEGES))

@app.before_request
def check_csrf():
    if request.method == "POST" and request.form.get("csrf") != session.get("csrf"): abort(400, "Invalid form token. Reload the page and try again.")

def login_required(*roles):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            if "role" not in session: flash("Log in to continue.", "warning"); return redirect(url_for("login"))
            if roles and session["role"] not in roles: abort(403)
            return f(*a, **k)
        return w
    return deco

@app.context_processor
def inject():
    n = 0
    if "role" in session: n = q("SELECT COUNT(*) c FROM Notifications WHERE user_role=? AND user_id=? AND is_read=0", (session["role"], session["uid"]), one=True)["c"]
    return {"unread": n, "crisis_on": q("SELECT 1 FROM Crisis_Event WHERE id=1 AND active=1", one=True) is not None}

def notify(role, uid, msg):
    if uid: q("INSERT INTO Notifications(user_role,user_id,message) VALUES(?,?,?)", (role, uid, msg), commit=True)

@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
def err(e): return render_template("error.html", e=e), e.code

# ---------- public / auth ----------
@app.route("/")
def index():
    s = {"students": q("SELECT COUNT(*) c FROM Students", one=True)["c"], "buses": q("SELECT COUNT(*) c FROM Buses", one=True)["c"],
         "cancelled": q("SELECT COUNT(*) c FROM Buses WHERE status='cancelled'", one=True)["c"],
         "vehicles": q("SELECT COUNT(*) c FROM Vehicles WHERE available=1 AND verified=1", one=True)["c"]}
    return render_template("index.html", s=s)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form; role = f.get("role"); name = f.get("name", "").strip(); email = f.get("email", "").strip().lower(); pw = f.get("password", "")
        if role not in ("student", "parent"): flash("Choose student or parent.", "danger")
        elif len(name) < 2 or not EMAIL.match(email) or len(pw) < 8: flash("Enter a name, a valid email and a password of at least 8 characters.", "danger")
        elif any(q(f"SELECT 1 FROM {t} WHERE email=?", (email,), one=True) for t in TABLE.values()): flash("That email is already registered.", "danger")
        elif role == "student":
            minor = 1 if f.get("minor") else 0; pe = f.get("parent_email", "").strip().lower()
            par = q("SELECT id FROM Parents WHERE email=?", (pe,), one=True) if pe else None
            if f.get("village") not in VILLAGES or f.get("college") not in COLLEGES: flash("Choose a village and college from the lists.", "danger")
            elif minor and not (par and f.get("consent")): flash("Students under 18 need a registered parent's email and parental consent.", "danger")
            else:
                q("INSERT INTO Students(name,email,password_hash,village,college,is_minor,parent_id,parent_consent) VALUES(?,?,?,?,?,?,?,?)",
                  (name, email, generate_password_hash(pw), f["village"], f["college"], minor, par["id"] if par else None, 1 if f.get("consent") else 0), commit=True)
                flash("Account created. Log in to plan journeys.", "success"); return redirect(url_for("login"))
        else:
            q("INSERT INTO Parents(name,email,phone,password_hash) VALUES(?,?,?,?)", (name, email, f.get("phone", "")[:15], generate_password_hash(pw)), commit=True)
            flash("Parent account created. Log in.", "success"); return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role = request.form.get("role"); email = request.form.get("email", "").strip().lower()
        if role in TABLE:
            u = q(f"SELECT * FROM {TABLE[role]} WHERE email=?", (email,), one=True)
            if u and check_password_hash(u["password_hash"], request.form.get("password", "")):
                session.clear(); session.update(role=role, uid=u["id"], name=u["name"]); return redirect(url_for("dashboard"))
        flash("Email, password or role is incorrect.", "danger")
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
def logout(): session.clear(); flash("You have been logged out.", "success"); return redirect(url_for("index"))

@app.route("/dashboard")
@login_required()
def dashboard():
    r, uid = session["role"], session["uid"]
    if r == "admin": return redirect(url_for("admin"))
    if r == "parent":
        kids = q("SELECT * FROM Students WHERE parent_id=? AND parent_consent=1", (uid,))
        reqs = q("""SELECT r.*, s.name sname, v.reg_no, v.vehicle_type FROM Transport_Requests r JOIN Students s ON s.id=r.student_id
                    LEFT JOIN Vehicles v ON v.id=r.vehicle_id WHERE s.parent_id=? AND s.parent_consent=1 ORDER BY r.id DESC""", (uid,))
        return render_template("parent_dashboard.html", kids=kids, reqs=reqs, notes=notes(r, uid))
    st = q("SELECT * FROM Students WHERE id=?", (uid,), one=True)
    reqs = q("""SELECT r.*, v.reg_no, v.vehicle_type FROM Transport_Requests r LEFT JOIN Vehicles v ON v.id=r.vehicle_id WHERE student_id=? ORDER BY r.id DESC""", (uid,))
    hist = q("SELECT * FROM Travel_History WHERE student_id=? ORDER BY id DESC LIMIT 20", (uid,))
    return render_template("student_dashboard.html", st=st, reqs=reqs, hist=hist, notes=notes(r, uid))

def notes(role, uid):
    n = q("SELECT * FROM Notifications WHERE user_role=? AND user_id=? ORDER BY id DESC LIMIT 15", (role, uid))
    q("UPDATE Notifications SET is_read=1 WHERE user_role=? AND user_id=?", (role, uid), commit=True); return n

@app.route("/profile", methods=["POST"])
@login_required("student")
def profile():
    v, c = request.form.get("village"), request.form.get("college")
    if v in VILLAGES and c in COLLEGES:
        q("UPDATE Students SET village=?,college=? WHERE id=?", (v, c, session["uid"]), commit=True); flash("Saved your daily route.", "success")
    else: flash("Choose a village and college from the lists.", "danger")
    return redirect(url_for("dashboard"))

# ---------- planner / emergency ----------
def parse_trip(f):
    v, c = f.get("village"), f.get("college")
    try: n = int(f.get("students", 1)); d = datetime.strptime(f.get("date", ""), "%Y-%m-%d").date(); t = datetime.strptime(f.get("time", ""), "%H:%M")
    except ValueError: return None, "Enter a valid date, time and number of students."
    if v not in VILLAGES or c not in COLLEGES: return None, "Choose a village and college from the lists."
    if not 1 <= n <= 60: return None, "Number of students must be between 1 and 60."
    return dict(village=v, college=c, n=n, date=d, time=t.strftime("%H:%M"), hour=t.hour), None

@app.route("/planner", methods=["GET", "POST"])
@login_required("student")
def planner():
    res = None
    if request.method == "POST":
        trip, e = parse_trip(request.form)
        if e: flash(e, "danger")
        else:
            info = ai.route_info(trip["village"], trip["college"])
            buses = q("""SELECT b.*, r.distance_km FROM Buses b JOIN Routes r ON r.id=b.route_id WHERE r.origin=? AND r.destination=? ORDER BY b.depart_time""", (trip["village"], trip["college"]))
            rows = []
            for b in buses:
                h, m = map(int, b["depart_time"].split(":")); arr = (h*60 + m + info["minutes"]) % 1440
                rows.append(dict(b, seats_left=b["capacity"]-b["seats_taken"], arrive=f"{arr//60:02d}:{arr%60:02d}", fare=round(b["distance_km"]*1.2*trip["n"])))
            running = [b for b in rows if b["status"] == "running"]
            seats = sum(b["seats_left"] for b in running)
            hist = q("SELECT AVG(students) a FROM Travel_History WHERE village=? AND college=?", (trip["village"], trip["college"]), one=True)["a"]
            others = q("SELECT COALESCE(SUM(num_students),0) c FROM Transport_Requests WHERE village=? AND college=? AND travel_date=?", (trip["village"], trip["college"], str(trip["date"])), one=True)["c"]
            demand = ai.predict_demand(trip["n"] + others, seats, trip["date"].weekday(), trip["hour"], hist)
            alt = demand["shortage"] > 0 or not any(b["seats_left"] >= trip["n"] for b in running)
            q("INSERT INTO Transport_Requests(student_id,village,college,travel_date,depart_time,num_students,kind,status) VALUES(?,?,?,?,?,?, 'journey','planned')",
              (session["uid"], trip["village"], trip["college"], str(trip["date"]), trip["time"], trip["n"]), commit=True)
            q("INSERT INTO Travel_History(student_id,village,college,travel_date,depart_time,students,mode) VALUES(?,?,?,?,?,?,?)",
              (session["uid"], trip["village"], trip["college"], str(trip["date"]), trip["time"], trip["n"], "bus (planned)"), commit=True)
            res = dict(trip=trip, info=info, buses=rows, demand=demand, alt=alt)
    st = q("SELECT village,college FROM Students WHERE id=?", (session["uid"],), one=True)
    return render_template("journey_planner.html", res=res, st=st, today=date.today())

@app.route("/emergency", methods=["GET", "POST"])
@login_required("student")
def emergency():
    res = None
    st = q("SELECT * FROM Students WHERE id=?", (session["uid"],), one=True)
    cancelled = q("""SELECT b.number, b.depart_time, b.status, r.origin, r.destination FROM Buses b JOIN Routes r ON r.id=b.route_id
                     WHERE b.status IN ('cancelled','delayed') AND r.origin=? AND r.destination=?""", (st["village"], st["college"]))
    if request.method == "POST":
        trip, e = parse_trip(request.form)
        if e: flash(e, "danger")
        else:
            others = q("""SELECT village, SUM(num_students) n FROM Transport_Requests WHERE college=? AND travel_date=? AND status IN ('pending','emergency')
                          AND village<>? GROUP BY village""", (trip["college"], str(trip["date"]), trip["village"]))
            nearby = [(o["village"], o["n"]) for o in others if road_km(VILLAGES[o["village"]], VILLAGES[trip["village"]]) < 40]
            opts = ai.match_vehicles(q("SELECT * FROM Vehicles"), trip["village"], trip["college"], trip["n"], nearby)
            res = dict(trip=trip, opts=opts, nearby=nearby)
    return render_template("emergency_ride.html", res=res, st=st, cancelled=cancelled, today=date.today())

@app.route("/emergency/request", methods=["POST"])
@login_required("student")
def emergency_request():
    trip, e = parse_trip(request.form)
    v = q("SELECT * FROM Vehicles WHERE id=?", (request.form.get("vehicle_id"),), one=True)
    if e or not v: flash(e or "Vehicle not found.", "danger"); return redirect(url_for("emergency"))
    if not v["verified"]: flash("Only verified vehicles can be requested.", "danger"); return redirect(url_for("emergency"))
    info = ai.route_info(trip["village"], trip["college"]); fare = round(info["km"] * v["rate_per_km"])
    q("INSERT INTO Transport_Requests(student_id,vehicle_id,village,college,travel_date,depart_time,num_students,kind,est_fare,status) VALUES(?,?,?,?,?,?,?, 'emergency',?, 'pending')",
      (session["uid"], v["id"], trip["village"], trip["college"], str(trip["date"]), trip["time"], trip["n"], fare), commit=True)
    notify("student", session["uid"], f"Ride request sent for {v['reg_no']}. It is not confirmed until an admin approves it.")
    flash("Request submitted. Waiting for admin approval.", "success"); return redirect(url_for("dashboard"))

# ---------- map / analytics ----------
# ---------- exam-day crisis ----------
def restore_buses():
    ev = q("SELECT broken FROM Crisis_Event WHERE id=1", one=True)
    for i in (json.loads(ev["broken"]) if ev and ev["broken"] else []): q("UPDATE Buses SET status='running' WHERE id=?", (i,), commit=True)

@app.route("/crisis")
@login_required()
def crisis():
    ev = q("SELECT * FROM Crisis_Event WHERE id=1", one=True); plan = broken = None
    if ev and ev["active"]:
        buses = [dict(b) for b in q("SELECT b.id,b.number,b.status,b.capacity-b.seats_taken seats_left,r.origin,r.destination FROM Buses b JOIN Routes r ON r.id=b.route_id")]
        blocked = (ev["blocked_a"], ev["blocked_b"]) if ev["blocked_a"] else None
        plan = ai.crisis_plan([dict(c) for c in q("SELECT * FROM Crisis_Demand ORDER BY id")], buses, [dict(v) for v in q("SELECT * FROM Vehicles")], blocked, ev["surge_pct"])
        ids = json.loads(ev["broken"] or "[]"); broken = [b["number"] for b in buses if b["id"] in ids]
    return render_template("crisis.html", ev=ev, plan=plan, broken=broken, cohorts=q("SELECT * FROM Crisis_Demand ORDER BY id"))

@app.route("/crisis/activate", methods=["POST"])
@login_required("admin")
def crisis_activate():
    f = request.form; a, b = f.get("block_a", ""), f.get("block_b", "")
    try: surge, nb = int(f["surge"]), int(f["broken"])
    except (KeyError, ValueError): flash("Enter whole numbers for surge and broken buses.", "danger"); return redirect(url_for("crisis"))
    if not (0 <= surge <= 200 and 0 <= nb <= 5) or (a and (a == b or a not in VILLAGES or b not in VILLAGES)):
        flash("Surge must be 0-200%, broken buses 0-5, and the blocked road needs two different villages.", "danger"); return redirect(url_for("crisis"))
    restore_buses()
    ids = [r["id"] for r in q("SELECT id FROM Buses WHERE status='running' ORDER BY capacity-seats_taken DESC LIMIT ?", (nb,))]
    for i in ids: q("UPDATE Buses SET status='cancelled' WHERE id=?", (i,), commit=True)
    q("INSERT OR REPLACE INTO Crisis_Event(id,active,surge_pct,blocked_a,blocked_b,broken,started_at) VALUES(1,1,?,?,?,?,?)",
      (surge, a or None, b or None, json.dumps(ids), datetime.now().strftime("%Y-%m-%d %H:%M")), commit=True)
    vill = {r["origin"] for i in ids for r in q("SELECT r.origin FROM Buses b JOIN Routes r ON r.id=b.route_id WHERE b.id=?", (i,))} | {x for x in (a, b) if x}
    for v in vill:
        for s in q("SELECT id,parent_id FROM Students WHERE village=?", (v,)):
            notify("student", s["id"], "Exam-day crisis: your route is disrupted. Open Crisis plan to see your reallocated ride."); notify("parent", s["parent_id"], "Exam-day crisis: your child's route is disrupted. A reallocated ride is being planned.")
    flash("Crisis activated. Buses taken out of service and the plan is recalculated.", "danger"); return redirect(url_for("crisis"))

@app.route("/crisis/reset", methods=["POST"])
@login_required("admin")
def crisis_reset():
    restore_buses(); q("UPDATE Crisis_Event SET active=0 WHERE id=1", commit=True); flash("Crisis ended. Buses restored to service.", "success"); return redirect(url_for("crisis"))

@app.route("/crisis/cohort", methods=["POST"])
@login_required("admin")
def crisis_cohort():
    f = request.form
    if f.get("action") == "delete": q("DELETE FROM Crisis_Demand WHERE id=?", (f.get("id"),), commit=True); flash("Group removed.", "success")
    else:
        try:
            n = int(f["students"]); ex = int(f["exam_min"]) if f.get("exam_min") else None
            if f["village"] not in VILLAGES or f["college"] not in COLLEGES or not 1 <= n <= 500 or (ex is not None and not 1 <= ex <= 600): raise ValueError
            q("INSERT INTO Crisis_Demand(village,college,students,exam_min) VALUES(?,?,?,?)", (f["village"], f["college"], n, ex), commit=True); flash("Student group added. Plan updated.", "success")
        except (KeyError, ValueError): flash("Check the group: valid village, college, 1-500 students, exam minutes 1-600 or blank.", "danger")
    return redirect(url_for("crisis"))

@app.route("/sw.js")
def sw(): return app.send_static_file("sw.js"), 200, {"Content-Type": "application/javascript", "Service-Worker-Allowed": "/"}

@app.route("/tracking")
def tracking(): return render_template("bus_tracking.html")

@app.route("/api/map")
def api_map():
    buses = q("""SELECT b.number,b.status,b.depart_time,r.name,r.origin,r.destination FROM Buses b JOIN Routes r ON r.id=b.route_id""")
    out = []
    for b in buses:
        a, c = VILLAGES[b["origin"]], COLLEGES[b["destination"]]
        # SIMULATED position: interpolate along the route based on clock time. Not real GPS.
        h, m = map(int, b["depart_time"].split(":")); prog = min(1, max(0, ((datetime.now().hour*60 + datetime.now().minute) - (h*60+m)) / 60)) if b["status"] == "running" else 0
        out.append(dict(b, a=a, c=c, pos=[a[0]+(c[0]-a[0])*prog, a[1]+(c[1]-a[1])*prog], simulated=True))
    vehicles = q("SELECT reg_no,vehicle_type,seats,verified,lat,lng FROM Vehicles WHERE available=1")
    ev = q("SELECT blocked_a,blocked_b FROM Crisis_Event WHERE id=1 AND active=1", one=True)
    blocked = [VILLAGES[ev["blocked_a"]], VILLAGES[ev["blocked_b"]]] if ev and ev["blocked_a"] else None
    return jsonify(blocked=blocked, villages=VILLAGES, colleges=COLLEGES, buses=out, vehicles=[dict(v) for v in vehicles], note="All positions are simulated demonstration data, not live GPS.")

@app.route("/analytics")
@login_required("admin", "student", "parent")
def analytics(): return render_template("analytics.html")

@app.route("/api/analytics")
@login_required()
def api_analytics():
    by_v = q("SELECT village, SUM(num_students) n FROM Transport_Requests GROUP BY village")
    by_s = q("SELECT status, COUNT(*) n FROM Transport_Requests GROUP BY status")
    return jsonify(villages=[dict(r) for r in by_v], statuses=[dict(r) for r in by_s])

# ---------- admin ----------
@app.route("/admin")
@login_required("admin")
def admin():
    c = lambda s: q(s, one=True)["c"]
    stats = dict(students=c("SELECT COUNT(*) c FROM Students"), buses=c("SELECT COUNT(*) c FROM Buses"), vehicles=c("SELECT COUNT(*) c FROM Vehicles WHERE available=1 AND verified=1"),
                 active=c("SELECT COUNT(*) c FROM Transport_Requests WHERE status='pending'"), done=c("SELECT COUNT(*) c FROM Transport_Requests WHERE status='completed'"),
                 cancelled=c("SELECT COUNT(*) c FROM Buses WHERE status='cancelled'"), unserved=c("SELECT COUNT(*) c FROM Transport_Requests WHERE status='rejected'"))
    term = request.args.get("search", "").strip(); status = request.args.get("status", "")
    sql = """SELECT r.*, s.name sname, v.reg_no FROM Transport_Requests r JOIN Students s ON s.id=r.student_id LEFT JOIN Vehicles v ON v.id=r.vehicle_id
             WHERE r.kind='emergency' AND (s.name LIKE ? OR r.village LIKE ?)""" + (" AND r.status=?" if status else "") + " ORDER BY r.id DESC"
    args = (f"%{term}%", f"%{term}%") + ((status,) if status else ())
    pred = ai.predict_demand(q("SELECT COALESCE(SUM(num_students),0) c FROM Transport_Requests WHERE status IN ('pending','planned')", one=True)["c"],
                             q("SELECT COALESCE(SUM(capacity-seats_taken),0) c FROM Buses WHERE status='running'", one=True)["c"])
    return render_template("admin_dashboard.html", stats=stats, pred=pred, reqs=q(sql, args), routes=q("SELECT * FROM Routes"), term=term, status=status,
                           buses=q("SELECT b.*, r.name rname FROM Buses b JOIN Routes r ON r.id=b.route_id ORDER BY b.id"),
                           providers=q("SELECT * FROM Transport_Providers"), vehicles=q("SELECT v.*, p.name pname FROM Vehicles v JOIN Transport_Providers p ON p.id=v.provider_id"),
                           stops=q("SELECT s.*, r.name rname FROM Bus_Stops s JOIN Routes r ON r.id=s.route_id ORDER BY r.id, s.seq"))

def back(): return redirect(url_for("admin"))

@app.route("/admin/bus", methods=["POST"])
@login_required("admin")
def admin_bus():
    f = request.form; act = f.get("action")
    try:
        if act == "add":
            q("INSERT INTO Buses(number,route_id,depart_time,capacity,seats_taken,status) VALUES(?,?,?,?,?,?)",
              (f["number"].strip(), int(f["route_id"]), f["depart_time"], int(f["capacity"]), 0, "running"), commit=True)
        elif act == "update":
            if f["status"] not in ("running", "cancelled", "delayed"): raise ValueError
            q("UPDATE Buses SET status=?, seats_taken=? WHERE id=?", (f["status"], int(f["seats_taken"]), int(f["id"])), commit=True)
            if f["status"] != "running":
                b = q("SELECT r.origin FROM Buses b JOIN Routes r ON r.id=b.route_id WHERE b.id=?", (f["id"],), one=True)
                for s in q("SELECT id,parent_id FROM Students WHERE village=?", (b["origin"],)):
                    notify("student", s["id"], f"A bus on your route is {f['status']}. Use Find my alternative ride."); notify("parent", s["parent_id"], f"A bus on your child's route is {f['status']}.")
        elif act == "delete": q("DELETE FROM Buses WHERE id=?", (int(f["id"]),), commit=True)
        flash("Bus saved." if act != "delete" else "Bus deleted.", "success")
    except Exception: flash("Could not save the bus. Check the values (bus number must be unique).", "danger")
    return back()

@app.route("/admin/provider", methods=["POST"])
@login_required("admin")
def admin_provider():
    f = request.form
    try:
        if f["action"] == "provider": q("INSERT INTO Transport_Providers(name,phone,base_village) VALUES(?,?,?)", (f["name"].strip(), f["phone"].strip(), f["village"]), commit=True)
        elif f["action"] == "vehicle":
            la, ln = VILLAGES[f["village"]]
            q("INSERT INTO Vehicles(provider_id,reg_no,vehicle_type,seats,rate_per_km,lat,lng) VALUES(?,?,?,?,?,?,?)",
              (int(f["provider_id"]), f["reg_no"].strip(), f["vehicle_type"], int(f["seats"]), float(f["rate"]), la, ln), commit=True)
        elif f["action"] == "verify":
            q("UPDATE Vehicles SET verified=? WHERE id=?", (1 if f["value"] == "1" else 0, int(f["id"])), commit=True)
        elif f["action"] == "toggle": q("UPDATE Vehicles SET available=1-available WHERE id=?", (int(f["id"]),), commit=True)
        flash("Saved.", "success")
    except Exception: flash("Could not save. Check the values (registration number must be unique).", "danger")
    return back()

@app.route("/admin/route", methods=["POST"])
@login_required("admin")
def admin_route():
    f = request.form
    try:
        if f["action"] == "add":
            o, d = f["origin"], f["destination"]; km = road_km(VILLAGES[o], COLLEGES[d])
            rid = q("INSERT INTO Routes(name,origin,destination,distance_km) VALUES(?,?,?,?)", (f"{o} to {d.split(',')[0]}", o, d, km), commit=True)
            q("INSERT INTO Bus_Stops(route_id,name,lat,lng,seq) VALUES(?,?,?,?,1)", (rid, o+" Stop", *VILLAGES[o]), commit=True)
            q("INSERT INTO Bus_Stops(route_id,name,lat,lng,seq) VALUES(?,?,?,?,2)", (rid, d+" Gate", *COLLEGES[d]), commit=True)
        elif f["action"] == "delete": q("DELETE FROM Routes WHERE id=?", (int(f["id"]),), commit=True)
        elif f["action"] == "stop":
            q("INSERT INTO Bus_Stops(route_id,name,lat,lng,seq) VALUES(?,?,?,?,?)", (int(f["route_id"]), f["name"].strip(), float(f["lat"]), float(f["lng"]), int(f["seq"])), commit=True)
        elif f["action"] == "delstop": q("DELETE FROM Bus_Stops WHERE id=?", (int(f["id"]),), commit=True)
        flash("Saved.", "success")
    except Exception: flash("Could not save. A route needs a valid village and college; delete buses on a route first.", "danger")
    return back()

@app.route("/admin/request", methods=["POST"])
@login_required("admin")
def admin_request():
    rid, act = request.form.get("id"), request.form.get("action")
    r = q("SELECT r.*, s.parent_id FROM Transport_Requests r JOIN Students s ON s.id=r.student_id WHERE r.id=?", (rid,), one=True)
    status = {"approve": "approved", "reject": "rejected", "complete": "completed"}.get(act)
    if not r or not status: abort(400)
    q("UPDATE Transport_Requests SET status=? WHERE id=?", (status, rid), commit=True)
    v = q("SELECT reg_no FROM Vehicles WHERE id=?", (r["vehicle_id"],), one=True)
    msg = {"approved": f"Your ride is confirmed with vehicle {v['reg_no'] if v else ''} on {r['travel_date']} at {r['depart_time']}.",
           "rejected": "Your ride request was not approved. Please request another vehicle.", "completed": "Journey completed: arrived at college."}[status]
    notify("student", r["student_id"], msg); notify("parent", r["parent_id"], "Update on your child's ride: " + msg)
    flash(f"Request {status}.", "success"); return back()

if __name__ == "__main__": app.run(debug=True)
