# -*- coding: utf-8 -*-

import datetime
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

from twactor import cache, connection, json, log


class User(cache.CachedObject):
    
    """Get info on a twitter user."""
    
    STATUS_UPDATE_INTERVAL = 3 * 60 # 3 minutes between each status update.
    
    def __init__(self, username_or_id, *args, **kwargs):
        if isinstance(username_or_id, basestring):
            self._cache['screen_name'] = username_or_id.decode('utf-8')
        elif isinstance(username_or_id, (int, long)):
            self._cache['id'] = username_or_id
        self.profile = UserProfile(self)
    
    def __eq__(self, user):
        if not isinstance(user, (User, UserProfile)):
            return False
        elif isinstance(user, User):
            return self.username == user.username
        elif isinstance(user, UserProfile):
            return self == user.user
    
    def __repr__(self):
        return 'User(%r)' % (self._identifier,)
    
    @classmethod
    def me(cls):
        return cls(cls._connection_broker.username)
        
    def _update_cache(self):
        logger = log.getLogger('twactor.User.update')
        logger.debug('Updating cache for user %s' % (self._identifier,))
        try:
            data = self._connection_broker.get('/users/show/%s.json' % (
                self._identifier,))
        except Exception, exc:
            # TODO: implement better error handling.
            logger.error('Error fetching user info for %s' % (
                self._identifier,))
        else:
            self._cache = data
    
    @property
    def _identifier(self):
        return self._cache.get('screen_name',
            self._cache.get('id', None) or '')
    
    @property
    @cache.update_on_time(STATUS_UPDATE_INTERVAL)
    def status(self):
        status_data = self._cache['status'].copy()
        status_data['user'] = self._cache.copy()
        status_data['user'].pop('status')
        return Tweet(status_data['id'], cache=status_data
            )._with_connection_broker(self._connection_broker)
    
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
    
    id = cache.simple_map('id')
    username = cache.simple_map('screen_name')
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


class UserProfile(cache.CachedMirror):
    
    _mirrored_attribute = 'user'
    
    def __eq__(self, profile):
        if not isinstance(profile, (User, UserProfile)):
            return False
        elif isinstance(profile, UserProfile):
            return profile.user == self.user
        elif isinstance(profile, User):
            return profile == self.user
    
    def __repr__(self):
        return 'UserProfile(%r)' % (self.user,)
    
    bg_color = cache.simple_map('profile_background_color')
    bg_image_url = cache.simple_map('profile_background_image_url')
    bg_title = cache.simple_map('profile_background_title')
    avatar_url = cache.simple_map('profile_image_url')
    link_color = cache.simple_map('profile_link_color')
    sidebar_border_color = cache.simple_map('profile_sidebar_border_color')
    sidebar_fill_color = cache.simple_map('profile_sidebar_fill_color')
    text_color = cache.simple_map('profile_text_color')


class Tweet(cache.CachedObject):
    
    def __init__(self, id, *args, **kwargs):
        try:
            id = int(id)
        except TypeError:
            pass
        else:
            self._cache['id'] = id
    
    def __eq__(self, tweet):
        if not isinstance(tweet, Tweet):
            return False
        return tweet.id == self.id
    
    def __repr__(self):
        return 'Tweet(%r)' % (self.id,)
    
    def _update_cache(self):
        logger = log.getLogger('twactor.Tweet.update')
        logger.debug('Updating cache for tweet %d' % (self.id,))
        try:
            data = self._connection_broker.get(
                '/statuses/show/%d.json' % (self.id,))
        except Exception, exc:
            # TODO: implement better error handling.
            logger.error('Error fetching info for tweet ID %d' % (self.id,))
        else:
            self._cache = data
    
    @property
    @cache.update_on_key('user')
    def user(self):
        return User(self._cache['user']['screen_name'],
            cache=self._cache['user'])._with_connection_broker(
                self._connection_broker)
    
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
    @cache.update_on_key('in_reply_to_status_id')
    def in_reply_to(self):
        if not self._cache['in_reply_to_status_id']:
            return
        cache = {'id': self._cache['in_reply_to_status_id']}
        cache['user'] = {'id': self._cache['in_reply_to_user_id']}
        return Tweet(self._cache['in_reply_to_status_id']
            )._with_connection_broker(self._connection_broker)
    
    id = cache.simple_map('id')
    text = cache.simple_map('text')
    truncated = cache.simple_map('truncated')


