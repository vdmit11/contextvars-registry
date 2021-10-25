# Why there are type hints in both context_var_ext.py/.pyi files?
# Do I really need this separate .pyi file?
# Why not just use inline type hints in the .py file?
#
# Well, for a couple of reasons:
#
# 1. ContextVarExt class re-writes .get() method during __init__(),
#    and that confuses some code analysis tools, like Jedi.
#    The separate .pyi file fixes the issue, at least for Jedi.
#
# 2. built-in contextvars.Token class is not subscriptable,
#    So I just can't get a nice type hint for it in a .py file
#    (while here in .pyi I can create a custom Token stub that would work).
#
# So, this .pyi file duplicates existing type hints in the corresponding .py file,
# but it fixes the issues, so I have to maintain it.

import contextvars
import sys
from contextvars import ContextVar
from typing import Any, Callable, ClassVar, Generic, Optional, Type, TypeVar, Union, overload

from contextvars_extras.context_management import bind_to_empty_context
from contextvars_extras.sentinel import Sentinel

class ContextVarDeletionMark(Sentinel): ...

CONTEXT_VAR_VALUE_DELETED: ContextVarDeletionMark
CONTEXT_VAR_RESET_TO_DEFAULT: ContextVarDeletionMark

class NoDefault(Sentinel): ...

NO_DEFAULT: NoDefault

_VarValueT = TypeVar("_VarValueT")  # value, stored in the ContextVar object
_FallbackT = TypeVar("_FallbackT")  # an object, returned by .get() when ContextVar has no value
_ContextVarExtOrItsSubclass = TypeVar("_ContextVarExtOrItsSubclass")

class ContextVarExt(Generic[_VarValueT]):
    @property
    def name(self) -> str: ...
    @property
    def context_var(self) -> ContextVar[Union[_VarValueT, ContextVarDeletionMark]]: ...
    @property
    def default(self) -> Union[_VarValueT, NoDefault]: ...
    def __init__(
        self,
        name: Optional[str] = ...,
        default: Union[_VarValueT, NoDefault] = ...,
        deferred_default: Optional[Callable[[], _VarValueT]] = ...,
        _context_var: Optional[ContextVar[_VarValueT]] = ...,
    ) -> None: ...
    @classmethod
    def from_existing_var(
        cls: Type[_ContextVarExtOrItsSubclass],
        context_var: ContextVar[_VarValueT],
        deferred_default: Optional[Callable[[], _VarValueT]] = ...,
    ) -> _ContextVarExtOrItsSubclass: ...
    @overload
    def get(self) -> _VarValueT: ...
    @overload
    def get(self, default: _FallbackT) -> Union[_VarValueT, _FallbackT]: ...
    @overload
    def get_raw(self) -> Union[_VarValueT, ContextVarDeletionMark]: ...
    @overload
    def get_raw(
        self, default: _FallbackT
    ) -> Union[_VarValueT, _FallbackT, ContextVarDeletionMark]: ...
    def is_set(self) -> bool: ...
    def set(self, value: _VarValueT) -> Token[Union[_VarValueT, ContextVarDeletionMark]]: ...
    def set_if_not_set(self, value: _VarValueT) -> _VarValueT: ...
    def reset(self, token: Token[_VarValueT]) -> None: ...
    def reset_to_default(self) -> None: ...
    def delete(self) -> None: ...
    if sys.version_info >= (3, 9):
        def __class_getitem__(cls, item: Any) -> GenericAlias: ...

class Token(Generic[_VarValueT], contextvars.Token[_VarValueT]):
    MISSING: ClassVar[object]
    var: ContextVar[_VarValueT]
    old_value: _VarValueT

    if sys.version_info >= (3, 9):
        def __class_getitem__(cls, item: Any) -> GenericAlias: ...

def get_context_var_default(
    context_var: ContextVar[_VarValueT], missing: _FallbackT = ...
) -> Union[_VarValueT, _FallbackT]: ...
