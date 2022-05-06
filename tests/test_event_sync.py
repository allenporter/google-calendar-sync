"""Tests for event sync library."""

import datetime
from collections.abc import Awaitable, Callable
from unittest.mock import patch

import aiohttp
import pytest
from freezegun import freeze_time

from gcal_sync.api import GoogleCalendarService, LocalListEventsRequest
from gcal_sync.event_sync import VERSION, CalendarEventSyncManager
from gcal_sync.exceptions import ApiException
from gcal_sync.model import EVENT_FIELDS, DateOrDatetime, Event
from gcal_sync.store import CalendarStore, InMemoryCalendarStore

from .conftest import ApiResult, ResponseResult

CALENDAR_ID = "some-calendar-id"


@pytest.fixture(name="store")
def fake_store() -> CalendarStore:
    """Fixture for a calendar store."""
    return InMemoryCalendarStore()


@pytest.fixture(name="event_sync_manager_cb")
def fake_event_sync_manager(
    calendar_service_cb: Callable[[], Awaitable[GoogleCalendarService]],
    store: CalendarStore,
) -> Callable[[], Awaitable[CalendarEventSyncManager]]:
    """Fixture for an event sync manager."""

    async def func() -> CalendarEventSyncManager:
        service = await calendar_service_cb()
        return CalendarEventSyncManager(service, CALENDAR_ID, store)

    return func


async def test_sync_failure(
    event_sync_manager_cb: Callable[[], Awaitable[CalendarEventSyncManager]],
    response: ResponseResult,
) -> None:
    """Test list calendars API."""

    response(aiohttp.web.Response(status=500))

    sync = await event_sync_manager_cb()
    with pytest.raises(ApiException):
        await sync.run()


@freeze_time("2022-04-05 07:31:02", tz_offset=-7)
async def test_lookup_items(
    event_sync_manager_cb: Callable[[], Awaitable[CalendarEventSyncManager]],
    json_response: ApiResult,
    url_request: Callable[[], str],
) -> None:
    """Test lookup events API."""

    json_response(
        {
            "items": [
                {
                    "id": "some-event-id-1",
                    "summary": "Event 1",
                    "description": "Event description 1",
                    "start": {
                        "date": "2022-04-13",
                    },
                    "end": {
                        "date": "2022-04-14",
                    },
                    "status": "confirmed",
                    "transparency": "transparent",
                },
                {
                    "id": "some-event-id-2",
                    "summary": "Event 2",
                    "description": "Event description 2",
                    "start": {
                        "date": "2022-04-15",
                    },
                    "end": {
                        "date": "2022-04-20",
                    },
                    "transparency": "opaque",
                },
            ]
        }
    )

    sync = await event_sync_manager_cb()
    await sync.run()
    assert url_request() == [
        "/calendars/some-calendar-id/events?maxResult=100&singleEvents=true&orderBy=startTime"
        f"&fields=kind,nextPageToken,nextSyncToken,items({EVENT_FIELDS})"
        "&timeMin=2022-03-08T00:31:02"
    ]

    result = await sync.store_service.async_list_events(
        LocalListEventsRequest(
            start_time=datetime.datetime.fromisoformat("2022-04-12 00:00:00"),
            end_time=datetime.datetime.fromisoformat("2022-04-16 00:00:00"),
        )
    )
    assert result.events == [
        Event(
            id="some-event-id-1",
            summary="Event 1",
            description="Event description 1",
            start=DateOrDatetime(date=datetime.date(2022, 4, 13)),
            end=DateOrDatetime(date=datetime.date(2022, 4, 14)),
            transparency="transparent",
        ),
        Event(
            id="some-event-id-2",
            summary="Event 2",
            description="Event description 2",
            start=DateOrDatetime(date=datetime.date(2022, 4, 15)),
            end=DateOrDatetime(date=datetime.date(2022, 4, 20)),
            transparency="opaque",
        ),
    ]

    result = await sync.store_service.async_list_events(
        LocalListEventsRequest(
            start_time=datetime.datetime.fromisoformat("2022-04-13 00:00:00"),
            end_time=datetime.datetime.fromisoformat("2022-04-14 00:00:00"),
        )
    )
    assert result.events == [
        Event(
            id="some-event-id-1",
            summary="Event 1",
            description="Event description 1",
            start=DateOrDatetime(date=datetime.date(2022, 4, 13)),
            end=DateOrDatetime(date=datetime.date(2022, 4, 14)),
            transparency="transparent",
        ),
    ]
    result = await sync.store_service.async_list_events(
        LocalListEventsRequest(
            start_time=datetime.datetime.fromisoformat("2022-04-15 00:00:00"),
            end_time=datetime.datetime.fromisoformat("2022-04-17 00:00:00"),
        )
    )
    assert result.events == [
        Event(
            id="some-event-id-2",
            summary="Event 2",
            description="Event description 2",
            start=DateOrDatetime(date=datetime.date(2022, 4, 15)),
            end=DateOrDatetime(date=datetime.date(2022, 4, 20)),
            transparency="opaque",
        ),
    ]

    result = await sync.store_service.async_list_events(
        LocalListEventsRequest(
            start_time=datetime.datetime.fromisoformat("2022-04-05 00:00:00"),
            end_time=datetime.datetime.fromisoformat("2022-04-07 00:00:00"),
        )
    )
    assert not result.events

    result = await sync.store_service.async_list_events(
        LocalListEventsRequest(
            start_time=datetime.datetime.fromisoformat("2022-04-21 00:00:00"),
            end_time=datetime.datetime.fromisoformat("2022-04-22 00:00:00"),
        )
    )
    assert not result.events


