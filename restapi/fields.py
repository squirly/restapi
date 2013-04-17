from dateutil import parser
import time
from restapi.errors import ValidationError


UNSET = type('UNSET', (), {
    '__repr__': lambda x: 'UNSET',
    '__nonzero__': lambda x: False,
})()


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
