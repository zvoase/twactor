# -*- coding:utf-8 -*-
# twactor.cache - Cache framework for twactor.

import operator
import time
try:
    import threading
except:
    import dummy_threading as threading

from twactor import connection, function_sync, propertyfix


class CachedMetaclass(type):
    
    """Metaclass for subclasses of ``CachedObject``."""
    
    def __new__(cls, name, bases, attrs):
        
        # Fix _update_cache
        update_cache = attrs.get('_update_cache', lambda *args, **kwargs: None)
        def fixed_update_cache(self, *args, **kwargs):
            val = update_cache(self, *args, **kwargs)
            if hasattr(bases[-1], '_update_cache'):
                bases[-1]._update_cache(self, *args, **kwargs)
            return val
        attrs['_update_cache'] = function_sync(update_cache, fixed_update_cache)
        
        # Fix __init__
        init = attrs.get('__init__', lambda *args, **kwargs: None)
        def fixed_init(self, *args, **kwargs):
            if hasattr(bases[-1], '__init__') and bases[-1] is not object:
                bases[-1].__init__(self, *args, **kwargs)
            init(self, *args, **kwargs)
        attrs['__init__'] = function_sync(init, fixed_init)
        
        return type.__new__(cls, name, bases, attrs)


class CachedObject(object):
    
    """Superclass for cached objects."""
    
    __metaclass__ = CachedMetaclass
    
    _connection_broker = connection.DEFAULT_CB
    
    def __init__(self, *args, **kwargs):
        self._cache = kwargs.pop('cache', {})
        self._updated = kwargs.pop('_updated', {'__count': 0, '__time': 0})
    
    def _update_cache(self, *args, **kwargs):
        self._updated['__count'] = self._updated.get('__count', 0) + 1
        self._updated['__time'] = time.time()
    
    def _with_connection_broker(self, cb):
        copy = self._copy()
        copy._connection_broker = cb
        return copy
    
    def _copy(self):
        return type(self)(self._cache.get('id', None), cache=self._cache.copy(),
            updated=self._updated.copy())


class CachedMirror(object):
    
    """Superclass for objects which rely on another object's cache."""
    
    def __init__(self, mirrored_object):
        setattr(self, self._mirrored_attribute, mirrored_object)
        self._mirrored = mirrored_object
    
    def mirror_attribute(attribute):
        """Shortcut for mirroring an attribute on another object."""
        def attr_methods():
            def fget(self):
                return reduce(getattr, attribute.split('.'), self)
            def fset(self, value):
                setattr(reduce(getattr, attribute.split('.')[:-1], self),
                    attribute.split('.'), value)
            def fdel(self):
                delattr(reduce(getattr, attribute.split('.')[:-1], self),
                    attribute.split('.'))
            return {'fget': fget, 'fset': fset, 'fdel': fdel}
        return property(**attr_methods())
    
    _cache = mirror_attribute('_mirrored._cache')
    _update_cache = mirror_attribute('_mirrored._update_cache')
    _updated = mirror_attribute('_mirrored._updated')
    
    del mirror_attribute


class CachedListMetaclass(type):
    
    def __new__(cls, name, bases, attrs):
        
        # Fix __init__
        init = attrs.get('__init__', lambda *args, **kwargs: None)
        def fixed_init(self, *args, **kwargs):
            for base in reversed(bases):
                if base is object:
                    break
                base.__init__(self, *args, **kwargs)
            init(self, *args, **kwargs)
        attrs['__init__'] = function_sync(init, fixed_init)
        
        # Fix _update_cache
        update_cache = attrs.get('_update_cache', None)
        if not update_cache:
            for base in reversed(bases):
                if hasattr(base, '_update_cache'):
                    update_cache = base._update_cache
                    break
        if update_cache:
            def fixed_update_cache(self, *args, **kwargs):
                data = update_cache(self, *args, **kwargs)
                for base in reversed(bases):
                    if hasattr(base, '_insert_into_cache'):
                        base._insert_into_cache(self, data)
                        break
            attrs['_update_cache'] = function_sync(update_cache,
                fixed_update_cache)
        
        return type.__new__(cls, name, bases, attrs)


