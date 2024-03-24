contextvars-registry
====================

|pypi badge| |build badge| |docs badge|

``contextvars-registry`` is an extension for the Python's `contextvars`_ module.

In case you are not familiar with Context Variables, they work like Thread-Local storage,
but better: they are both thread-safe and async task-safe, have snapshots (all existing
vars copied in O(1) time), allowing to run functions/threads/asynctasks in the copied context snapshot.

.. _contextvars: https://docs.python.org/3/library/contextvars.html
.. _ContextVar: https://docs.python.org/3/library/contextvars.html#contextvars.ContextVar

The `contextvars`_ is a powerful module, but its API seems too low-level.

So this ``contextvars_registry`` package provides some higher-level additions on top of the
standard API, like, for example, grouping `ContextVar`_ objects in a registry class,
with nice ``@property``-like access:

.. code::

    from contextvars_registry import ContextVarsRegistry

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

Check out the `full documentation <https://contextvars-registry.readthedocs.io>`_

Links
-----

- Read the Docs: https://contextvars-registry.readthedocs.io
- GitHub repository: https://github.com/vdmit11/contextvars-registry
- Python package: https://pypi.org/project/contextvars-registry/


.. |pypi badge| image:: https://img.shields.io/pypi/v/contextvars-registry.svg
  :target: https://pypi.org/project/contextvars-registry/
  :alt: Python package version

.. |build badge| image:: https://github.com/vdmit11/contextvars-registry/actions/workflows/build.yml/badge.svg
  :target: https://github.com/vdmit11/contextvars-registry/actions/workflows/build.yml
  :alt: Tests Status

.. |docs badge| image:: https://readthedocs.org/projects/contextvars-registry/badge/?version=latest
  :target: https://contextvars-registry.readthedocs.io/en/latest/?badge=latest
  :alt: Documentation Status

