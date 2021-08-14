from contextvars import ContextVar
from typing import Callable

from contextvars_extras.context import bind_to_sandbox_context

current_environ: ContextVar = ContextVar("contextvars_extras.integrations.wsgi.current_environ")
"""Environment variables for the current HTTP request.

This context variable contains a dictionary of CGI environment variables,
so-called ``environ``, that contains metadata about the HTTP request currently being handled.

See PEP 333 for the list of possible variables:
https://www.python.org/dev/peps/pep-0333/#environ-variables

.. Note::

  This context variable is set by :class:`ContextVarsMiddleware`.

  So you can use it only when you use that special middleware class,
  and only inside HTTP request handler code.

  An attempt to use it ouside of HTTP request context will raise ``LookupError``.
"""


class ContextVarsMiddleware:
    """Middleware for WSGI apps that puts each request to its own isolated context.

    Actually, this middleware does 2 things:

      1. Puts each request into its own sandbox context.
         That allows you to set any context variables freely,
         and your changes will remain local to the current HTTP request.

      2. Sets :ref:`current_environ` context variable.
         That allows you to reach the ``environ`` dict from any function in your code,
         without passing it through arguments.

    Example::

       >>> from contextvars_extras.integrations.wsgi import ContextVarsMiddleware, current_environ
       >>> import werkzeug.test

       >>> def get_current_url():
       ...     return current_environ.get().get('REQUEST_URI')

       >>> def my_wsgi_app(environ, start_response):
       ...     start_response('200 OK', [('Content-type', 'text/plain; charset=utf-8')])
       ...     return get_current_url()

       >>> wrapped_wsgi_app = ContextVarsMiddleware(my_wsgi_app)

       >>> test_client = werkzeug.test.Client(wrapped_wsgi_app)

       >>> response_body_iter, status, headers = test_client.post("http://localhost/test_api")
       >>> ''.join(response_body_iter)
       'http://localhost/test_api'
    """

    def __init__(self, app):
        self.app = app

    @bind_to_sandbox_context
    def __call__(self, environ: dict, start_response: Callable):  # noqa: D102
        current_environ.set(environ)
        return self.app(environ, start_response)