@freeze_time("2022-04-05 07:31:02", tz_offset=-7)
async def test_sync_date_pages(
    event_sync_manager_cb: Callable[[], Awaitable[CalendarEventSyncManager]],
    json_response: ApiResult,
    url_request: Callable[[], str],
) -> None:
    """Test lookup events API."""

    json_response(
        {
            "items": [
                {
                    "id": "some-event-id-1",
                    "summary": "Event 1",
                    "description": "Event description 1",
                    "start": {
                        "date": "2022-04-13",
                    },
                    "end": {
                        "date": "2022-04-14",
                    },
                    "status": "confirmed",
                    "transparency": "transparent",
                },
            ],
            "nextPageToken": "page-token-1",
        }
    )
    json_response(
        {
            "items": [
                {
                    "id": "some-event-id-2",
                    "summary": "Event 2",
                    "description": "Event description 2",
                    "start": {
                        "date": "2022-04-15",
                    },
                    "end": {
                        "date": "2022-04-20",
                    },
                    "transparency": "opaque",
                },
            ],
            "nextSyncToken": "sync-token-1",
        }
    )

    sync = await event_sync_manager_cb()
    await sync.run()
    assert url_request() == [
        "/calendars/some-calendar-id/events?maxResult=100&singleEvents=true&orderBy=startTime"
        f"&fields=kind,nextPageToken,nextSyncToken,items({EVENT_FIELDS})"
        "&timeMin=2022-03-08T00:31:02",
        "/calendars/some-calendar-id/events?maxResult=100&singleEvents=true&orderBy=startTime"
        f"&fields=kind,nextPageToken,nextSyncToken,items({EVENT_FIELDS})"
        "&timeMin=2022-03-08T00:31:02&pageToken=page-token-1",
    ]

    json_response(
        {
            "items": [
                {
                    "id": "some-event-id-3",
                    "summary": "Event 3",
                    "description": "Event description 3",
                    "start": {
                        "date": "2022-04-16",
                    },
                    "end": {
                        "date": "2022-04-27",
                    },
                },
            ],
            "nextSyncToken": "sync-token-2",
        }
    )
    await sync.run()
    assert url_request() == [
        "/calendars/some-calendar-id/events?maxResult=100&singleEvents=true&orderBy=startTime"
        f"&fields=kind,nextPageToken,nextSyncToken,items({EVENT_FIELDS})"
        "&timeMin=2022-03-08T00:31:02",
        "/calendars/some-calendar-id/events?maxResult=100&singleEvents=true&orderBy=startTime"
        f"&fields=kind,nextPageToken,nextSyncToken,items({EVENT_FIELDS})"
        "&timeMin=2022-03-08T00:31:02&pageToken=page-token-1",
        "/calendars/some-calendar-id/events?maxResult=100&singleEvents=true&orderBy=startTime"
        f"&fields=kind,nextPageToken,nextSyncToken,items({EVENT_FIELDS})"
        "&syncToken=sync-token-1",
    ]