class PublicTimeline(cache.ForwardCachedList):
    
    OBJ_CLASS = Tweet
    UPDATE_INTERVAL = 60
    
    _sort_attrs = ('id',)
    
    def __len__(self):
        return len(self._cache)
    
    def __repr__(self):
        return 'PublicTimeline()'
    
    def _update_cache(self):
        logger = log.getLogger('twactor.PublicTimeline.update')
        logger.debug('Updating public timeline')
        try:
            return self._connection_broker.get('/statuses/public_timeline.json')
        except Exception, exc:
            # TODO: implement better error handling.
            logger.error('Error fetching public timeline update')


class UserTimeline(cache.ForwardCachedList):
    
    OBJ_CLASS = Tweet
    
    # Too low and we make too many API calls. Too high and it takes too long to
    # fetch the data. 100 is a reasonable amount, which can be changed at any
    # time by just setting the attribute.
    _count = 100
    
    def __init__(self, *args, **kwargs):
        user = None
        if args:
            user = args[0]
        if not user:
            user = User.me()
        self.user = user
    
    def __getitem__(self, pos_or_slice):
        new_timeline = super(UserTimeline, self).__getitem__(pos_or_slice)
        if isinstance(new_timeline, UserTimeline):
            new_timeline.user = self.user
        return new_timeline
    
    def __len__(self):
        return self.user._status_count
    
    def __repr__(self):
        return 'UserTimeline(%r)' % (self.user,)
    
    def __str__(self):
        return self.user.username.encode('utf-8')

    def __unicode__(self):
        return self.user.username
    
    def _copy(self):
        copy = type(self)(self.user, cache=self._cache[:],
            updated=self._updated.copy())
        copy._connection_broker = self._connection_broker
        return copy
    
    def _update_cache(self):
        logger = log.getLogger('twactor.UserTimeline.update')
        if ((time.time() - self._updated.get('__time', 0)) <
            self.UPDATE_INTERVAL):
            return []
        logger.debug('Updating data for user %s' % (self.user.username,))
        params = {'count': self._count}
        if self._cache:
            params['since_id'] = self._cache[-1]['id']
        path = '/statuses/user_timeline/%s.json' % (self.user.username,)
        try:
            data = self._connection_broker.get(path, params=params)
        except Exception, exc:
            # TODO: implement better error handling.
            logger.error('Error fetching user timeline update')
        else:
            logger.debug('Data for %s fetched' % (self.user.username,))
            return data


class UserHistory(cache.ReverseCachedList):
    
    OBJ_CLASS = Tweet
    
    # Too low and we make too many API calls. Too high and it takes too long to
    # fetch the data. 100 is a reasonable amount, which can be changed at any
    # time by just setting the attribute.
    _count = 100
    
    def __init__(self, *args, **kwargs):
        user = None
        if args:
            user = args[0]
        if not user:
            user = User.me()
        elif isinstance(user, (basestring, int, long)):
            user = User(user)
        self.user = user
        self._cache_page = kwargs.get('cache_page', 1)
    
    def __getitem__(self, pos_or_slice):
        new_history = super(UserHistory, self).__getitem__(pos_or_slice)
        if isinstance(new_history, UserHistory):
            new_history.user = self.user
        return new_history
    
    def __len__(self):
        return self.user._status_count
    
    def __repr__(self):
        return 'UserHistory(%r)' % (self.user,)
    
    def __str__(self):
        return self.user.username.encode('utf-8')
    
    def __unicode__(self):
        return self.user.username
    
    def _copy(self):
        copy = type(self)(self.user, cache=self._cache[:],
            updated=self._updated.copy())
        copy._connection_broker = self._connection_broker
        return copy
    
    def _update_cache(self):
        logger = log.getLogger('twactor.UserHistory.update')
        logger.debug('Updating data for user %s' % (self.user.username,))
        path = '/statuses/user_timeline/%s.json' % (self.user.username,)
        params = {'page': self._cache_page, 'count': self._count}
        try:
            data = self._connection_broker.get(path, params=params)
        except Exception, exc:
            # TODO: implement better error handling.
            logger.error('Error fetching data')
        else:
            logger.debug('Data for %s fetched' % (self.user.username,))
            self._cache_page += 1
            return data


class UserFollowers(cache.CachedObject):
    pass # TODO: implement.


class UserFollowing(cache.CachedObject):
    pass # TODO: implement


class UserDirectMessages(object):
    pass # TODO: implement