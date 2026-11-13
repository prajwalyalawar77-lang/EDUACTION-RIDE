import os, re, tempfile, sys
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app
import ai_engine as ai

def tok(c, url="/login"): return re.search(r'name="csrf" value="(\w+)"', c.get(url).get_data(as_text=True)).group(1)
def login(c, role, email):
    return c.post("/login", data=dict(csrf=tok(c), role=role, email=email, password="demo1234"), follow_redirects=True)

def test_demand_example():
    d = ai.predict_demand(120, 80); assert d["shortage"] == 40 and d["level"] == "HIGH" and d["extra_vehicles"] == 4

def test_access_control():
    c = app.test_client(); assert c.get("/admin").status_code == 302
    login(c, "student", "student@demo.local"); assert c.get("/admin").status_code == 403

def test_register_and_login():
    c = app.test_client()
    r = c.post("/register", data=dict(csrf=tok(c, "/register"), role="student", name="Test", email="t@x.com", password="longpass1", village="Hosahalli", college="Bangalore University Campus", minor="on"), follow_redirects=True)
    assert b"under 18" in r.data  # minor without parent consent is rejected
    r = c.post("/register", data=dict(csrf=tok(c, "/register"), role="student", name="Test", email="t@x.com", password="longpass1", village="Hosahalli", college="Bangalore University Campus", minor="on", parent_email="parent@demo.local", consent="on"), follow_redirects=True)
    assert b"Account created" in r.data

def test_student_flow():
    c = app.test_client(); assert b"Hello, Demo Student" in login(c, "student", "student@demo.local").data
    t = tok(c, "/planner")
    r = c.post("/planner", data=dict(csrf=t, village="Hosahalli", college="Bangalore University Campus", students=5, date="2030-01-07", time="07:00"))
    assert b"Demand prediction" in r.data and b"KA-DEMO" in r.data
    r = c.post("/emergency", data=dict(csrf=t, village="Hosahalli", college="Bangalore University Campus", students=5, date="2030-01-07", time="07:00"))
    assert b"Best match" in r.data and b"KA-01-DEMO-1001" in r.data
    r = c.post("/emergency/request", data=dict(csrf=t, vehicle_id=1, village="Hosahalli", college="Bangalore University Campus", students=5, date="2030-01-07", time="07:00"), follow_redirects=True)
    assert b"Waiting for admin approval" in r.data

def test_admin_and_parent():
    c = app.test_client(); assert b"Administrator dashboard" in login(c, "admin", "admin@demo.local").data
    t = tok(c, "/admin")
    assert b"Bus saved" in c.post("/admin/bus", data=dict(csrf=t, action="add", number="KA-NEW-1", route_id=1, depart_time="09:00", capacity=40), follow_redirects=True).data
    assert b"Request approved" in c.post("/admin/request", data=dict(csrf=t, id=1, action="approve"), follow_redirects=True).data
    assert c.get("/api/map").status_code == 200
    p = app.test_client(); assert b"Ride details" in login(p, "parent", "parent@demo.local").data
    assert b"confirmed" in p.get("/dashboard").data

def test_crisis():
    c = app.test_client(); login(c, "admin", "admin@demo.local"); t = tok(c, "/crisis")
    r = c.post("/crisis/activate", data=dict(csrf=t, broken=2, surge=40, block_a="Maddur Village", block_b="Channapatna Outskirts"), follow_redirects=True)
    assert b"Priority order" in r.data and b"Detour via" in r.data
    assert b"Road closed" in c.get("/static/../tracking").data or c.get("/api/map").json["blocked"]
    s = app.test_client(); login(s, "student", "student@demo.local"); assert b"Exam-day crisis" in s.get("/crisis").data
    assert s.post("/crisis/activate", data=dict(csrf=tok(s, "/crisis"))).status_code == 403
    assert b"Crisis ended" in c.post("/crisis/reset", data=dict(csrf=t), follow_redirects=True).data
