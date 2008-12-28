import datetime
import httplib
import logging
import logging.config
import os
import re
import time

import pytz
try:
    import json
except ImportError:
    try:
        import simplejson as json
    except ImportError:
        from django.utils import simplejson as json

# Set up the logger. Consult logging.conf for more information.
logconfig = os.path.join(os.path.dirname(__file__), 'logging.conf')
logging.config.fileConfig(logconfig)


class Cached(object):
    
    """Represent an object with several cached attribtues."""
    
    @staticmethod
    def _update_cache_once(method):
        def wrapper(otherself, *args, **kwargs):
            if not otherself._updated.get(method, False):
                otherself._update_cache()
                otherself._updated[method] = True
            return method(otherself, *args, **kwargs)
        wrapper.__name__ = method.__name__
        wrapper.__doc__ = method.__doc__
        return wrapper
    
    @staticmethod
    def _update_cache_time(length):
        def wrapper_deco(method):
            def wrapper(otherself, *args, **kwargs):
                if (time.time() - otherself._updated.get(method, 0)) > length:
                    otherself._update_cache()
                    otherself._updated[method] = time.time()
                return method(otherself, *args, **kwargs)
            wrapper.__name__ = method.__name__
            wrapper.__doc__ = method.__doc__
            return wrapper
        return wrapper_deco
    
    @staticmethod
    def _update_cache_num(num):
        def wrapper_deco(method):
            def wrapper(otherself, *args, **kwargs):
                if otherself._updated.get(method, num) == num:
                    otherself._update_cache()
                    otherself._updated[method] = 1
                else:
                    otherself._updated[method] += 1
                return method(otherself, *args, **kwargs)
            wrapper.__name__ = method.__name__
            wrapper.__doc__ = method.__doc__
            return wrapper
        return wrapper_deco
    
    @staticmethod
    def _update_cache_key(key):
        def wrapper_deco(method):
            def wrapper(otherself, *args, **kwargs):
                if ((otherself._cache.get(key, None) is None) or
                    not otherself._updated.get(key, True)):
                    otherself._update_cache()
                    otherself._updated[key] = True
                return method(otherself, *args, **kwargs)
            wrapper.__name__ = method.__name__
            wrapper.__doc__ = method.__doc__
            return wrapper
        return wrapper_deco