class CachedList(object):
    
    __metaclass__ = CachedListMetaclass
    
    _connection_broker = connection.DEFAULT_CB
    _sort_attrs = ('created', 'id')
    _reverse_class = None
    
    OBJ_CLASS = lambda cache: cache
    UPDATE_INTERVAL = 60 * 3 # Three-minute update interval by default.
    
    def __init__(self, *args, **kwargs):
        self._cache = kwargs.pop('cache', [])
        self._object_cache = kwargs.pop('object_cache', {})
        self._updated = kwargs.pop('updated', {'__count': 0, '__time': 0})
        self.update_monitor = CachedListUpdateMonitorThread(self)
    
    def __getitem__(self, pos_or_slice):
        if isinstance(pos_or_slice, (int, long)):
            return self._cache_to_obj(
                self._cache[self._resolve_cache_index(pos_or_slice)])
        start, stop, step = [getattr(pos_or_slice, attr)
            for attr in ('start', 'stop', 'step')]
        start = self._resolve_cache_index(start, start=True)
        stop = self._resolve_cache_index(stop, start=False)
        new_cache = map(self._cache.__getitem__, range(start, stop, step or 1))
        new_updated = {'__count': self._updated['__count'],
            '__time': self._updated['__time']}
        for item in new_cache:
            count_key = '%s__count' % (item.get('id', repr(item)))
            time_key = '%s__time' % (item.get('id', repr(item)))
            new_updated[count_key] = self._updated.get(count_key, None)
            new_updated[time_key] = self._updated.get(time_key, None)
        return type(self)(
            cache=new_cache, updated=new_updated)._with_connection_broker(
                self._connection_broker)
    
    def __delitem__(self, pos_or_slice):
        raise NotImplementedError
    
    def __iter__(self):
        for item in self._cache:
            yield self._cache_to_obj(item)
    
    def __reversed__(self):
        raise NotImplementedError
    
    def __contains__(self, obj):
        if not isinstance(obj, self.OBJ_CLASS):
            return False
        return obj.id in (obj2.id for obj2 in self._objects)
    
    def __len__(self):
        raise NotImplementedError
    
    def _cache_to_obj(self, cache_item):
        if 'id' in cache_item and cache_item['id'] in self._object_cache:
            obj = self._object_cache[cache_item['id']]
        elif 'id' in cache_item and cache_item['id'] not in self._object_cache:
            obj = self.OBJ_CLASS(cache_item['id'], cache=cache_item)
            self._object_cache[cache_item['id']] = obj
        else:
            obj = self.OBJ_CLASS(None, cache=cache_item)
            self._object_cache[repr(obj)] = obj
        if hasattr(obj, '_with_connection_broker'):
            return obj._with_connection_broker(self._connection_broker)
        return obj
    
    def _clean_object_cache(self):
        obj_cache_ids = self._object_cache.keys()
        data_cache_ids = map(operator.attrgetter('id'), self._objects)
        for obj_id in obj_cache_ids:
            if obj_id not in data_cache_ids:
                del self._objects[obj_id]
    
    def _copy(self):
        copy = type(self)(cache=self._cache[:],
            updated=self._updated.copy())
        copy._connection_broker = self._connection_broker
        return copy
    
    @property
    def _objects(self):
        return map(self._cache_to_obj, self._cache)
    
    def _resolve_cache_index(self, index, start=True):
        if index < 0:
            old_length, length = None, len(self._cache)
            while (old_length != length):
                old_length = length
                self._update_cache()
                length = len(self._cache)
            if abs(index) <= length:
                return length + index
            raise IndexError('list index out of range')
        elif (not index) and (index != 0):
            return 0 if start else (len(self._cache) - 1)
        elif index < len(self._cache):
            return index
        old_length, length = None, len(self._cache)
        while (index >= length) and (old_length != length):
            old_length = length
            self._update_cache()
            length = len(self._cache)
        if old_length == length:
            raise IndexError('list index out of range')
        return index
    
    def _sort_key(self, item):
        return operator.attrgetter(*self._sort_attrs)(item)
    
    def _with_connection_broker(self, connection_broker):
        copy = self._copy()
        copy._connection_broker = connection_broker
        return copy


