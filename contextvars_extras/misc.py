"""A collection of miscellaneous functions that didn't fit in any other module."""

from contextvars import ContextVar

from contextvars_extras.context_management import bind_to_empty_context
from contextvars_extras.sentinel import Missing


@bind_to_empty_context
def get_context_var_default(context_var: ContextVar, missing=Missing):
    """Get a default value from :class:`contextvars.ContextVar` object.

    Example::

      >>> from contextvars import ContextVar
      >>> from contextvars_extras.misc import get_context_var_default

      >>> timezone_var = ContextVar('timezone_var', default='UTC')

      >>> timezone_var.set('GMT')
      <Token ...>

      >>> get_context_var_default(timezone_var)
      'UTC'

    In case the default value is missing, the :func:`get_context_var_default`
    returns a special sentinel object called ``Missing``::

      >>> timezone_var = ContextVar('timezone_var')  # no default value

      >>> timezone_var.set('UTC')
      <Token ...>

      >>> get_context_var_default(timezone_var)
      contextvars_extras.sentinel.Missing

    You can also use a custom missing marker (instead of ``Missing``), like this::

      >>> get_context_var_default(timezone_var, '[NO DEFAULT TIMEZONE]')
      '[NO DEFAULT TIMEZONE]'
    """
    try:
        return context_var.get()
    except LookupError:
        return missing