class User(Cached):
    
    """Get info on a twitter user."""
    
    _update_cache_once = Cached._update_cache_once
    _update_cache_key = Cached._update_cache_key
    _update_cache_time = Cached._update_cache_time
    _update_cache_num = Cached._update_cache_num
    
    _USERNAME = 0
    _ID = 1
    STATUS_UPDATE_INTERVAL = 3 * 60 # 3 minutes between each status update.
    
    def __init__(self, username_or_id, cache={}):
        super(User, self).__init__()
        if isinstance(username_or_id, basestring):
            self._screen_name = username_or_id.decode('utf-8')
            self._identified_by = self._USERNAME
        elif isinstance(username_or_id, int):
            self._id = username_or_id
            self._identified_by = self._ID
        self._cache = cache
        self._updated = {}
        self.profile = UserProfile(self)
        
    def _update_cache(self):
        logger = logging.getLogger('twactor.User.update')
        conn = httplib.HTTPConnection('twitter.com')
        if self._identified_by == self._USERNAME:
            path = '/users/show/%s.json' % (self.username,)
            logger.debug('Updating cache for @%s...' % (self.username,))
        elif self._identified_by == self._ID:
            path = '/users/show/%d.json' % (self.id,)
            logger.debug('Updating cache for user %d...' % (self.id,))
        conn.request('GET', path)
        response = conn.getresponse()
        if response.status == 200:
            self._cache = json.load(response.fp)
        else:
            # TODO: implement better error handling.
            logger.error('Error fetching user info for %s.' % (self.username,))
        
    @property
    def id(self):
        if self._identified_by == self._ID:
            return self._id
        id = self._cache.get('id', None)
        if id:
            return id
        else:
            self._update_cache()
            return self._cache['id']
    
    @property
    def username(self):
        if self._identified_by == self._USERNAME:
            return self._screen_name
        screen_name = self._cache.get('screen_name', None)
        if screen_name:
            return screen_name
        else:
            self._update_cache()
            return self._cache['screen_name']
        
    @property
    @_update_cache_time(STATUS_UPDATE_INTERVAL)
    def status(self):
        status_data = self._cache['status'].copy()
        status_data['user'] = self._cache.copy()
        status_data['user'].pop('status')
        return Tweet(status_data['id'], cache=status_data)
    
    @property
    @_update_cache_key('created_at')
    def joined(self):
        dtime = datetime.datetime.strptime(self._cache['created_at'],
            '%a %b %d %H:%M:%S +0000 %Y')
        return dtime.replace(tzinfo=pytz.utc)
    
    @property
    @_update_cache_key('utc_offset')
    def timezone(self):
        tzinfo = pytz.FixedOffset(self._cache['utc_offset'] / 60.0)
        tzinfo.dst = lambda *args: datetime.timedelta()
        return (self._cache['time_zone'], tzinfo)
    
    @property
    @_update_cache_key('description')
    def description(self):
        return self._cache.get('description')
    
    @property
    @_update_cache_key('location')
    def location(self):
        return self._cache.get('location')
    
    @property
    @_update_cache_key('name')
    def name(self):
        return self._cache.get('name')
    
    @property
    @_update_cache_key('protected')
    def protected(self):
        return self._cache.get('protected')
    
    @property
    @_update_cache_key('url')
    def url(self):
        return self._cache.get('url')
    
    @property
    @_update_cache_key('favourites_count')
    def _favourite_count(self):
        return self._cache.get('favourites_count')
    
    @property
    @_update_cache_key('followers_count')
    def _follower_count(self):
        return self._cache.get('followers_count')
    
    @property
    @_update_cache_key('friends_count')
    def _friend_count(self):
        return self._cache.get('friends_count')
    
    @property
    @_update_cache_key('statuses_count')
    def _status_count(self):
        return self._cache.get('statuses_count')
    
    @property
    @_update_cache_key('time_zone')
    def _time_zone_name(self):
        return self._cache.get('time_zone')
    
    @property
    @_update_cache_key('utc_offset')
    def _time_zone_utc_offset(self):
        return self._cache.get('utc_offset')


class UserProfile(Cached):
    
    _update_cache_once = Cached._update_cache_once
    _update_cache_key = Cached._update_cache_key
    _update_cache_time = Cached._update_cache_time
    _update_cache_num = Cached._update_cache_num
    
    def __init__(self, user):
        super(UserProfile, self).__init__()
        self.user = user
    
    def _get_cache(self):
        return self.user._cache
    
    def _set_cache(self, value):
        self.user._cache = value
    
    _cache = property(_get_cache, _set_cache)
    
    def _get_updated(self):
        return self.user._updated
    
    def _set_updated(self, value):
        self.user._updated = value
    
    _updated = property(_get_updated, _set_updated) 
    
    def _update_cache(self):
        return self.user._update_cache()
    
    @property
    @_update_cache_key('profile_background_color')
    def bg_color(self):
        return self.user._cache.get('profile_background_color')
    
    @property
    @_update_cache_key('profile_background_image_url')
    def bg_image_url(self):
        return self.user._cache.get('profile_background_image_url')
    
    @property
    @_update_cache_key('profile_background_title')
    def bg_title(self):
        return self.user._cache.get('profile_background_title')
    
    @property
    @_update_cache_key('profile_image_url')
    def image_url(self):
        return self.user._cache.get('profile_image_url')
    
    @property
    @_update_cache_key('profile_link_color')
    def link_color(self):
        return self.user._cache.get('profile_link_color')
    
    @property
    @_update_cache_key('profile_sidebar_border_color')
    def sidebar_border_color(self):
        return self.user._cache.get('profile_sidebar_border_color')
    
    @property
    @_update_cache_key('profile_sidebar_fill_color')
    def sidebar_fill_color(self):
        return self.user._cache.get('profile_sidebar_fill_color')
    
    @property
    @_update_cache_key('profile_text_color')
    def text_color(self):
        return self.user._cache.get('profile_text_color')


