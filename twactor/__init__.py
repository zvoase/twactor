try:
    import json
except ImportError:
    try:
        import simplejson as json
    except ImportError:
        from django.utils import simplejson as json

__all__ = ['cache', 'connection', 'log', 'models']