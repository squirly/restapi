from functools import wraps
from dateutil import parser
import time
from inspect import getmembers


class UNSET(object):
    __repr__ = lambda x: 'UNSET'
    __nonzero__ = lambda x: False
UNSET = UNSET()


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


class ValidationError(Exception):
    def __init__(self, message='', obj=None, attribute=None):
        self.message = message
        self.obj = obj
        self.attribute = attribute

    def get_class(self):
        return self.error.obj.__class__.__name__ if self.error.obj else None

    def __str__(self, show_object=True):
        message = ''
        if show_object and self.obj:
            message += self.obj.__class__.__name__ + ': '
        if self.attribute:
            message += self.attribute + ' '
        message += self.message
        return message


class ValidationErrors(Exception):
    def __init__(self, errors):
        if len(errors) == 0:
            raise ValueError('Errors cannot be empty')
        self.errors = errors

    def error_dict(self):
        messages = {}
        for error in self.errors:
            obj = error.obj.__class__.__name__ if hasattr(error, 'obj') else ''
            value = messages.get(obj, [])
            value.append(error.__str__(show_object=False))
            messages[obj] = value
        return messages

    def __str__(self, *a, **k):
        messages = self.error_dict()
        final_message = messages.pop('', [])
        for obj, message in messages.items():
            final_message.append(obj + ': ' + ', '.join(message))
        return '. '.join(final_message)


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


class Field(object):
    type = None
    default = UNSET

    def __init__(self, value_type=None, required=True, null=False, **kwargs):
        if value_type is not None:
            self.type = value_type
        if 'default' in kwargs:
            self.default = kwargs['default']
        self.required = required
        self.null = null

    def hydrate(self, value):
        if value is None:
            return None
        return self.type(value)

    def dehydrate(self, value):
        return value

    def validate(self, value, obj):
        if not isinstance(value, self.type):
            type_name = self.type.__name__
            ValidationError('value not of type ' + type_name)


class StringField(Field):
    type = unicode


class IntegerField(Field):
    type = int


class FloatField(Field):
    type = float


class BooleanField(Field):
    type = bool


class ListField(Field):
    type = list
    default = []


class DictionaryField(Field):
    type = dict
    default = UNSET


class ResourceField(Field):
    @property
    def default(self):
        return self.type()

    def hydrate(self, value):
        if isinstance(value, self.type):
            return value
        return self.type(**value)

    def dehydrate(self, value):
        return value.get_dict()

    def validate(self, value):
        super(ResourceField, self).validate(value)
        value.validate()


class ResourceListField(ResourceField):
    default = []

    def __init__(self, *args, **kwargs):
        pass

    def hydrate(self, value):
        return map(super(ResourceListField, self).hydrate, value)

    def dehydrate(self, value):
        return map(super(ResourceListField, self).dehydrate, value)

    def validate(self, value):
        return map(super(ResourceListField, self).validate, value)


class DateTimeField(Field):
    def __init__(self, datetime_format=None, *args, **kwargs):
        self.datetime_format = datetime_format
        super(DateTimeField, self).__init__(*args, **kwargs)

    def hydrate(self, value):
        return parser.parse(value)

    def dehydrate(self, value):
        return value.strftime(self.datetime_format) \
            if self.datetime_format \
            else time.mktime(value.timetuple())
