"""Explainable rule-based engines. No ML model is trained or claimed; scikit-learn is
reserved for a future version once real travel records exist (see README)."""
from database import VILLAGES, COLLEGES, road_km

def predict_demand(students, seats, weekday=None, hour=None, history_avg=None):
    shortage = max(0, students - seats)
    ratio = students / seats if seats else 9.9
    why = [f"{students} students need seats; {seats} are available."]
    factor = 1.0
    if weekday in (0, 4): factor += .05; why.append("Mondays and Fridays usually run busier (assumed rule).")
    if hour is not None and 6 <= hour <= 9: factor += .05; why.append("Morning peak hour (assumed rule).")
    if history_avg: why.append(f"Average of past requests on this route: {history_avg:.0f} students.")
    predicted = round(students * factor)
    shortage = max(0, predicted - seats)
    level = "LOW" if ratio <= .7 else "MEDIUM" if ratio <= 1 else "HIGH"
    vans = -(-shortage // 10)
    return {"predicted": predicted, "capacity": seats, "shortage": shortage, "level": level,
            "extra_vehicles": vans, "method": "Rule-based (no trained model)", "explanation": why}

def route_info(village, college):
    km = road_km(VILLAGES[village], COLLEGES[college])
    return {"km": km, "minutes": round(km / 35 * 60 + 5)}  # assumes 35 km/h rural average

def match_vehicles(vehicles, village, college, group, groups_nearby=()):
    """Rank verified, available vehicles. groups_nearby: [(village, n_students)] heading to the same college."""
    info = route_info(village, college); total = group + sum(n for _, n in groups_nearby)
    out = []
    for v in vehicles:
        if not v["available"]: continue
        km_to_pickup = road_km((v["lat"], v["lng"]), VILLAGES[village])
        fare_total = (info["km"] + km_to_pickup) * v["rate_per_km"]
        shared = min(total, v["seats"])
        per = round(fare_total / max(1, shared) , 0)
        fits = v["seats"] >= group
        score = (0 if v["verified"] else 100) + km_to_pickup + (0 if fits else 500) + max(0, v["seats"] - total) * 2
        reasons = [f"{'Verified' if v['verified'] else 'NOT verified'} driver/vehicle",
                   f"{km_to_pickup} km from pickup", f"{v['seats']} seats for {total} student(s)"]
        if groups_nearby and v["seats"] >= total: reasons.append("Can carry all nearby groups in one trip, which splits the cost")
        out.append({"id": v["id"], "reg_no": v["reg_no"], "type": v["vehicle_type"], "seats": v["seats"], "verified": bool(v["verified"]),
                    "distance_km": info["km"], "minutes": info["minutes"], "fare_per_student": per, "fare_total": round(fare_total),
                    "score": round(score, 1), "reasons": reasons, "fits_group": fits})
    return sorted(out, key=lambda x: x["score"])


# ---------------- Exam-day crisis engine ----------------
import math

def nearest_village(lat, lng):
    return min(VILLAGES, key=lambda v: road_km(VILLAGES[v], (lat, lng)))

def trip(village, college, blocked):
    """Road km and detour village. A village on the flooded road must go round via the best other village."""
    km, via = road_km(VILLAGES[village], COLLEGES[college]), None
    if blocked and village in blocked:
        other = blocked[1] if village == blocked[0] else blocked[0]
        best = min(((road_km(VILLAGES[village], VILLAGES[x]) + road_km(VILLAGES[x], COLLEGES[college]), x)
                    for x in VILLAGES if x not in (village, other)), default=None)
        if best: km, via = best
    return km, via

def crisis_plan(cohorts, buses, vehicles, blocked, surge_pct, buffer=15, boarding=10):
    """Greedy, explainable plan: most urgent exam groups are served first; buses first, then smallest verified van that fits.
    Assumes (1) surviving buses and vans can be dispatched immediately, (2) 35 km/h rural average, (3) one van serves one group."""
    f = 1 + surge_pct / 100
    dem = []
    for c in cohorts:
        km, via = trip(c["village"], c["college"], blocked)
        dem.append(dict(c, n=math.ceil(c["students"] * f), km=km, via=via, mins=round(km / 35 * 60 + 5)))
    on_route = lambda b, d: b["status"] == "running" and b["origin"] == d["village"] and b["destination"] == d["college"]
    # Before: surviving buses only, first come first served, no vans, no priority (same on-time rule)
    left = {b["id"]: b["seats_left"] for b in buses}; base = base_exam = 0
    for d in dem:
        need = d["n"]
        for b in buses:
            if on_route(b, d) and need > 0 and (d["exam_min"] is None or d["mins"] + boarding <= d["exam_min"] - buffer):
                t = min(need, left[b["id"]]); left[b["id"]] -= t; need -= t; base += t
                if d["exam_min"] is not None: base_exam += t
    # After: prioritised reallocation
    bus_cap = {b["id"]: b["seats_left"] for b in buses}
    vans = [dict(v, base=nearest_village(v["lat"], v["lng"])) for v in vehicles if v["available"] and v["verified"]]
    van_free = {v["id"]: True for v in vans}
    out, res = [], []
    order = sorted(dem, key=lambda d: (d["exam_min"] if d["exam_min"] is not None else 10**6, -d["n"]))
    for rank, d in enumerate(order, 1):
        need, got = d["n"], 0
        limit = None if d["exam_min"] is None else d["exam_min"] - buffer
        ok = lambda eta: limit is None or eta <= limit
        for b in buses:
            if need > 0 and on_route(b, d) and bus_cap[b["id"]] > 0 and ok(d["mins"] + boarding):
                t = min(need, bus_cap[b["id"]]); bus_cap[b["id"]] -= t; need -= t; got += t
                out.append(dict(village=d["village"], mode="Bus", ref=b["number"], n=t, eta=d["mins"] + boarding, via=d["via"], exam_min=d["exam_min"]))
        while need > 0:
            cands = []
            for v in vans:
                if not van_free[v["id"]]: continue
                pk = road_km(VILLAGES[v["base"]], VILLAGES[d["village"]])
                if blocked and {v["base"], d["village"]} == set(blocked): pk *= 1.6  # detour round the flooded road
                eta = round(pk / 35 * 60 + boarding + d["mins"])
                if ok(eta): cands.append((v, eta))
            if not cands: break
            fit = [c for c in cands if c[0]["seats"] >= need]
            v, eta = min(fit, key=lambda c: (c[0]["seats"], c[1])) if fit else max(cands, key=lambda c: c[0]["seats"])
            t = min(need, v["seats"]); van_free[v["id"]] = False; need -= t; got += t
            out.append(dict(village=d["village"], mode=v["vehicle_type"], ref=v["reg_no"], n=t, eta=eta, via=d["via"], exam_min=d["exam_min"], spare=v["seats"] - t))
        status = "Fully covered" if need == 0 else "Partly covered" if got else "Stranded"
        res.append(dict(rank=rank, village=d["village"], college=d["college"], exam_min=d["exam_min"], n=d["n"], seated=got, stranded=need,
                        via=d["via"], km=d["km"], mins=d["mins"], status=status))
    total = sum(d["n"] for d in dem); seated = sum(r["seated"] for r in res)
    exam_total = sum(d["n"] for d in dem if d["exam_min"] is not None)
    exam_seated = sum(r["seated"] for r in res if r["exam_min"] is not None)
    stranded = total - seated
    return dict(demand=total, seated=seated, stranded=stranded, base_seated=base, base_stranded=total - base,
                exam_total=exam_total, exam_seated=exam_seated, base_exam=base_exam,
                results=res, assignments=out, extra_vehicles=-(-stranded // 10), spare=sum(a.get("spare", 0) for a in out))
