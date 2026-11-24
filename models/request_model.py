# models/request_model.py - MODEL for resource requests stored in Azure Cosmos DB.
# Uses the shared db.get_container("requests") helper (partition key: /request_type).

import uuid

from db import get_container


def _run(query, parameters=None):
    """Execute a cross-partition SQL query against the Cosmos DB 'requests' container."""
    return list(
        get_container("requests").query_items(
            query=query,
            parameters=parameters or [],
            enable_cross_partition_query=True,
        )
    )


def _normalize_request(doc):
    """Ensure every request document has consistent default fields for UI rendering."""
    item = dict(doc)
    item["status"] = (item.get("status") or "pending").strip().lower()
    item["request_type"] = (item.get("request_type") or "general").strip().lower()
    return item


def get_all_requests():
    """Collect all resource requests across every partition, sorted newest-first in Python."""
    # Avoid SQL 'ORDER BY c._ts DESC' across partitions so missing composite indexes never break queries
    items = [_normalize_request(r) for r in _run("SELECT * FROM c")]
    return sorted(items, key=lambda r: r.get("_ts", 0), reverse=True)


def get_requests_by_user(work_id):
    """Collect only the requests submitted by one staff member (used for their status tracker)."""
    clean_work_id = (work_id or "").strip()
    if not clean_work_id:
        return []

    # Case-insensitive match on work_id so staff always see their pending/approved/rejected requests
    items = [
        _normalize_request(r)
        for r in _run(
            "SELECT * FROM c WHERE UPPER(c.work_id) = @work_id",
            [{"name": "@work_id", "value": clean_work_id.upper()}],
        )
    ]
    return sorted(items, key=lambda r: r.get("_ts", 0), reverse=True)


def get_request(request_id, request_type):
    """Read a single request document directly using its ID and partition key (/request_type)."""
    doc = get_container("requests").read_item(item=request_id, partition_key=request_type)
    return _normalize_request(doc)


def create_request(name, work_id, request_type, items_needed, date, time, end_time, venue):
    """Create and persist a new staff resource request in Azure Cosmos DB with status 'pending'."""
    clean_type = (request_type or "general").strip().lower()
    clean_work_id = (work_id or "").strip().upper()

    data = {
        "id": str(uuid.uuid4()),          # Unique document ID in Cosmos DB
        "name": (name or "").strip(),
        "work_id": clean_work_id,         # Links the request back to the submitting staff member
        "request_type": clean_type,       # Partition key (/request_type) for the 'requests' container
        "items_needed": (items_needed or "").strip(),
        "date": date,
        "time": time,
        "end_time": end_time,
        "venue": (venue or "").strip(),
        "status": "pending",              # Initial lifecycle state until admin approves or rejects
    }
    get_container("requests").create_item(body=data)
    return data


def set_request_status(item, status):
    """Update a request's status ('approved' or 'rejected') in Azure Cosmos DB."""
    item["status"] = status.strip().lower()
    # replace_item updates the document in place while preserving its partition key (/request_type)
    get_container("requests").replace_item(item=item["id"], body=item)
    return item


# ---------- double-booking check ----------

def _item_set(text):
    """Parse comma-separated items ('Projector, HDMI cable' -> {'projector', 'hdmi cable'})."""
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
    """Aggregate request counts by formatted category ({'Office Items': 4, 'Field Day': 2, ...})."""
    counts = {}
    for r in requests:
        label = (r.get("request_type") or "unknown").replace("_", " ").title()
        counts[label] = counts.get(label, 0) + 1
    return counts


def get_item_counts(requests, limit=6):
    """Return the top requested individual items ({'projector': 5, ...}) for dashboard charts."""
    counts = {}
    for r in requests:
        for item in _item_set(r.get("items_needed")):
            counts[item] = counts.get(item, 0) + 1
    top = sorted(counts.items(), key=lambda pair: pair[1], reverse=True)[:limit]
    return dict(top)