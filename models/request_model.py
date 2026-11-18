# models/request_model.py - MODEL for resource requests.

import uuid

from db import get_container


def _run(query, parameters=None):
    return list(get_container("requests").query_items(
        query=query,
        parameters=parameters or [],
        enable_cross_partition_query=True,
    ))


def get_all_requests():
    """Every request, newest first."""
    return _run("SELECT * FROM c ORDER BY c._ts DESC")


def get_requests_by_user(work_id):
    """Only the requests submitted by one staff member, newest first."""
    return _run(
        "SELECT * FROM c WHERE c.work_id = @work_id ORDER BY c._ts DESC",
        [{"name": "@work_id", "value": work_id}],
    )


def get_request(request_id, request_type):
    """Read one request. Partition key is request_type."""
    return get_container("requests").read_item(item=request_id, partition_key=request_type)


def create_request(name, work_id, request_type, items_needed, date, time, end_time, venue):
    """Save a new request with status 'pending'."""
    data = {
        "id": str(uuid.uuid4()),
        "name": name,
        "work_id": work_id,
        "request_type": request_type,
        "items_needed": items_needed,
        "date": date,
        "time": time,
        "end_time": end_time,
        "venue": venue,
        "status": "pending",
    }
    get_container("requests").create_item(body=data)
    return data


def set_request_status(item, status):
    """Change a request's status ('approved' or 'rejected') and save it."""
    item["status"] = status
    get_container("requests").replace_item(item=item["id"], body=item)
    return item


# ---------- double-booking check ----------

def _item_set(text):
    """'Projector, HDMI cable' -> {'projector', 'hdmi cable'}"""
    return {part.strip().lower() for part in (text or "").split(",") if part.strip()}


def find_conflicts(req):
    """
    Return [(other_request, shared_items)] for approved requests that book the same
    item(s) on the same date with an overlapping time window.
    Once a booking's end time has passed, a later slot is free again.
    """
    approved = _run(
        "SELECT * FROM c WHERE c.status = 'approved' AND c.date = @date AND c.id != @id",
        [{"name": "@date", "value": req["date"]}, {"name": "@id", "value": req["id"]}],
    )
    mine = _item_set(req.get("items_needed"))
    start = req.get("time") or "00:00"
    end = req.get("end_time") or "23:59"

    conflicts = []
    for other in approved:
        shared = mine & _item_set(other.get("items_needed"))
        other_start = other.get("time") or "00:00"
        other_end = other.get("end_time") or "23:59"
        if shared and start < other_end and other_start < end:
            conflicts.append((other, shared))
    return conflicts


# ---------- chart data for the admin dashboard ----------

def get_type_counts(requests):
    """{'Office Items': 4, 'Field Day': 2, ...}"""
    counts = {}
    for r in requests:
        label = (r.get("request_type") or "unknown").replace("_", " ").title()
        counts[label] = counts.get(label, 0) + 1
    return counts


def get_item_counts(requests, limit=6):
    """Most requested individual items: {'projector': 5, ...}"""
    counts = {}
    for r in requests:
        for item in _item_set(r.get("items_needed")):
            counts[item] = counts.get(item, 0) + 1
    top = sorted(counts.items(), key=lambda pair: pair[1], reverse=True)[:limit]
    return dict(top)
