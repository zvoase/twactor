# -*- coding: utf-8 -*-

# For a proper summary of the errors here, consult the following URL:
#
#   http://apiwiki.twitter.com/REST+API+Documentation#HTTPStatusCodes
#

class TwitterError(Exception):
    
    """An error in twitter communications."""
    
    def __init__(self, request, fp, code, message, headers):
        self.request = request
        self.fp = fp
        self.code = code
        self.message = message
        self.headers = headers


class ServerError(TwitterError):
    """An error with twitter, not you."""
    pass


class ClientError(TwitterError):
    """An error with you, not twitter."""
    pass


class APILimitError(ClientError):
    """You've used up too many API calls. Wait a few minutes, then try again."""
    pass


class NotAuthorizedError(ClientError):
    """You have not provided a correct username and password."""
    pass


class ForbiddenError(ClientError):
    """You are authenticated, but not allowed to take an action."""
    pass


class NotFoundError(ClientError):
    """The requested resource was not found."""
    pass


class TwitterServerError(ServerError):
    """There was an unspecified error with twitter's server."""
    pass


class TwitterDownError(ServerError):
    """Twitter is down, or is being upgraded."""
    pass


class TwitterOverloadedError(ServerError):
    """Twitter is overloaded. Try again in another few minutes."""
    pass


CODE_EXCEPTION_MAP = {
    # Client errors
    400: APILimitError,
    401: NotAuthorizedError,
    403: ForbiddenError,
    404: NotFoundError,
    
    # Server errors
    500: TwitterServerError,
    502: TwitterDownError,
    503: TwitterOverloadedError
}