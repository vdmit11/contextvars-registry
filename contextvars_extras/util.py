import functools
import inspect


class MissingType:
    """Sentinel object that allows to distinguish "no value" from ``None``.

    This is a singleton.
    There should be only one instance of MissingType

    Example:

        >>> from contextvars_extras.util import Missing
        >>> value = getattr(object, 'some_attribute', Missing)
        >>> if value is Missing:
        ...    print('attribute is not set')
        attribute is not set
    """
    was_instanciated: bool = False

    @staticmethod
    def __init__():
        if MissingType.was_instanciated:
            raise AssertionError(
                "The `Missing` object must be a singleton (instanciated only once)."
            )
        MissingType.was_instanciated = True

    @staticmethod
    def __str__():
        return 'Missing'

    @staticmethod
    def __repr__():
        return MissingType.__module__ + '.Missing'


Missing = MissingType()


@functools.lru_cache(maxsize=128)
def cleandoc_cached(doc):
    return inspect.cleandoc(doc)
