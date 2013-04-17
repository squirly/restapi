from functools import wraps
from inspect import getmembers

from restapi.fields import UNSET, Field
from restapi.errors import ValidationError, ValidationErrors


class ResponseHook(object):
    DEBUG = 'debug'
    WARNING = 'warning'
    ERROR = 'error'

    log = None

    def __call__(self, response, **kwargs):
        level = None
        status_code = response.status_code
        if 200 <= status_code and status_code <= 299:
            level = self.handle_sucess(response)
        elif 400 <= status_code and status_code <= 499:
            level = self.handle_client_error(response)
        elif 500 <= status_code and status_code <= 599:
            level = self.handle_server_error(response)
        if level:
            self.log_response(response, level)

    def null_log(self, *args, **kwargs):
        pass

    def handle_sucess(self, response):
        return self.DEBUG

    def handle_client_error(self, response):
        return self.WARNING

    def handle_server_error(self, response):
        return self.ERROR

    def log_response(self, response, level):
        request = response.request
        response_log = 'Response {code}: {content}.'.format(
            code=response.status_code,
            content=response.content)
        request_log = 'Request {method} {url} with {data}.'.format(
            method=request.method,
            url=request.url,
            data=getattr(request, 'body', ''))
        log_function = getattr(self.log, level, self.null_log)
        log_function(request_log + '\n' + response_log, extra={
            'request': request,
            'response': response
        })


class ApiObjectMeta(object):
    def __init__(self, attributes):
            self.attributes = attributes


class ApiObject(object):
    uri = 'resource_uri'

    @classmethod
    def get_meta(cls):
        attributes = {}
        for name, attribute in getmembers(cls):
            if not name.startswith('__'):
                if isinstance(attribute, Field):
                    attributes[name] = attribute
        cls._meta = ApiObjectMeta(attributes)
        return cls._meta

    def __new__(cls, *args, **kwargs):
        meta = cls.get_meta()
        values = {}
        if cls.uri in kwargs:
            values['uri'] = kwargs.pop(cls.uri)
        for attr, field in meta.attributes.items():
            value = kwargs.pop(attr, field.default)
            if value is not UNSET:
                values[attr] = field.hydrate(value)
        obj = object.__new__(cls)
        map(lambda attr: setattr(obj, attr, UNSET), meta.attributes.keys())
        obj.__init__(*args, **kwargs)
        obj.__dict__.update(values)
        return obj

    def validate(self):
        errors = []
        for attribute, field in self._meta.attributes.items():
            try:
                value = getattr(self, attribute, UNSET)
                if value is UNSET:
                    if field.required:
                        raise ValidationError('cannot be empty', self, attribute)
                elif value is None:
                    if not field.null:
                        raise ValidationError('cannot be null', self, attribute)
                else:
                    field.validate(value, self)
            except ValidationError, e:
                e.attribute = attribute
                errors.append(e)
            except ValidationErrors, e:
                errors.append(e)
        raise ValidationErrors(errors)

    def get_dict(self):
        values = {}
        for attribute, field in self._meta.attributes.items():
            value = getattr(self, attribute, UNSET)
            if value is not UNSET:
                if value is None:
                    values[attribute] = None
                else:
                    values[attribute] = field.dehydrate(value)
        return values

    @classmethod
    def returns_single(klass, function):
        @wraps(function)
        def return_single(*args, **kwargs):
            item = function(*args, **kwargs)
            if isinstance(item, klass):
                return item
            else:
                return klass(**item)
        return return_single

    @classmethod
    def returns_mutiple(klass, function):
        @wraps(function)
        def return_multiple(*args, **kwargs):
            raw_items = function(*args, **kwargs)
            for item in raw_items:
                if isinstance(item, klass):
                    yield item
                else:
                    yield klass(**item)
        return return_multiple

    def __repr__(self, *args, **kwargs):
        return self.__class__.__name__ + ':' + str(self.get_dict())
