"""Reuse immutable patch calculations only during one synchronous evaluation.

Nested choice evaluations share the scope, keyed by the actual data object.
Nothing survives the outer call or crosses an Engine worker's context.
"""
from contextvars import ContextVar
from functools import wraps
from inspect import signature


_current = ContextVar('engine_preparation', default=None)


def evaluation_scope(function):
    @wraps(function)
    def scoped(*args, **kwargs):
        if _current.get() is not None:
            return function(*args, **kwargs)
        token = _current.set({})
        try:
            return function(*args, **kwargs)
        finally:
            _current.reset(token)
    return scoped


def patch_calculation(function):
    """Memoize hashable arguments against an immutable DataSnapshot identity."""
    data_index = tuple(signature(function).parameters).index('data')

    @wraps(function)
    def cached(*args, **kwargs):
        scope = _current.get()
        if scope is None:
            return function(*args, **kwargs)
        data = args[data_index] if len(args) > data_index else kwargs['data']
        identity = id(data)
        if identity not in scope:
            # Retain the object, so temporary choice data cannot recycle its id.
            scope[identity] = (data, {})
        memo = scope[identity][1]
        key = (function, args[:data_index] + args[data_index+1:],
               tuple((name, value) for name, value in sorted(kwargs.items()) if name != 'data'))
        if key not in memo:
            memo[key] = function(*args, **kwargs)
        return memo[key]
    return cached
