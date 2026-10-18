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
        if len(args) > data_index:
            data = args[data_index]
            rest = args[:data_index] + args[data_index+1:]
        else:
            data = kwargs['data']
            rest = args
        entry = scope.get(id(data))
        if entry is None:
            # Retain the object, so temporary choice data cannot recycle its id.
            entry = scope[id(data)] = (data, {})
        memo = entry[1]
        key = (function, rest,
               tuple((name, value) for name, value in sorted(kwargs.items()) if name != 'data') if kwargs else ())
        try:
            return memo[key]
        except KeyError:
            value = memo[key] = function(*args, **kwargs)
            return value
    return cached


def scoped_reuse(data, key, build):
    """Return one object per hashable key and data identity in the current scope.

    The object may memoize pure results of its own construction inputs; every
    input that changes those results must be part of ``key``. Pass ``None`` as
    data for values that do not depend on a DataSnapshot.
    """
    scope = _current.get()
    if scope is None:
        return build()
    identity = id(data)
    if identity not in scope:
        scope[identity] = (data, {})
    memo = scope[identity][1]
    key = (scoped_reuse, key)
    if key not in memo:
        memo[key] = build()
    return memo[key]
