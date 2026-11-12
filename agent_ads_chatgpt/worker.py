from __future__ import annotations

import queue
import threading
import itertools
from concurrent.futures import Future, TimeoutError as FutureTimeoutError

from .errors import ChatGPTError


class BrowserWorker:
    """Keep every synchronous Playwright call on one dedicated thread."""

    _STOP = object()

    def __init__(self, client: object) -> None:
        self.client = client
        self._queue = queue.PriorityQueue()
        self._sequence = itertools.count()
        self._closed = False
        self._active_cancel: threading.Event | None = None
        self._thread = threading.Thread(target=self._run, name="chatgpt-browser", daemon=True)
        self._thread.start()

    def call(
        self,
        method: str,
        *args,
        timeout: int | None = 600,
        priority: int = 0,
        cancel_event: threading.Event | None = None,
    ):
        if threading.current_thread() is self._thread:
            raise ChatGPTError(
                "Lỗi lập trình: không được gọi BrowserWorker.call() từ worker thread."
            )
        if self._closed:
            raise ChatGPTError("Tiến trình ChatGPT đã dừng.")
        future = Future()
        cancel_event = cancel_event or threading.Event()
        self._queue.put((priority, next(self._sequence), method, args, future, cancel_event))
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            cancel_event.set()
            future.cancel()
            raise ChatGPTError(f"ChatGPT không phản hồi sau {timeout} giây.") from exc

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._active_cancel:
            self._active_cancel.set()
        while True:
            try:
                _, _, _, _, future, cancel_event = self._queue.get_nowait()
            except queue.Empty:
                break
            cancel_event.set()
            future.cancel()
        self._queue.put((10**9, next(self._sequence), self._STOP, (), None, None))
        # Browser operations use timeouts of at most 60 seconds. Give the active
        # operation time to observe cancellation and reach client.stop().
        self._thread.join(timeout=75)

    def _run(self) -> None:
        try:
            while True:
                _, _, method, args, future, cancel_event = self._queue.get()
                if method is self._STOP:
                    break
                if not future.set_running_or_notify_cancel():
                    continue
                self._active_cancel = cancel_event
                try:
                    if method == "ask":
                        result = self.client.ask(*args, cancel_event=cancel_event)
                    else:
                        result = getattr(self.client, method)(*args)
                except BaseException as exc:
                    if not future.done():
                        future.set_exception(exc)
                else:
                    if not future.done():
                        future.set_result(result)
                finally:
                    self._active_cancel = None
        finally:
            self.client.stop()