class CachedListUpdateMonitorThread(threading.Thread):
    
    def __init__(self, object, *args, **kwargs):
        super(CachedListUpdateMonitorThread, self).__init__(
            *args, **kwargs)
        self.object = object
        self.kill_flag = False
    
    def run(self):
        while not self.kill_flag:
            self.object._update_cache()
            time.sleep(self.object.UPDATE_INTERVAL)
        self.kill_flag = False
    
    def stop(self):
        self.kill_flag = True


class ForwardCachedList(CachedList):
        
    def _insert_into_cache(self, fetched_data):
        if not fetched_data:
            self._updated['__count'] = self._updated.get('__count', 0) + 1
            self._updated['__time'] = time.time()
            return
        fetched_objects = zip(fetched_data,
            map(self._cache_to_obj, fetched_data))
        sorted_objects = sorted(fetched_objects,
            key=lambda pair: self._sort_key(pair[1]))
        timestamp = time.time()
        if not self._cache:
            for data, object in sorted_objects:
                count_key = '%s__count' % (getattr(object, 'id', repr(object)),)
                time_key = '%s__time' % (getattr(object, 'id', repr(object)),)
                self._updated[count_key] = self._updated.get(count_key, 0) + 1
                self._updated[time_key] = timestamp
            self._cache.extend(pair[0] for pair in sorted_objects)
        else:
            latest_key = self._sort_key(self._cache_to_obj(self._cache[-1]))
            add_to_cache = self._sort_key(sorted_objects[0][1]) > latest_key
            for data, object in sorted_objects:
                count_key = '%s__count' % (getattr(object, 'id', repr(object)),)
                time_key = '%s__time' % (getattr(object, 'id', repr(object)),)
                self._updated[count_key] = self._updated.get(count_key, 0) + 1
                self._updated[time_key] = timestamp
                if add_to_cache or (self._sort_key(object) > latest_key):
                    self._cache.append(data)
                if self._sort_key(object) >= latest_key:
                    add_to_cache = True
        self._updated['__count'] = self._updated.get('__count', 0) + 1
        self._updated['__time'] = time.time()
        self._clean_object_cache()


class ReverseCachedList(CachedList):
    
    def _insert_into_cache(self, fetched_data):
        if not fetched_data:
            self._updated['__count'] = self._updated.get('__count', 0) + 1
            self._updated['__time'] = time.time()
            return
        fetched_objects = zip(fetched_data,
            map(self._cache_to_obj, fetched_data))
        sorted_objects = sorted(fetched_objects, reverse=True,
            key=lambda pair: self._sort_key(pair[1]))
        timestamp = time.time()
        if not self._cache:
            for data, object in sorted_objects:
                count_key = '%s__count' % (getattr(object, 'id', repr(object)),)
                time_key = '%s__time' % (getattr(object, 'id', repr(object)),)
                self._updated[count_key] = self._updated.get(count_key, 0) + 1
                self._updated[time_key] = timestamp
            self._cache.extend(pair[0] for pair in sorted_objects)
        else:
            latest_key = self._sort_key(self._cache_to_obj(self._cache[-1]))
            add_to_cache = self._sort_key(sorted_objects[0][1]) < latest_key
            for data, object in sorted_objects:
                count_key = '%s__count' % (getattr(object, 'id', repr(object)),)
                time_key = '%s__time' % (getattr(object, 'id', repr(object)),)
                self._updated[count_key] = self._updated.get(count_key, 0) + 1
                self._updated[time_key] = timestamp
                if add_to_cache or (self._sort_key(object) < latest_key):
                    self._cache.append(data)
                if self._sort_key(object) <= latest_key:
                    add_to_cache = True
        self._updated['__count'] = self._updated.get('__count', 0) + 1
        self._updated['__time'] = time.time()
        self._clean_object_cache()

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