@freeze_time("2022-04-05 07:31:02", tz_offset=-7)
async def test_sync_datetime_pages(
    event_sync_manager_cb: Callable[[], Awaitable[CalendarEventSyncManager]],
    json_response: ApiResult,
    url_request: Callable[[], str],
) -> None:
    """Test lookup events API."""

    json_response(
        {
            "items": [
                {
                    "id": "some-event-id-1",
                    "summary": "Event 1",
                    "description": "Event description 1",
                    "start": {
                        "dateTime": "2022-04-13T03:00:00",
                    },
                    "end": {
                        "dateTime": "2022-04-13T04:00:00",
                    },
                    "status": "confirmed",
                    "transparency": "transparent",
                },
            ],
            "nextPageToken": "page-token-1",
        }
    )
    json_response(
        {
            "items": [
                {
                    "id": "some-event-id-2",
                    "summary": "Event 2",
                    "description": "Event description 2",
                    "start": {
                        "dateTime": "2022-04-13T05:00:00",
                    },
                    "end": {
                        "dateTime": "2022-04-13T06:00:00",
                    },
                    "transparency": "opaque",
                },
            ],
            "nextSyncToken": "sync-token-1",
        }
    )

    sync = await event_sync_manager_cb()
    await sync.run()
    assert url_request() == [
        "/calendars/some-calendar-id/events?maxResult=100&singleEvents=true&orderBy=startTime"
        f"&fields=kind,nextPageToken,nextSyncToken,items({EVENT_FIELDS})"
        "&timeMin=2022-03-08T00:31:02",
        "/calendars/some-calendar-id/events?maxResult=100&singleEvents=true&orderBy=startTime"
        f"&fields=kind,nextPageToken,nextSyncToken,items({EVENT_FIELDS})"
        "&timeMin=2022-03-08T00:31:02&pageToken=page-token-1",
    ]

    json_response(
        {
            "items": [
                {
                    "id": "some-event-id-3",
                    "summary": "Event 3",
                    "description": "Event description 3",
                    "start": {
                        "dateTime": "2022-04-13T05:30:00",
                    },
                    "end": {
                        "dateTime": "2022-04-13T06:00:00",
                    },
                },
            ],
            "nextSyncToken": "sync-token-2",
        }
    )
    await sync.run()
    assert url_request() == [
        "/calendars/some-calendar-id/events?maxResult=100&singleEvents=true&orderBy=startTime"
        f"&fields=kind,nextPageToken,nextSyncToken,items({EVENT_FIELDS})"
        "&timeMin=2022-03-08T00:31:02",
        "/calendars/some-calendar-id/events?maxResult=100&singleEvents=true&orderBy=startTime"
        f"&fields=kind,nextPageToken,nextSyncToken,items({EVENT_FIELDS})"
        "&timeMin=2022-03-08T00:31:02&pageToken=page-token-1",
        "/calendars/some-calendar-id/events?maxResult=100&singleEvents=true&orderBy=startTime"
        f"&fields=kind,nextPageToken,nextSyncToken,items({EVENT_FIELDS})"
        "&syncToken=sync-token-1",
    ]


