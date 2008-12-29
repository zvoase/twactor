# -*- coding:utf-8 -*-
# twactor.cache - Cache framework for twactor.

import time


class CachedMetaclass(type):
    
    """Metaclass for subclasses of ``Cached``."""
    
    def __new__(cls, name, bases, attrs):
        update_cache = attrs.get('_update_cache', lambda *args, **kwargs: None)
        def fixed_update_cache(self, *args, **kwargs):
            val = update_cache(self, *args, **kwargs)
            if hasattr(bases[-1], '_update_cache'):
                bases[-1]._update_cache(self, *args, **kwargs)
            return val
        attrs['_update_cache'] = fixed_update_cache
        return type.__new__(cls, name, bases, attrs)


class CachedObject(object):
    
    """Superclass for cached objects."""
    
    __metaclass__ = CachedMetaclass
    
    def __init__(self, *args, **kwargs):
        self._cache = kwargs.pop('cache', {})
        self._updated = {'__count': 0, '__time': 0}
    
    def _update_cache(self, *args, **kwargs):
        self._updated['__count'] = self._updated.get('__count', 0) + 1
        self._updated['__time'] = time.time()


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

def update_once(method):
    """
    Make sure the cache has been updated at least once before calling a method.

    This should be used as a decorator, and it wraps a method on a cached object
    to make sure that the object's cache has been updated at least once before
    the method is called. This allows you to implement lazy evaluation, which
    is especially useful when fetching data over the network.
    """
    def wrapper(self, *args, **kwargs):
        if not self._updated.get('__count', 0):
            self._update_cache()
            self._updated['__count'] = self._updated.get('__count', 0) + 1
        return method(self, *args, **kwargs)
    return function_sync(method, wrapper)

def update_on_key(key, always=False):
    """
    Make sure the cache has a particular key present before calling a method.

    This decorator accepts a key which it will look up in the cache before
    calling the wrapped method. If the cache doesn't have the key, it will
    perform an update before calling the method. Note that it does not keep
    updating the cache until the key is present - this may result in a
    non-terminating loop.

    You may also pass the decorator an additional keyword, ``always``, which
    will tell it whether or not to keep checking for the key every time the
    method is called. By default, this is ``False``, which means that the key
    will be checked only the first time the method is called. If set to true,
    the key will be checked *every* time the method is called.
    """
    def wrapper_deco(method):
        def wrapper(self, *args, **kwargs):
            if always:
                if key not in self._cache:
                    self._update_cache()
                return method(self, *args, **kwargs)
            elif (key not in self._cache and
                (not self._updated.get('key__' + key, False))):
                self._update_cache()
                self._updated['key__' + key] = True
            return method(self, *args, **kwargs)
        return function_sync(method, wrapper)
    return wrapper_deco

def update_on_time(length):
    """
    Update the cache if an amount of time has passed before calling a method.

    This decorator accepts a length of time in seconds, and will wrap a method
    with a cache-checker. Every time the method is called, the wrapper will
    check to see that a certain amount of time has passed. If the time that has
    passed is greater than or equal to the specified length, the cache is
    updated. Finally, the method is called.
    """
    def wrapper_deco(method):
        def wrapper(self, *args, **kwargs):
            if (time.time() - self._updated.get('__time', 0)) >= length:
                self._update_cache()
                self._updated['__time'] = time.time()
            return method(self, *args, **kwargs)
        return function_sync(method, wrapper)
    return wrapper_deco


def update_on_count(num):
    """
    Update the cache if a method has been called a certain number of times.

    This decorator accepts a number, and keeps track of how many times the
    method it is wrapping has been called. When the number of calls reaches this
    number, the cache is updated.
    """
    def wrapper_deco(method):
        def wrapper(self, *args, **kwargs):
            if self._updated.get('count__' + method.__name__, num) == num:
                self._update_cache()
                self._updated['count__' + method.__name__] = 1
            else:
                self._updated['count__' + method] = self._updated.get(
                    'count__' + method, 0) + 1
            return method(self, *args, **kwargs)
        return function_sync(method, wrapper)
    return wrapper_deco


def simple_map(key):
    """
    Shortcut for a typical cacheing use-case.
    
    This is a shortcut for the following pattern::
    
        class SomeCachedObject(CachedObject):
            
            @property
            @update_on_key(key_name)
            def attrname(self):
                return self._cache[key_name]
    
    Instead you can do this::
        
        class SomeCachedObject(CachedObject):
            
            attrname = simple_map(key_name)
    """
    return property(update_on_key(key)(lambda self: self._cache[key]))


def propertyfix(method):
    """Workaround for Python 2.4 and 2.5's ``property``."""
    return property(**method())