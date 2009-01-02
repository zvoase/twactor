# -*- coding: utf-8 -*-

try:
    import json
except ImportError:
    try:
        import simplejson as json
    except ImportError:
        from django.utils import simplejson as json

propertyfix = lambda method: property(**method())

global function_sync

def function_sync(from_fun, to_fun):
    """
    Copy name and documentation from one function to another.

    This function accepts two functional arguments, ``from_fun`` and ``to_fun``,
    and copies the function name and documentation string from the first to the
    second, returning the second. This is useful when writing decorators which
    wrap a function - the wrapped function will keep the metadata of the old
    one.
    """
    to_fun.__name__ = from_fun.__name__
    to_fun.__doc__ = from_fun.__doc__
    return to_fun

__all__ = ['cache', 'connection', 'function_sync', 'json', 'log', 'models',
    'propertyfix']