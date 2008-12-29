import datetime
import os
import re

import pytz
try:
    import json
except ImportError:
    try:
        import simplejson as json
    except ImportError:
        from django.utils import simplejson as json

from twactor import cache, connection, json, log


class User(cache.CachedObject):
    
    """Get info on a twitter user."""
    
    STATUS_UPDATE_INTERVAL = 3 * 60 # 3 minutes between each status update.
    
    def __init__(self, username_or_id, cache={}):
        super(User, self).__init__(cache=cache)
        if isinstance(username_or_id, basestring):
            self._screen_name = username_or_id.decode('utf-8')
            self._identified_by = 'username'
        elif isinstance(username_or_id, int):
            self._id = username_or_id
            self._identified_by = 'id'
        self.profile = UserProfile(self)
    
    def __eq__(self, user):
        if not isinstance(user, (User, UserProfile)):
            return False
        elif isinstance(user, User):
            return self.username == user.username
        elif isinstance(user, UserProfile):
            return self == user.user
    
    def _update_cache(self):
        logger = log.getLogger('twactor.User.update')
        cb = connection.DEFAULT_CB
        if self._identified_by == 'username':
            path = '/users/show/%s.json' % (self.username,)
            logger.debug('Updating cache for @%s...' % (self.username,))
        elif self._identified_by == 'id':
            path = '/users/show/%d.json' % (self.id,)
            logger.debug('Updating cache for user %d...' % (self.id,))
        try:
            data = cb.get(path)
        except Exception, exc:
            # TODO: implement better error handling.
            logger.error('Error fetching user info for %s.' % (self.username,))
        else:
            self._cache = data
    
    @property
    def id(self):
        if self._identified_by == 'id':
            return self._id
        id = self._cache.get('id', None)
        if id:
            return id
        else:
            self._update_cache()
            return self._cache['id']
    
    @property
    def username(self):
        if self._identified_by == 'username':
            return self._screen_name
        screen_name = self._cache.get('screen_name', None)
        if screen_name:
            return screen_name
        else:
            self._update_cache()
            return self._cache['screen_name']
    
    @property
    @cache.update_on_time(STATUS_UPDATE_INTERVAL)
    def status(self):
        status_data = self._cache['status'].copy()
        status_data['user'] = self._cache.copy()
        status_data['user'].pop('status')
        return Tweet(status_data['id'], cache=status_data)
    
    @property
    @cache.update_on_key('created_at')
    def joined(self):
        dtime = datetime.datetime.strptime(self._cache['created_at'],
            '%a %b %d %H:%M:%S +0000 %Y')
        return dtime.replace(tzinfo=pytz.utc)
    
    @property
    @cache.update_on_key('utc_offset')
    def timezone(self):
        tzinfo = pytz.FixedOffset(self._cache['utc_offset'] / 60.0)
        tzinfo.dst = lambda *args: datetime.timedelta()
        return (self._cache['time_zone'], tzinfo)
    
    description = cache.simple_map('description')
    location = cache.simple_map('location')
    name = cache.simple_map('name')
    protected = cache.simple_map('protected')
    url = cache.simple_map('url')
    _favourite_count = cache.simple_map('favourites_count')
    _follower_count = cache.simple_map('followers_count')
    _friend_count = cache.simple_map('friends_count')
    _status_count = cache.simple_map('statuses_count')
    _time_zone_name = cache.simple_map('time_zone')
    _time_zone_utc_offset = cache.simple_map('utc_offset')


class UserProfile(cache.CachedObject):
    
    def __init__(self, user):
        # We do not call the parent class's __init__ because this is not a
        # conventional cached object.
        self.user = user
    
    def __eq__(self, profile):
        if not isinstance(profile, (User, UserProfile)):
            return False
        elif isinstance(profile, UserProfile):
            return profile.user == self.user
        elif isinstance(profile, User):
            return profile == self.user
    
    @cache.propertyfix
    def _cache():
        def fget(self):
            return self.user._cache
        def fset(self, value):
            self.user._cache = value
        return locals()
    
    @cache.propertyfix
    def _updated():
        def fget(self):
            return self.user._updated
        def fset(self, value):
            self.user._updated = value
        return locals()
    
    @property
    def _update_cache(self):
        return self.user._update_cache
    
    bg_color = cache.simple_map('profile_background_color')
    bg_image_url = cache.simple_map('profile_background_image_url')
    bg_title = cache.simple_map('profile_background_title')
    avatar_url = cache.simple_map('profile_image_url')
    link_color = cache.simple_map('profile_link_color')
    sidebar_border_color = cache.simple_map('profile_sidebar_border_color')
    sidebar_fill_color = cache.simple_map('profile_sidebar_fill_color')
    text_color = cache.simple_map('profile_text_color')


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
        logger = log.getLogger('twactor.UserFeed.update')
        cb = connection.DEFAULT_CB
        try:
            if self.user._identified_by == self.user._USERNAME:
                data = cb.get('/statuses/user_timeline/%s.json?page=%d' %
                    (self.user.username, self._cache_page))
            elif self.user._identified_by == self.user._ID:
                data = cb.get('/statuses/user_timeline/%d.json?page=%d' %
                    (self.user.id, self._cache_page))
        except Exception, exc:
            logger.error('Error retrieving statuses for user %s.' %
                (self.user.username,))
        else:
            self._cache.extend(data)
            self._cache_page += 1            


class Tweet(cache.CachedObject):
        
    def __init__(self, id, *args, **kwargs):
        super(Tweet, self).__init__(*args, **kwargs)
        self._id = id
    
    def __eq__(self, tweet):
        if not isinstance(tweet, Tweet):
            return False
        return tweet.id == self.id
    
    def _update_cache(self):
        logger = log.getLogger('twactor.Tweet.update')
        logger.debug('Updating cache for tweet %d...' % (self.id,))
        cb = connection.DEFAULT_CB
        try:
            data = cb.get('/statuses/show/%d.json' % (self.id,))
        except Exception, exc:
            # TODO: implement better error handling.
            logger.error('Error fetching info for tweet ID %d.' % (self.id,))
        else:
            self._cache = data
    
    id = property(lambda self: self._id)
    
    @property
    @cache.update_on_key('user')
    def user(self):
        return User(self._cache['user']['screen_name'],
            cache=self._cache['user'])
    
    @property
    @cache.update_on_key('source')
    def source_name(self):
        return re.search(r'>(.*)<', self._cache['source']).groups()[0]
    
    @property
    @cache.update_on_key('source')
    def source_url(self):
        return re.search(r'<a href="(.*)">', self._cache['source']).groups()[0]
    
    @property
    @cache.update_on_key('created_at')
    def created(self):
        return datetime.datetime.strptime(self._cache['created_at'],
            '%a %b %d %H:%M:%S +0000 %Y').replace(tzinfo=pytz.utc)
    
    @property
    @cache.update_once
    def in_reply_to(self):
        if not self._cache['in_reply_to_status_id']:
            return
        return Tweet(self._cache['in_reply_to_status_id'])
    
    text = cache.simple_map('text')
    truncated = cache.simple_map('truncated')