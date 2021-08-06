import queue
from multiprocessing import Event, Process, Queue


class AbortError(Exception):
    """User canceled the operation."""


class ResultProcess(Process):
    """A process + internal queue to get target result in other process."""

    def __init__(self, target, **kwargs) -> None:
        self._real_target = target
        self._result_queue: Queue = Queue()
        self._failed = Event()
        kwargs.setdefault("daemon", True)
        super().__init__(target=self._wrapper, **kwargs)

    def _wrapper(self, *args, **kwargs) -> None:
        try:
            self._result_queue.put(self._real_target(*args, **kwargs))
        except BaseException as ex:
            self._failed.set()
            self._result_queue.put(ex)

    def abort(self) -> None:
        """Cancel process execution."""
        self.kill()
        self._failed.set()
        self._result_queue.put(AbortError())

    def get_result(self, timeout: float = None, kill: bool = True):
        """Return target result."""
        try:
            result = self._result_queue.get(timeout=timeout)
        except queue.Empty as ex:
            if kill:
                self.kill()
            raise TimeoutError("Operation timed out.") from ex
        if self._failed.is_set():
            raise result
        return result
