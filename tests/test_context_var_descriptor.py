from contextvars import ContextVar

from contextvars_extras.context_var_descriptor import ContextVarDescriptor


def test__descriptor__can_be_initialized_with_an_existing_context_var_object():
    timezone_var = ContextVar("timezone_var", default="UTC")

    class CurrentVars:
        timezone = ContextVarDescriptor(context_var=timezone_var)

    current = CurrentVars()

    assert current.timezone == "UTC"
    assert CurrentVars.timezone.context_var is timezone_var