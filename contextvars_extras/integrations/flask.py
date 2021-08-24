import flask

from contextvars_extras.context import bind_to_sandbox_context


class Flask(flask.Flask):
    """Flask app with contextvars extensions.

    This is a subclass of :class:`flask.Flask`, that adds some integration
    :ref:`contextvars` module.

    Currently, it adds only 1 feature: it puts each HTTP request to its own context.

    That means that inside a view function, you can freely change any context variables,
    and your changes stay private to the current HTTP request.

    Once HTTP request is handled, all context variables are automatically restored.

    Example::

        >>> import pytz
        >>> from contextvars import ContextVar
        >>> from contextvars_extras.integrations.flask import Flask

        >>> timezone_var = ContextVar("timezone_var", default="UTC")

        >>> flask_app = Flask(__name__)

        >>> @flask_app.route("/test_url")
        ... def test_view_function():
        ...     timezone_var.set("Antarctica/Troll")
        ...     return timezone_var.get()

        >>> client = flask_app.test_client()

        >>> response = client.get("/test_url")
        >>> response.data
        b'Antarctica/Troll'

        # timezone_var var was change by test_view_function() above, but that
        # change isn't seen here, because each HTTP context is put to its own sandbox context.
        >>> timezone_var.get()
        'UTC'
    """

    @bind_to_sandbox_context
    def __call__(self, environ, start_response):
        """Call Flask as WSGI application.

        This is the entry point to Flask application.
        It just calls ``Flask.wsgi_app``, where all the interesting stuff happens.

        Also, it puts each WSGI request into its own context (by calling
        :func:`contextvars.copy_context`), so each HTTP request can modify context vars
        without affecting other HTTP requests.

        """
        return super().__call__(environ, start_response)
