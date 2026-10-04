"""Task-local access to independently owned chat runtimes.

Bindings are inherited by child tasks. Leaving a binding does not stop or remove
its runtime: lifecycle owners must explicitly drain and retire it.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Generic, Iterator, TypeVar
from functools import wraps
from inspect import signature

T = TypeVar('T')


class CurrentRuntime:
    """Compatibility field access, resolved against task-local ownership."""
    def __init__(self, runtimes):
        object.__setattr__(self, '_runtimes', runtimes)

    def __getattr__(self, name):
        return getattr(self._runtimes.current(), name)

    def __setattr__(self, name, value):
        setattr(self._runtimes.current(), name, value)

    def __delattr__(self, name):
        delattr(self._runtimes.current(), name)


class SessionRuntimes(Generic[T]):
    def __init__(self, factory: Callable[[], T]):
        self._factory = factory
        self._states: dict[str, T] = {}
        self._selected: ContextVar[str] = ContextVar('runtime_chat', default='default')

    def get(self, chat_id: str) -> T:
        if not isinstance(chat_id, str) or not chat_id.strip():
            raise ValueError('Chat identity required')
        if chat_id not in self._states:
            self._states[chat_id] = self._factory()
        return self._states[chat_id]

    def current(self) -> T:
        return self.get(self._selected.get())

    def scoped(self, function):
        """Bind explicit chat_id arguments; nested unscoped RPCs inherit it."""
        parameters = signature(function)

        @wraps(function)
        async def wrapped(*args, **kwargs):
            bound = parameters.bind(*args, **kwargs)
            bound.apply_defaults()
            chat_id = bound.arguments.get('chat_id')
            if chat_id is None:
                return await function(*args, **kwargs)
            with self.bind(chat_id):
                return await function(*args, **kwargs)
        return wrapped

    def selected_chat(self) -> str:
        return self._selected.get()

    def existing(self, chat_id: str) -> T | None:
        """Passive lookup must not allocate a runtime."""
        return self._states.get(chat_id)

    def snapshot(self) -> tuple[tuple[str, T], ...]:
        return tuple(self._states.items())

    @contextmanager
    def bind(self, chat_id: str) -> Iterator[T]:
        state = self.get(chat_id)
        token = self._selected.set(chat_id)
        try:
            yield state
        finally:
            self._selected.reset(token)
