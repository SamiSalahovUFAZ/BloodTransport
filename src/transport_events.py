from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TransportEvent:
    request_id: str
    previous_status: str
    status: str
    actor: str
    note: Optional[str] = None
    receipt_condition: Optional[str] = None
    receipt_note: Optional[str] = None


def record_history(connection, event):
    connection.execute("""
        INSERT INTO transport_history (request_id, previous_status, status, actor, note)
        VALUES (?, ?, ?, ?, ?)
    """, (event.request_id, event.previous_status, event.status, event.actor, event.note))


def report_receipt_issue(connection, event):
    if event.receipt_condition == "issue":
        connection.execute("""
            INSERT INTO transport_incidents (request_id, description, reported_by)
            VALUES (?, ?, ?)
        """, (event.request_id, event.receipt_note, event.actor))


SUBSCRIBERS = (record_history, report_receipt_issue)


def publish_transport_event(connection, event):
    # Subscribers share the write transaction so failed history or issue writes roll back the handoff.
    for subscriber in SUBSCRIBERS:
        subscriber(connection, event)
