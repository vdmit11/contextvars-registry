contextvars-extras
==================

|pypi badge| |build badge| |docs badge|

**Warning!**

**The code is at the early development stage, and may be unstable. Use with caution.**

``contextvars-extras`` is a set of extensions for the Python's `contextvars`_ module.

In case you are not familiar with the `contextvars`_ module, its `ContextVar`_ objects
work like Thread-Local storage, but better: they are both thread-safe and async task-safe,
and they can be copied (all existing vars copied in O(1) time), and then you can run
a function in the copied and isolated context.

.. _contextvars: https://docs.python.org/3/library/contextvars.html
.. _ContextVar: https://docs.python.org/3/library/contextvars.html#contextvars.ContextVar

The `contextvars`_ is a powerful module, but its API seems too low-level.

So this ``contextvars_extras`` package provides some higher-level additions on top of the
standard API, like, for example, organizing `ContextVar`_ objects into registry classes,
with nice ``@property``-like access:

.. code:: python

    from contextvars_extras import ContextVarsRegistry

    class CurrentVars(ContextVarsRegistry):
        locale: str = 'en'
        timezone: str = 'UTC'

    current = CurrentVars()

    # calls ContextVar.get() under the hood
    current.timezone  # => 'UTC'

    # calls ContextVar.set() under the hood
    current.timezone = 'GMT'

    # ContextVar() objects can be reached as class members
    CurrentVars.timezone.get()  # => 'GMT'

That makes your code more readable (no more noisy ``.get()`` calls),
and it is naturally firendly to `typing`_, so static code analysis features
(like type checkers and auto-completion in your IDE) work nicely.

.. _typing: https://docs.python.org/3/library/typing.html

Check out the `full documentation <https://contextvars-extras.readthedocs.io>`_

Links
-----

- Read the Docs: https://contextvars-extras.readthedocs.io
- GitHub repository: https://github.com/vdmit11/contextvars-extras
- Python package: https://pypi.org/project/contextvars-extras/


.. |pypi badge| image:: https://img.shields.io/pypi/v/contextvars-extras.svg
  :target: https://pypi.org/project/contextvars-extras/
  :alt: Python package version

.. |build badge| image:: https://github.com/vdmit11/contextvars-extras/actions/workflows/build.yml/badge.svg
  :target: https://github.com/vdmit11/contextvars-extras/actions/workflows/build.yml
  :alt: Tests Status

.. |docs badge| image:: https://readthedocs.org/projects/contextvars-extras/badge/?version=latest
  :target: https://contextvars-extras.readthedocs.io/en/latest/?badge=latest
  :alt: Documentation Status