@freeze_time("2022-04-05 07:31:02", tz_offset=-7)
async def test_invalidated_sync_token(
    event_sync_manager_cb: Callable[[], Awaitable[CalendarEventSyncManager]],
    json_response: ApiResult,
    response: ResponseResult,
    url_request: Callable[[], str],
    request_reset: Callable[[], str],
) -> None:
    """Test lookup events API."""

    json_response(
        {
            "items": [
                {
                    "id": "some-event-id-1",
                    "summary": "Event 1",
                    "description": "Event description 1",
                    "start": {
                        "date": "2022-04-13",
                    },
                    "end": {
                        "date": "2022-04-14",
                    },
                },
                {
                    "id": "some-event-id-2",
                    "summary": "Event 2",
                    "description": "Event description 2",
                    "start": {
                        "date": "2022-04-15",
                    },
                    "end": {
                        "date": "2022-04-20",
                    },
                },
            ],
            "nextSyncToken": "sync-token-1",
        }
    )

    sync = await event_sync_manager_cb()
    await sync.run()
    assert url_request() == [
        "/calendars/some-calendar-id/events?maxResult=100&singleEvents=true&orderBy=startTime"
        f"&fields=kind,nextPageToken,nextSyncToken,items({EVENT_FIELDS})"
        "&timeMin=2022-03-08T00:31:02"
    ]

    result = await sync.store_service.async_list_events(LocalListEventsRequest())
    assert result.events == [
        Event(
            id="some-event-id-1",
            summary="Event 1",
            description="Event description 1",
            start=DateOrDatetime(date=datetime.date(2022, 4, 13)),
            end=DateOrDatetime(date=datetime.date(2022, 4, 14)),
        ),
        Event(
            id="some-event-id-2",
            summary="Event 2",
            description="Event description 2",
            start=DateOrDatetime(date=datetime.date(2022, 4, 15)),
            end=DateOrDatetime(date=datetime.date(2022, 4, 20)),
        ),
    ]

    request_reset()
    response(aiohttp.web.Response(status=410))  # Token invalid
    json_response(
        {
            "items": [
                {
                    "id": "some-event-id-3",
                    "summary": "Event 3",
                    "description": "Event description 3",
                    "start": {
                        "date": "2022-04-12",
                    },
                    "end": {
                        "date": "2022-04-13",
                    },
                },
            ],
            "nextSyncToken": "sync-token-2",
        }
    )
    await sync.run()
    assert url_request() == [
        "/calendars/some-calendar-id/events?maxResult=100&singleEvents=true&orderBy=startTime"
        f"&fields=kind,nextPageToken,nextSyncToken,items({EVENT_FIELDS}"
        ")&syncToken=sync-token-1",
        "/calendars/some-calendar-id/events?maxResult=100&singleEvents=true&orderBy=startTime"
        f"&fields=kind,nextPageToken,nextSyncToken,items({EVENT_FIELDS})"
        "&timeMin=2022-03-08T00:31:02",
    ]
    result = await sync.store_service.async_list_events(LocalListEventsRequest())
    assert result.events == [
        Event(
            id="some-event-id-3",
            summary="Event 3",
            description="Event description 3",
            start=DateOrDatetime(date=datetime.date(2022, 4, 12)),
            end=DateOrDatetime(date=datetime.date(2022, 4, 13)),
        ),
    ]