class UserFollowers(Cached):
    
    def __init__(self, user):
        super(UserFollowers, self).__init__()
        self.user = user
        self._cache = []
        self._cache_page = 0
    
    def __iter__(self):
        pass # TODO: implement.


class UserFeed(object):
    
    def __init__(self, user):
        super(UserFeed, self).__init__()
        self.user = user
        self._cache = []
        self._cache_page = 0
    
    def __iter__(self):
        pass # TODO: implement.
    
    def __len__(self):
        return self.user._status_count
    
    def __getitem__(self, pos):
        while len(self._cache) < (pos + 1):
            self._extend_cache()
        return Tweet(self._cache[pos]['id'], cache=self._cache[pos])
    
    def __getslice__(self, start, end):
        assert (start >= 0 and end >= 0), 'Negative indices not allowed yet!'
        i, slice = start, []
        while i < (end or len(self)):
            slice.append(self[i])
            i += 1
        return slice
    
    def _extend_cache(self):
        logger = logging.getLogger('twactor.UserFeed.update')
        conn = httplib.HTTPConnection('twitter.com')
        if self.user._identified_by == self.user._USERNAME:
            conn.request('GET', '/statuses/user_timeline/%s.json?page=%d' %
                (self.user.username, self._cache_page))
        elif self.user._identified_by == self.user._ID:
            conn.request('GET', '/statuses/user_timeline/%d.json?page=%d' %
                (self.user.id, self._cache_page))
        response = conn.getresponse()
        if response.status == 200:
            self._cache.extend(json.load(response.fp))
            self._cache_page += 1
        else:
            logger.error('Error retrieving statuses for user %s.' %
                (self.user.username,))


class Tweet(Cached):
    
    _update_cache_once = Cached._update_cache_once
    _update_cache_key = Cached._update_cache_key
    _update_cache_time = Cached._update_cache_time
    _update_cache_num = Cached._update_cache_num
    
    def __init__(self, id, cache={}):
        super(Tweet, self).__init__()
        self._id = id
        self._cache = cache
        self._updated = {}
    
    def _update_cache(self):
        logger = logging.getLogger('twactor.Tweet.update')
        logger.debug('Updating cache for tweet %d...' % (self.id,))
        conn = httplib.HTTPConnection('twitter.com')
        conn.request('GET', '/statuses/show/%d.json' % (self.id,))
        response = conn.getresponse()
        if response.status == 200:
            self._cache = json.load(response.fp)
        else:
            # TODO: implement better error handling.
            logger.error('Error fetching info for tweet ID %d.' % (self.id,))
    
    @property
    def id(self):
        return self._id
    
    @property
    @_update_cache_key('user')
    def user(self):
        return User(self._cache['user']['screen_name'],
            cache=self._cache['user'])
    
    @property
    @_update_cache_key('source')
    def source_name(self):
        return re.search(r'>(.*)<', self._cache['source']).groups()[0]
    
    @property
    @_update_cache_key('source')
    def source_url(self):
        return re.search(r'<a href="(.*)">', self._cache['source']).groups()[0]
    
    @property
    @_update_cache_key('created_at')
    def created(self):
        return datetime.datetime.strptime(self._cache['created_at'],
            '%a %b %d %H:%M:%S +0000 %Y').replace(tzinfo=pytz.utc)
    
    @property
    @_update_cache_once
    def in_reply_to(self):
        if not self._cache['in_reply_to_status_id']:
            return
        return Tweet(self._cache['in_reply_to_status_id'])
    
    @property
    @_update_cache_key('text')
    def text(self):
        return self._cache['text']
    
    @property
    @_update_cache_key('truncated')
    def truncated(self):
        return self._cache['truncated']
