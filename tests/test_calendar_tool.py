"""Tests for src.tools.calendar — CalendarTool with mocked CalDAV."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.calendar_store import CalendarConnectionStore
from src.tools.calendar import CalendarTool


@pytest.fixture()
def store():
    """Fake CalendarConnectionStore backed by an in-memory dict (no DB required)."""
    from unittest.mock import MagicMock
    s = MagicMock(spec=CalendarConnectionStore)
    _data = {}
    _seq = iter(range(1, 10_000))

    def _add(name, url, username, password, provider="caldav"):
        if name in _data:
            import psycopg2.errors
            raise psycopg2.errors.UniqueViolation("duplicate key")
        conn_id = next(_seq)
        _data[name] = dict(id=conn_id, name=name, url=url, username=username,
                           password=password, provider=provider,
                           added_at="2026-01-01T00:00:00+00:00")
        return conn_id

    s.add.side_effect = _add
    s.list_all.side_effect = lambda: [
        {k: v for k, v in c.items() if k != "password"} for c in _data.values()
    ]
    s.get.side_effect = lambda name: _data.get(name)
    s.remove.side_effect = lambda name: bool(_data.pop(name, None))
    s.count.side_effect = lambda: len(_data)
    yield s


@pytest.fixture()
def tool(store):
    return CalendarTool(store=store)


@pytest.fixture()
def store_with_conn(store):
    """Store pre-loaded with one connection."""
    store.add(
        name="work",
        url="https://cal.example.com/dav/",
        username="alice",
        password="secret",
        provider="nextcloud",
    )
    return store


@pytest.fixture()
def tool_with_conn(store_with_conn):
    return CalendarTool(store=store_with_conn)


# ------------------------------------------------------------------
# Connection management
# ------------------------------------------------------------------


class TestAddConnection:
    def test_success(self, tool):
        result = json.loads(tool.execute(
            action="add_connection",
            name="work",
            url="https://cal.example.com/dav/",
            username="alice",
            password="secret",
            provider="nextcloud",
        ))
        assert result["added"] is True
        assert result["total_connections"] == 1

    def test_missing_fields(self, tool):
        result = json.loads(tool.execute(action="add_connection", name="x"))
        assert "error" in result

    def test_duplicate_name(self, tool):
        tool.execute(
            action="add_connection", name="a",
            url="https://a", username="u", password="p",
        )
        result = json.loads(tool.execute(
            action="add_connection", name="a",
            url="https://b", username="u2", password="p2",
        ))
        assert "error" in result


class TestListConnections:
    def test_empty(self, tool):
        result = json.loads(tool.execute(action="list_connections"))
        assert result["count"] == 0
        assert result["connections"] == []

    def test_with_connections(self, tool_with_conn):
        result = json.loads(tool_with_conn.execute(action="list_connections"))
        assert result["count"] == 1
        assert result["connections"][0]["name"] == "work"
        # Password must not appear in list
        assert "password" not in result["connections"][0]


class TestRemoveConnection:
    def test_success(self, tool_with_conn):
        result = json.loads(tool_with_conn.execute(
            action="remove_connection", name="work",
        ))
        assert result["removed"] is True

    def test_not_found(self, tool):
        result = json.loads(tool.execute(
            action="remove_connection", name="ghost",
        ))
        assert result["removed"] is False

    def test_missing_name(self, tool):
        result = json.loads(tool.execute(action="remove_connection"))
        assert "error" in result


# ------------------------------------------------------------------
# Calendar operations (CalDAV mocked)
# ------------------------------------------------------------------


def _mock_calendar(name="Personal"):
    """Create a mock caldav.Calendar."""
    cal = MagicMock()
    cal.name = name
    cal.url = f"https://cal.example.com/dav/{name}/"
    return cal


def _mock_event(uid="test-uid-123", summary="Meeting", dtstart="2026-03-15 10:00:00",
                dtend="2026-03-15 11:00:00", description=None, location=None):
    """Create a mock caldav Event with vobject_instance."""
    event = MagicMock()
    vevent = MagicMock()

    vevent.uid.value = uid
    vevent.summary.value = summary
    vevent.dtstart.value = dtstart
    vevent.dtend.value = dtend

    if description:
        vevent.description.value = description
    else:
        vevent.description = None

    if location:
        vevent.location.value = location
    else:
        vevent.location = None

    # No alarms by default
    vevent.valarm_list = []

    event.vobject_instance.vevent = vevent
    return event


class TestListCalendars:
    @patch("src.tools.calendar.caldav.DAVClient")
    def test_success(self, mock_dav_cls, tool_with_conn):
        mock_client = MagicMock()
        mock_dav_cls.return_value = mock_client
        mock_client.principal.return_value.calendars.return_value = [
            _mock_calendar("Personal"),
            _mock_calendar("Work"),
        ]

        result = json.loads(tool_with_conn.execute(
            action="list_calendars", connection="work",
        ))
        assert result["count"] == 2
        assert result["calendars"][0]["name"] == "Personal"
        assert result["calendars"][1]["name"] == "Work"

    def test_missing_connection(self, tool):
        result = json.loads(tool.execute(action="list_calendars"))
        assert "error" in result

    @patch("src.tools.calendar.caldav.DAVClient")
    def test_connection_not_found(self, mock_dav_cls, tool):
        result = json.loads(tool.execute(
            action="list_calendars", connection="nonexistent",
        ))
        assert "error" in result
        assert "not found" in result["error"]


class TestListEvents:
    @patch("src.tools.calendar.caldav.DAVClient")
    def test_success(self, mock_dav_cls, tool_with_conn):
        mock_client = MagicMock()
        mock_dav_cls.return_value = mock_client
        mock_cal = _mock_calendar("Personal")
        mock_client.principal.return_value.calendars.return_value = [mock_cal]
        mock_cal.search.return_value = [
            _mock_event(uid="e1", summary="Standup"),
        ]

        result = json.loads(tool_with_conn.execute(
            action="list_events",
            connection="work",
            calendar="Personal",
            start="2026-03-01T00:00:00",
            end="2026-03-31T23:59:59",
        ))
        assert result["count"] == 1
        assert result["events"][0]["summary"] == "Standup"
        assert result["events"][0]["uid"] == "e1"

    def test_missing_fields(self, tool_with_conn):
        result = json.loads(tool_with_conn.execute(
            action="list_events", connection="work",
        ))
        assert "error" in result


class TestCreateEvent:
    @patch("src.tools.calendar.caldav.DAVClient")
    def test_success(self, mock_dav_cls, tool_with_conn):
        mock_client = MagicMock()
        mock_dav_cls.return_value = mock_client
        mock_cal = _mock_calendar("Personal")
        mock_client.principal.return_value.calendars.return_value = [mock_cal]

        result = json.loads(tool_with_conn.execute(
            action="create_event",
            connection="work",
            calendar="Personal",
            summary="Team Meeting",
            start="2026-03-15T10:00:00",
            end="2026-03-15T11:00:00",
            description="Weekly sync",
            location="Room 42",
            reminder_minutes=15,
        ))
        assert result["created"] is True
        assert result["summary"] == "Team Meeting"
        assert result["uid"]  # non-empty UUID

        # Verify save_event was called with iCalendar data
        mock_cal.save_event.assert_called_once()
        vcal_data = mock_cal.save_event.call_args[0][0]
        assert "BEGIN:VCALENDAR" in vcal_data
        assert "Team Meeting" in vcal_data
        assert "Room 42" in vcal_data
        assert "VALARM" in vcal_data
        assert "TRIGGER:-PT15M" in vcal_data

    @patch("src.tools.calendar.caldav.DAVClient")
    def test_without_reminder(self, mock_dav_cls, tool_with_conn):
        mock_client = MagicMock()
        mock_dav_cls.return_value = mock_client
        mock_cal = _mock_calendar("Personal")
        mock_client.principal.return_value.calendars.return_value = [mock_cal]

        result = json.loads(tool_with_conn.execute(
            action="create_event",
            connection="work",
            calendar="Personal",
            summary="Quick Chat",
            start="2026-03-15T14:00:00",
            end="2026-03-15T14:30:00",
        ))
        assert result["created"] is True

        vcal_data = mock_cal.save_event.call_args[0][0]
        assert "VALARM" not in vcal_data

    def test_missing_fields(self, tool_with_conn):
        result = json.loads(tool_with_conn.execute(
            action="create_event", connection="work", calendar="Personal",
        ))
        assert "error" in result


class TestUpdateEvent:
    @patch("src.tools.calendar.caldav.DAVClient")
    def test_success(self, mock_dav_cls, tool_with_conn):
        mock_client = MagicMock()
        mock_dav_cls.return_value = mock_client
        mock_cal = _mock_calendar("Personal")
        mock_client.principal.return_value.calendars.return_value = [mock_cal]

        mock_evt = _mock_event(uid="u1", summary="Old Title")
        mock_cal.event_by_uid.return_value = mock_evt

        result = json.loads(tool_with_conn.execute(
            action="update_event",
            connection="work",
            calendar="Personal",
            uid="u1",
            summary="New Title",
        ))
        assert result["updated"] is True
        assert result["uid"] == "u1"

        # Verify the summary was changed
        vevent = mock_evt.vobject_instance.vevent
        assert vevent.summary.value == "New Title"
        mock_evt.save.assert_called_once()

    @patch("src.tools.calendar.caldav.DAVClient")
    def test_event_not_found(self, mock_dav_cls, tool_with_conn):
        mock_client = MagicMock()
        mock_dav_cls.return_value = mock_client
        mock_cal = _mock_calendar("Personal")
        mock_client.principal.return_value.calendars.return_value = [mock_cal]
        mock_cal.event_by_uid.side_effect = Exception("Not found")

        result = json.loads(tool_with_conn.execute(
            action="update_event",
            connection="work",
            calendar="Personal",
            uid="missing",
            summary="X",
        ))
        assert "error" in result

    def test_missing_fields(self, tool_with_conn):
        result = json.loads(tool_with_conn.execute(
            action="update_event", connection="work",
        ))
        assert "error" in result


class TestDeleteEvent:
    @patch("src.tools.calendar.caldav.DAVClient")
    def test_success(self, mock_dav_cls, tool_with_conn):
        mock_client = MagicMock()
        mock_dav_cls.return_value = mock_client
        mock_cal = _mock_calendar("Personal")
        mock_client.principal.return_value.calendars.return_value = [mock_cal]

        mock_evt = _mock_event(uid="del1")
        mock_cal.event_by_uid.return_value = mock_evt

        result = json.loads(tool_with_conn.execute(
            action="delete_event",
            connection="work",
            calendar="Personal",
            uid="del1",
        ))
        assert result["deleted"] is True
        assert result["uid"] == "del1"
        mock_evt.delete.assert_called_once()

    @patch("src.tools.calendar.caldav.DAVClient")
    def test_event_not_found(self, mock_dav_cls, tool_with_conn):
        mock_client = MagicMock()
        mock_dav_cls.return_value = mock_client
        mock_cal = _mock_calendar("Personal")
        mock_client.principal.return_value.calendars.return_value = [mock_cal]
        mock_cal.event_by_uid.side_effect = Exception("Not found")

        result = json.loads(tool_with_conn.execute(
            action="delete_event",
            connection="work",
            calendar="Personal",
            uid="missing",
        ))
        assert "error" in result

    def test_missing_fields(self, tool):
        result = json.loads(tool.execute(action="delete_event"))
        assert "error" in result


class TestUnknownAction:
    def test_unknown(self, tool):
        result = json.loads(tool.execute(action="bogus"))
        assert "error" in result
        assert "Unknown action" in result["error"]


class TestBuildVcalendar:
    def test_basic_event(self):
        from datetime import datetime
        vcal = CalendarTool._build_vcalendar(
            summary="Test",
            dtstart=datetime(2026, 3, 15, 10, 0),
            dtend=datetime(2026, 3, 15, 11, 0),
            uid="fixed-uid",
        )
        assert "BEGIN:VCALENDAR" in vcal
        assert "UID:fixed-uid" in vcal
        assert "SUMMARY:Test" in vcal
        assert "DTSTART:20260315T100000" in vcal
        assert "DTEND:20260315T110000" in vcal
        assert "VALARM" not in vcal

    def test_with_reminder(self):
        from datetime import datetime
        vcal = CalendarTool._build_vcalendar(
            summary="Reminder Test",
            dtstart=datetime(2026, 1, 1, 9, 0),
            dtend=datetime(2026, 1, 1, 10, 0),
            reminder_minutes=30,
        )
        assert "BEGIN:VALARM" in vcal
        assert "TRIGGER:-PT30M" in vcal
        assert "ACTION:DISPLAY" in vcal

    def test_with_all_fields(self):
        from datetime import datetime
        vcal = CalendarTool._build_vcalendar(
            summary="Full Event",
            dtstart=datetime(2026, 6, 1, 14, 0),
            dtend=datetime(2026, 6, 1, 15, 30),
            description="Detailed notes",
            location="Berlin",
            reminder_minutes=10,
            uid="my-uid",
        )
        assert "DESCRIPTION:Detailed notes" in vcal
        assert "LOCATION:Berlin" in vcal
        assert "UID:my-uid" in vcal
        assert "TRIGGER:-PT10M" in vcal
