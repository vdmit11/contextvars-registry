import os
import functools
import inspect


class MissingType:
    """Sentinel object that allows to distinguish "no value" from ``None``.

    This is a singleton.
    There should be only one instance of MissingType

    Example::

        >>> from contextvars_extras.util import Missing
        >>> value = getattr(object, 'some_attribute', Missing)
        >>> if value is Missing:
        ...    print('attribute is not set')
        attribute is not set
    """

    was_instanciated: bool = False

    def __init__(self):
        if MissingType.was_instanciated:
            raise AssertionError(
                "The `Missing` object must be a singleton (instanciated only once)."
            )
        MissingType.was_instanciated = True

        super().__init__()

    @staticmethod
    def __str__():
        return 'Missing'

    @staticmethod
    def __repr__():
        return MissingType.__module__ + '.Missing'


Missing = MissingType()


class ExceptionDocstringMixin:
    """An Exception with pre-defined message stored in the docstring.

    It allows to put a nice multi-line error message into class docstring,
    like that:

        >>> class MyError(ExceptionDocstringMixin, RuntimeError):
        ...     '''my error
        ...
        ...     Some long multi-line
        ...     description of the error.
        ...     '''

    and then, when you raise the exception, the class docstring becomes the error message:

        >>> try:
        ...     raise MyError
        ... except RuntimeError as err:
        ...     print(err)
        my error
        <BLANKLINE>
        Some long multi-line
        description of the error.
        <BLANKLINE>

    The benefit is that you re-use the same text for auto-generated documentation,
    and for the exception thrown in Python. The message is consistent across both places,
    and also you have to maintain less messages in the code.

    .. caution::

        This mixin must be placed before standard ``Exception`` in the list of base classes,
        like this:

            >>> class MyException(ExceptionDocstringMixin, Exception):
            ...     '''docsstring'''

        If you put ``Exception`` (or any other standard base class) first,
        it will not work properly (you will get an empty error message):

            >>> class MyException(Exception, ExceptionDocstringMixin):  # <--- BAD, won't work
            ...     '''docstring'''

        That happens because the standard ``Exception.__init__()`` doesn't call ``super()``.
        There is no good workaround for that.
        You just have to remember to put the mixin first.
    """

    def __init__(self, *args, **kwargs):
        if not args and not kwargs:
            super().__init__(self._clean_docstring())
        else:
            super().__init__(*args, **kwargs)

    @classmethod
    def format(cls, **kwargs):
        """Format class docstring as the exception message.

        Example::

            >>> class InvalidEmailAddressError(ExceptionDocstringMixin, ValueError):
            ...     '''Invalid e-mail address: '{email_address}'
            ...
            ...     This exception is raised an e-mail address doesn't contain the '@' character.
            ...     Please make sure this is a valid address: '{email_address}'.
            ...     '''

            >>> email_address = 'foo bar'
            >>> try:
            ...     if '@' not in email_address:
            ...         raise InvalidEmailAddressError.format(email_address=email_address)
            ... except ValueError as err:
            ...     print(err)
            Invalid e-mail address: 'foo bar'
            <BLANKLINE>
            This exception is raised an e-mail address doesn't contain the '@' character.
            Please make sure this is a valid address: 'foo bar'.
            <BLANKLINE>
        """
        message = cls._clean_docstring().format(**kwargs)
        return cls(message)

    @classmethod
    def _clean_docstring(cls):
        return cleandoc_cached(cls.__doc__) + os.linesep


@functools.lru_cache(maxsize=128)
def cleandoc_cached(doc):
    return inspect.cleandoc(doc)