@freeze_time("2022-04-05 07:31:02", tz_offset=-7)
async def test_token_version_invalidation(
    event_sync_manager_cb: Callable[[], Awaitable[CalendarEventSyncManager]],
    json_response: ApiResult,
    url_request: Callable[[], str],
    request_reset: Callable[[], str],
) -> None:
    """Test lookup events API."""

    json_response(
        {
            "items": [
                {
                    "id": "some-event-id-1",
                    "summary": "Event 1",
                    "description": "Event description 1",
                    "start": {
                        "date": "2022-04-13",
                    },
                    "end": {
                        "date": "2022-04-14",
                    },
                    "status": "confirmed",
                    "transparency": "transparent",
                },
            ],
            "nextSyncToken": "sync-token-1",
        }
    )
    sync = await event_sync_manager_cb()
    await sync.run()
    assert url_request() == [
        "/calendars/some-calendar-id/events?maxResult=100&singleEvents=true&orderBy=startTime"
        f"&fields=kind,nextPageToken,nextSyncToken,items({EVENT_FIELDS})"
        "&timeMin=2022-03-08T00:31:02"
    ]

    result = await sync.store_service.async_list_events(LocalListEventsRequest())
    assert len(result.events) == 1
    assert result.events[0].id == "some-event-id-1"

    request_reset()
    json_response(
        {
            "items": [
                {
                    "id": "some-event-id-2",
                    "summary": "Event 2",
                    "description": "Event description 2",
                    "start": {
                        "date": "2022-04-15",
                    },
                    "end": {
                        "date": "2022-04-20",
                    },
                    "transparency": "opaque",
                },
            ],
            "nextSyncToken": "sync-token-2",
        }
    )

    with patch("gcal_sync.event_sync.VERSION", VERSION + 1):
        await sync.run()

    assert url_request() == [
        "/calendars/some-calendar-id/events?maxResult=100&singleEvents=true&orderBy=startTime"
        f"&fields=kind,nextPageToken,nextSyncToken,items({EVENT_FIELDS})"
        "&timeMin=2022-03-08T00:31:02"
    ]
    result = await sync.store_service.async_list_events(LocalListEventsRequest())
    assert len(result.events) == 1
    assert result.events[0].id == "some-event-id-2"


@freeze_time("2022-04-05 07:31:02", tz_offset=-7)
async def test_canceled_events(
    event_sync_manager_cb: Callable[[], Awaitable[CalendarEventSyncManager]],
    json_response: ApiResult,
) -> None:
    """Test lookup events API."""

    json_response(
        {
            "items": [
                {
                    "id": "some-event-id-1",
                    "summary": "Event 1",
                    "description": "Event description 1",
                    "start": {
                        "date": "2022-04-13",
                    },
                    "end": {
                        "date": "2022-04-14",
                    },
                    "status": "confirmed",
                },
                {
                    "id": "some-event-id-2",
                    "summary": "Event 2",
                    "description": "Event description 2",
                    "start": {
                        "date": "2022-04-15",
                    },
                    "end": {
                        "date": "2022-04-20",
                    },
                },
            ],
            "nextSyncToken": "sync-token-1",
        }
    )

    sync = await event_sync_manager_cb()
    await sync.run()
    result = await sync.store_service.async_list_events(
        LocalListEventsRequest(
            start_time=datetime.datetime.fromisoformat("0001-01-01T00:00:00"),
        )
    )
    assert result.events == [
        Event(
            id="some-event-id-1",
            summary="Event 1",
            description="Event description 1",
            start=DateOrDatetime(date=datetime.date(2022, 4, 13)),
            end=DateOrDatetime(date=datetime.date(2022, 4, 14)),
        ),
        Event(
            id="some-event-id-2",
            summary="Event 2",
            description="Event description 2",
            start=DateOrDatetime(date=datetime.date(2022, 4, 15)),
            end=DateOrDatetime(date=datetime.date(2022, 4, 20)),
        ),
    ]
    json_response(
        {
            "items": [
                {
                    "id": "some-event-id-1",
                    "status": "cancelled",
                },
                {
                    "id": "some-event-id-3",
                    "summary": "Event 3",
                    "description": "Event description 3",
                    "start": {
                        "date": "2022-04-15",
                    },
                    "end": {
                        "date": "2022-04-20",
                    },
                },
            ],
            "nextSyncToken": "sync-token-2",
        }
    )
    await sync.run()
    result = await sync.store_service.async_list_events(
        LocalListEventsRequest(
            start_time=datetime.datetime.fromisoformat("0001-01-01T00:00:00"),
        )
    )
    assert result.events == [
        Event(
            id="some-event-id-2",
            summary="Event 2",
            description="Event description 2",
            start=DateOrDatetime(date=datetime.date(2022, 4, 15)),
            end=DateOrDatetime(date=datetime.date(2022, 4, 20)),
        ),
        Event(
            id="some-event-id-3",
            summary="Event 3",
            description="Event description 3",
            start=DateOrDatetime(date=datetime.date(2022, 4, 15)),
            end=DateOrDatetime(date=datetime.date(2022, 4, 20)),
        ),
    ]