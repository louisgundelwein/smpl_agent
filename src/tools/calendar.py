"""Calendar tool for managing CalDAV calendars and events."""

import json
import uuid
from datetime import datetime
from typing import Any

import caldav

from src.calendar_store import CalendarConnectionStore
from src.tools.base import Tool


class CalendarTool(Tool):
    """Tool that gives the LLM access to CalDAV calendars.

    Supports managing connections, listing calendars, and full
    CRUD on events (create, list, update, delete) including reminders.
    Works with any CalDAV-compatible provider (Nextcloud, iCloud,
    Google Calendar, generic CalDAV).
    """

    def __init__(self, store: CalendarConnectionStore) -> None:
        self._store = store

    @property
    def name(self) -> str:
        return "calendar"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Manage calendars and events via CalDAV. "
                    "First add a connection (CalDAV server), then list calendars, "
                    "then create/list/update/delete events. "
                    "Supports Nextcloud, iCloud, Google Calendar, and any CalDAV server."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "add_connection",
                                "list_connections",
                                "remove_connection",
                                "list_calendars",
                                "list_events",
                                "create_event",
                                "update_event",
                                "delete_event",
                            ],
                            "description": (
                                "'add_connection' to register a CalDAV server, "
                                "'list_connections' to show all connections, "
                                "'remove_connection' to unregister, "
                                "'list_calendars' to list calendars on a connection, "
                                "'list_events' to list events in a date range, "
                                "'create_event' to create a new event, "
                                "'update_event' to modify an event, "
                                "'delete_event' to remove an event."
                            ),
                        },
                        "connection": {
                            "type": "string",
                            "description": "Connection name (for calendar/event operations).",
                        },
                        "calendar": {
                            "type": "string",
                            "description": "Calendar name (for event operations).",
                        },
                        "name": {
                            "type": "string",
                            "description": "Connection name (for add/remove connection).",
                        },
                        "url": {
                            "type": "string",
                            "description": "CalDAV server URL (for add_connection).",
                        },
                        "username": {
                            "type": "string",
                            "description": "Username (for add_connection).",
                        },
                        "password": {
                            "type": "string",
                            "description": "Password or app-specific password (for add_connection).",
                        },
                        "provider": {
                            "type": "string",
                            "enum": ["caldav", "nextcloud", "icloud", "google"],
                            "description": "Provider type hint (default: 'caldav').",
                        },
                        "summary": {
                            "type": "string",
                            "description": "Event title/summary.",
                        },
                        "start": {
                            "type": "string",
                            "description": "Start datetime in ISO 8601 format (e.g. '2026-03-15T10:00:00').",
                        },
                        "end": {
                            "type": "string",
                            "description": "End datetime in ISO 8601 format (e.g. '2026-03-15T11:00:00').",
                        },
                        "description": {
                            "type": "string",
                            "description": "Event description/notes.",
                        },
                        "location": {
                            "type": "string",
                            "description": "Event location.",
                        },
                        "reminder_minutes": {
                            "type": "integer",
                            "description": "Reminder N minutes before the event.",
                        },
                        "uid": {
                            "type": "string",
                            "description": "Event UID (for update/delete).",
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        try:
            if action == "add_connection":
                return self._add_connection(kwargs)
            elif action == "list_connections":
                return self._list_connections()
            elif action == "remove_connection":
                return self._remove_connection(kwargs)
            elif action == "list_calendars":
                return self._list_calendars(kwargs)
            elif action == "list_events":
                return self._list_events(kwargs)
            elif action == "create_event":
                return self._create_event(kwargs)
            elif action == "update_event":
                return self._update_event(kwargs)
            elif action == "delete_event":
                return self._delete_event(kwargs)
            else:
                return json.dumps({"error": f"Unknown action: {action}"})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _add_connection(self, kw: dict) -> str:
        name = kw.get("name")
        url = kw.get("url")
        username = kw.get("username")
        password = kw.get("password")

        if not all([name, url, username, password]):
            return json.dumps({
                "error": "name, url, username, and password are required for 'add_connection'"
            })

        provider = kw.get("provider", "caldav")
        conn_id = self._store.add(
            name=name, url=url, username=username,
            password=password, provider=provider,
        )
        return json.dumps({
            "added": True,
            "connection_id": conn_id,
            "total_connections": self._store.count(),
        })

    def _list_connections(self) -> str:
        conns = self._store.list_all()
        return json.dumps({"connections": conns, "count": len(conns)}, ensure_ascii=False)

    def _remove_connection(self, kw: dict) -> str:
        name = kw.get("name")
        if not name:
            return json.dumps({"error": "name is required for 'remove_connection'"})
        removed = self._store.remove(name)
        return json.dumps({"removed": removed, "name": name})

    # ------------------------------------------------------------------
    # CalDAV helpers
    # ------------------------------------------------------------------

    def _get_client(self, connection_name: str) -> caldav.DAVClient:
        """Build a caldav.DAVClient from a stored connection."""
        conn = self._store.get(connection_name)
        if conn is None:
            raise ValueError(f"Connection '{connection_name}' not found")
        return caldav.DAVClient(
            url=conn["url"],
            username=conn["username"],
            password=conn["password"],
        )

    def _find_calendar(
        self, client: caldav.DAVClient, calendar_name: str,
    ) -> caldav.Calendar:
        """Find a calendar by display name on the principal."""
        principal = client.principal()
        for cal in principal.calendars():
            if cal.name == calendar_name:
                return cal
        raise ValueError(
            f"Calendar '{calendar_name}' not found on this connection"
        )

    @staticmethod
    def _parse_dt(value: str) -> datetime:
        """Parse an ISO 8601 datetime string."""
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)

    @staticmethod
    def _build_vcalendar(
        summary: str,
        dtstart: datetime,
        dtend: datetime,
        description: str = "",
        location: str = "",
        reminder_minutes: int | None = None,
        uid: str | None = None,
    ) -> str:
        """Build a VCALENDAR/VEVENT iCalendar string."""
        if uid is None:
            uid = str(uuid.uuid4())

        def _fmt(dt: datetime) -> str:
            return dt.strftime("%Y%m%dT%H%M%S")

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//smpl_agent//CalendarTool//EN",
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTART:{_fmt(dtstart)}",
            f"DTEND:{_fmt(dtend)}",
            f"SUMMARY:{summary}",
        ]
        if description:
            lines.append(f"DESCRIPTION:{description}")
        if location:
            lines.append(f"LOCATION:{location}")
        if reminder_minutes is not None and reminder_minutes > 0:
            lines.extend([
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                f"TRIGGER:-PT{reminder_minutes}M",
                f"DESCRIPTION:{summary} reminder",
                "END:VALARM",
            ])
        lines.extend(["END:VEVENT", "END:VCALENDAR"])
        return "\r\n".join(lines)

    @staticmethod
    def _event_to_dict(event: Any) -> dict[str, Any]:
        """Extract key fields from a caldav Event into a plain dict."""
        try:
            vevent = event.vobject_instance.vevent
        except Exception:
            return {"raw": str(event.data) if hasattr(event, "data") else str(event)}

        def _get(attr: str) -> str | None:
            try:
                val = getattr(vevent, attr, None)
                if val is None:
                    return None
                return str(val.value)
            except Exception:
                return None

        result: dict[str, Any] = {}
        result["uid"] = _get("uid")
        result["summary"] = _get("summary")
        result["dtstart"] = _get("dtstart")
        result["dtend"] = _get("dtend")
        result["description"] = _get("description")
        result["location"] = _get("location")

        # Extract reminders
        try:
            alarms = list(vevent.valarm_list)
            if alarms:
                result["reminders"] = []
                for alarm in alarms:
                    trigger = str(alarm.trigger.value)
                    result["reminders"].append(trigger)
        except Exception:
            pass

        return result

    # ------------------------------------------------------------------
    # Calendar operations
    # ------------------------------------------------------------------

    def _list_calendars(self, kw: dict) -> str:
        connection = kw.get("connection")
        if not connection:
            return json.dumps({"error": "connection is required for 'list_calendars'"})

        client = self._get_client(connection)
        principal = client.principal()
        calendars = principal.calendars()
        result = [{"name": cal.name, "url": str(cal.url)} for cal in calendars]
        return json.dumps({"calendars": result, "count": len(result)}, ensure_ascii=False)

    def _list_events(self, kw: dict) -> str:
        connection = kw.get("connection")
        calendar_name = kw.get("calendar")
        start = kw.get("start")
        end = kw.get("end")

        if not all([connection, calendar_name, start, end]):
            return json.dumps({
                "error": "connection, calendar, start, and end are required for 'list_events'"
            })

        client = self._get_client(connection)
        cal = self._find_calendar(client, calendar_name)
        events = cal.search(
            start=self._parse_dt(start),
            end=self._parse_dt(end),
            event=True,
            expand=True,
        )
        result = [self._event_to_dict(e) for e in events]
        return json.dumps({"events": result, "count": len(result)}, ensure_ascii=False)

    def _create_event(self, kw: dict) -> str:
        connection = kw.get("connection")
        calendar_name = kw.get("calendar")
        summary = kw.get("summary")
        start = kw.get("start")
        end = kw.get("end")

        if not all([connection, calendar_name, summary, start, end]):
            return json.dumps({
                "error": "connection, calendar, summary, start, and end are required for 'create_event'"
            })

        client = self._get_client(connection)
        cal = self._find_calendar(client, calendar_name)

        event_uid = str(uuid.uuid4())
        vcal = self._build_vcalendar(
            summary=summary,
            dtstart=self._parse_dt(start),
            dtend=self._parse_dt(end),
            description=kw.get("description", ""),
            location=kw.get("location", ""),
            reminder_minutes=kw.get("reminder_minutes"),
            uid=event_uid,
        )
        cal.save_event(vcal)

        return json.dumps({
            "created": True,
            "uid": event_uid,
            "summary": summary,
            "start": start,
            "end": end,
        }, ensure_ascii=False)

    def _update_event(self, kw: dict) -> str:
        connection = kw.get("connection")
        calendar_name = kw.get("calendar")
        uid = kw.get("uid")

        if not all([connection, calendar_name, uid]):
            return json.dumps({
                "error": "connection, calendar, and uid are required for 'update_event'"
            })

        client = self._get_client(connection)
        cal = self._find_calendar(client, calendar_name)

        # Find the event by UID
        try:
            event = cal.event_by_uid(uid)
        except Exception:
            return json.dumps({"error": f"Event with UID '{uid}' not found"})

        vevent = event.vobject_instance.vevent

        if "summary" in kw:
            vevent.summary.value = kw["summary"]
        if "start" in kw:
            vevent.dtstart.value = self._parse_dt(kw["start"])
        if "end" in kw:
            vevent.dtend.value = self._parse_dt(kw["end"])
        if "description" in kw:
            if hasattr(vevent, "description"):
                vevent.description.value = kw["description"]
            else:
                vevent.add("description").value = kw["description"]
        if "location" in kw:
            if hasattr(vevent, "location"):
                vevent.location.value = kw["location"]
            else:
                vevent.add("location").value = kw["location"]

        event.save()

        return json.dumps({
            "updated": True,
            "uid": uid,
        })

    def _delete_event(self, kw: dict) -> str:
        connection = kw.get("connection")
        calendar_name = kw.get("calendar")
        uid = kw.get("uid")

        if not all([connection, calendar_name, uid]):
            return json.dumps({
                "error": "connection, calendar, and uid are required for 'delete_event'"
            })

        client = self._get_client(connection)
        cal = self._find_calendar(client, calendar_name)

        try:
            event = cal.event_by_uid(uid)
        except Exception:
            return json.dumps({"error": f"Event with UID '{uid}' not found"})

        event.delete()

        return json.dumps({
            "deleted": True,
            "uid": uid,
        })
