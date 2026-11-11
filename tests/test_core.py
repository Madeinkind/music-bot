"""Быстрые проверки логики без сети и Discord."""

from __future__ import annotations

from music.queue import Queue, QueueFull
from music.track import Track
from music.ytdl import YTDLSource, is_playlist_url, is_url
from utils.formatting import format_duration, progress_bar, truncate


def make_track(title: str = "Трек", duration: int = 180) -> Track:
    return Track(
        title=title,
        webpage_url=f"https://example.com/{title}",
        duration=duration,
        requester_id=1,
        requester_name="tester",
    )


def test_format_duration() -> None:
    assert format_duration(0) == "0:00"
    assert format_duration(59) == "0:59"
    assert format_duration(60) == "1:00"
    assert format_duration(3599) == "59:59"
    assert format_duration(3600) == "1:00:00"
    assert format_duration(3661) == "1:01:01"


def test_truncate() -> None:
    assert truncate("коротко", 20) == "коротко"
    assert truncate("0123456789", 5) == "0123…"
    assert len(truncate("0123456789", 5)) == 5


def test_progress_bar() -> None:
    assert progress_bar(0, 100) == "🔘" + "─" * 13
    assert progress_bar(100, 100) == "█" * 14
    assert progress_bar(10, 0) == ""


def test_track_duration_text() -> None:
    assert make_track(duration=75).duration_text == "1:15"
    live = Track(title="Live", webpage_url="https://example.com/live", is_live=True)
    assert live.duration_text == "🔴 в эфире"


def test_queue_order_and_remove() -> None:
    queue = Queue(max_size=5)
    first, second = make_track("first"), make_track("second")
    assert queue.add_many([first, second]) == 2
    assert queue.peek() is first
    assert queue.remove(1) is second
    assert queue.pop() is first
    assert not queue


def test_queue_limit() -> None:
    queue = Queue(max_size=2)
    assert queue.add_many([make_track(str(index)) for index in range(5)]) == 2
    assert queue.is_full
    try:
        queue.add(make_track("third"))
    except QueueFull:
        pass
    else:  # pragma: no cover
        raise AssertionError("QueueFull не выброшен")


def test_queue_pagination() -> None:
    queue = Queue(max_size=100)
    queue.add_many([make_track(str(index)) for index in range(25)])
    page, number, pages = queue.page(2, 10)
    assert number == 2
    assert pages == 3
    assert len(page) == 10
    assert page[0].title == "10"

    page, number, pages = queue.page(99, 10)
    assert number == 3
    assert len(page) == 5


def test_queue_shuffle_keeps_tracks() -> None:
    queue = Queue(max_size=100)
    tracks = [make_track(str(index)) for index in range(10)]
    queue.add_many(tracks)
    queue.shuffle()
    assert sorted(track.title for track in queue) == sorted(track.title for track in tracks)


def test_url_helpers() -> None:
    assert is_url("https://youtu.be/dQw4w9WgXcQ")
    assert not is_url("never gonna give you up")
    assert is_playlist_url("https://www.youtube.com/playlist?list=PL123")
    assert not is_playlist_url("https://youtu.be/dQw4w9WgXcQ")


def test_friendly_errors() -> None:
    message = YTDLSource._friendly_error("Sign in to confirm you're not a bot")
    assert "cookies" in message.lower()
    assert "приватное" in YTDLSource._friendly_error("This video is private")


def test_reply_does_not_pass_none_view() -> None:
    """Регрессия: send_message(view=None) падал с AttributeError в discord.py."""

    import asyncio
    import types

    from cogs.music import _reply
    from utils import embeds

    class Response:
        def __init__(self) -> None:
            self.done = False
            self.payload: dict[str, object] | None = None

        def is_done(self) -> bool:
            return self.done

        async def send_message(self, **kwargs: object) -> None:
            self.payload = kwargs

    response = Response()
    ctx = types.SimpleNamespace(interaction=types.SimpleNamespace(response=response))

    asyncio.run(_reply(ctx, embeds.info("проверка"), ephemeral=True))

    assert response.payload is not None
    assert "view" not in response.payload
    assert response.payload["ephemeral"] is True

