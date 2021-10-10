from typing import Set


class Sentinel:
    """A class that allows to create special marker objects.

    Mostly useful for distinguishing "value is not set" and "value is set to None" cases,
    as shown in this example::

        >>> from contextvars_extras.sentinel import Sentinel

        >>> NotSet = Sentinel(__name__, 'NotSet')

        >>> value = getattr(object, 'some_attribute', NotSet)
        >>> if value is NotSet:
        ...    print('attribute is not set')
        attribute is not set
    """

    registered_names: Set[str] = set()

    def __init__(self, module_name, instance_name):
        qualified_name = module_name + "." + instance_name

        if qualified_name in self.registered_names:
            raise AssertionError(f"Sentinel with name `{qualified_name}` is already registered.")
        self.registered_names.add(qualified_name)

        self.short_name = instance_name
        self.qualified_name = qualified_name

        super().__init__()

    def __str__(self):
        return self.short_name

    def __repr__(self):
        return self.qualified_name

    @staticmethod
    def __bool__():
        """Evaluate to ``False`` when treated as boolean.

        This thing allows to do ``if not`` checks on the ``Missing`` object, like this:

            >>> value = getattr(object, 'some_attribute', Missing)
            >>> if not value:
            ...     print('no value')
            no value
        """
        return False


Missing = Sentinel(__name__, "Missing")
