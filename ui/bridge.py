"""이벤트 펌프 — root.after로 주기적으로 on_tick을 호출한다.

워커 스레드(인덱서/Tail/필터)가 큐에 넣은 엔진 이벤트를 메인 스레드에서 안전하게
드레인하기 위한 단일 타이머. App이 on_tick에서 모든 탭의 engine.poll_events()를
드레인해 각 탭으로 라우팅한다.
"""

from __future__ import annotations

from collections.abc import Callable


class EventPump:
    def __init__(self, root, on_tick: Callable[[], None], interval_ms: int = 40):
        self.root = root
        self.on_tick = on_tick
        self.interval_ms = interval_ms
        self._id = None
        self._running = False

    def start(self) -> None:
        self._running = True
        self._schedule()

    def _schedule(self) -> None:
        if self._running:
            self._id = self.root.after(self.interval_ms, self._run)

    def _run(self) -> None:
        try:
            self.on_tick()
        finally:
            self._schedule()

    def stop(self) -> None:
        self._running = False
        if self._id is not None:
            try:
                self.root.after_cancel(self._id)
            except Exception:
                pass
            self._id = None
