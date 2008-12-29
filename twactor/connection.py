# Manages HTTP requests, responses and connections.

import httplib
import re
import types
import urllib
import urllib2
import urlparse

from twactor import json
from twactor.cache import propertyfix


VALID_USERNAME_RE = re.compile(r'^[A-Za-z0-9_]+$')
VALID_PASSWORD_RE = re.compile(r'^.{6,}$')

SSL_SUPPORTED = hasattr(httplib, 'HTTPS')


def xunique(items, reverse=False):
    def rest(items, i):
        if not reverse:
            return items[:i]
        return items[i+1:]
    i = 0
    while i < len(items):
        if items[i] not in rest(items, i):
            yield items[i]
        i += 1


def unique(*args, **kwargs):
    return list(xunique(*args, **kwargs))


class ConnectionBroker(object):
    
    HTTP_AUTH_REALM = 'Twitter API'
    HTTP_AUTH_URI = 'twitter.com'
    SECURE = SSL_SUPPORTED
    
    DEFAULT_HANDLERS = [urllib2.ProxyHandler, urllib2.UnknownHandler,
        urllib2.HTTPHandler, urllib2.HTTPDefaultErrorHandler,
        urllib2.HTTPRedirectHandler, urllib2.FTPHandler, urllib2.FileHandler,
        urllib2.HTTPErrorProcessor]
    
    if SECURE:
        DEFAULT_HANDLERS.append(urllib2.HTTPSHandler)
    
    extra_handlers = []
    
    def __init__(self, username=None, password=None):
        self._username = username
        self._password = password
        self._update()
    
    @propertyfix
    def username():
        def fget(self):
            return self._username
        def fset(self, value):
            if not VALID_USERNAME_RE.match(value):
                raise ValueError('Invalid username: %r' % (value,))
            self._username = username
            self._update()
        def fdel(self):
            self._username, self._password = None, None
            self._update()
        return locals()
    
    @propertyfix
    def password():
        def fget(self):
            return self._password
        def fset(self, value):
            if not VALID_PASSWORD_RE.match(value):
                raise ValueError('Invalid password: %r' % (value,))
            self._password = password
            self._update()
        def fdel(self):
            self._username, self._password = None, None
            self._update()
        return locals()
    
    @property
    def handlers(self):
        return self._get_handlers()
    
    def _update(self):
        self._http_auth_handler = self._get_http_auth_handler()
        self._opener = self._get_opener()
    
    def _get_http_auth_handler(self):
        if not (self._username and self._password):
            return None
        handler = urllib2.HTTPBasicAuthHandler(
            urllib2.HTTPPasswordMgrWithDefaultRealm())
        handler.add_password(self.HTTP_AUTH_REALM, self.HTTP_AUTH_URI,
            self.username, self.password)
        return handler
    
    def _get_handlers(self, *more_handlers):
        handlers = filter(None, (self.DEFAULT_HANDLERS +
            [self._http_auth_handler] +
            self.extra_handlers +
            list(more_handlers)))
        for (i, handler) in enumerate(handlers):
            if isinstance(handler, (types.ClassType, types.TypeType)):
                handlers[i] = handler()
        return unique(handlers, reverse=True)
    
    def _get_opener(self, *more_handlers):
        handlers = self._get_handlers(*more_handlers)
        opener = urllib2.OpenerDirector()
        for handler in handlers:
            opener.add_handler(handler)
        return opener
    
    def _build_url(self, path, params):
        scheme = 'https' if self.SECURE else 'http'
        netloc = self.HTTP_AUTH_URI
        query = urllib.urlencode(params)
        return urlparse.urlunsplit((scheme, netloc, path, query, ''))
    
    def get(self, path, params={}):
        request = Request(self._build_url(path, params), method='GET')
        connection = self._opener.open(request)
        try:
            if 'json' in connection.info().dict['content-type']:
                return json.load(connection)
            else:
                return connection.read()
        finally:
            connection.close()
    
    def post(self, path, *args, **kwargs):
        params, data = kwargs.pop('params', {}), kwargs.pop('data', {})
        # Deal with content type and POST data.
        if hasattr(data, '__iter__') and not isinstance(data, basestring):
            data = urllib.urlencode(data)
            content_type = 'application/x-www-form-urlencoded'
        else:
            content_type = kwargs.pop('content_type', None)
        headers = kwargs.pop('headers', {})
        if content_type:
            headers['Content-Type'] = content_type
        # Using custom Request object.
        request = Request(self._build_url(path, params), data=data,
            headers=headers, method='POST')
        connection = self._opener.open(request)
        try:
            if 'json' in connection.info().dict['content-type']:
                return json.load(connection)
            else:
                return connection.read()
        finally:
            connection.close()
    
    def delete(self, path, params):
        request = Request(self._build_url(path, params), method='DELETE')
        connection = self._opener.open(request)
        try:
            if 'json' in connection.info().dict['content-type']:
                return json.load(connection)
            else:
                return connection.read()
        finally:
            connection.close()


class Request(urllib2.Request):
    
    def __init__(self, *args, **kwargs):
        if 'method' in kwargs:
            self._set_method = True
            self._method = kwargs.pop('method')
        else:
            self._set_method = False
            self._method = 'GET'
        urllib2.Request.__init__(self, *args, **kwargs)
    
    @propertyfix
    def method():
        def fget(self):
            return self.get_method()
        def fset(self, method):
            self._set_method = True
            self._method = method
        def fdel(self):
            self._set_method = False
            self._method = 'GET'
        return locals()
    
    def get_method(self):
        if self._set_method:
            return self._method
        elif self.has_data():
            return 'POST'
        else:
            return 'GET'


global DEFAULT_CB

DEFAULT_CB = ConnectionBroker()

def configure(*args, **kwargs):
    DEFAULT_CB = ConnectionBroker(*args, **kwargs)