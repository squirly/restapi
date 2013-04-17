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