"""Request-local budget for physical model attempts, including adapter retries."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


class ModelBudgetExceeded(ValueError):
    """Raised before another HTTP attempt could consume model quota."""


@dataclass
class ModelAttemptBudget:
    limit: int
    used: int = 0

    def __post_init__(self) -> None:
        if type(self.limit) is not int or self.limit < 1:
            raise ValueError("模型实际请求预算必须为正整数")
        if self.used != 0:
            raise ValueError("模型预算必须从零开始")

    def charge(self) -> None:
        # Synchronous and contains no await: shared request tasks cannot interleave
        # the check and increment. Failed attempts retain their reservation.
        if self.used >= self.limit:
            raise ModelBudgetExceeded("本轮模型实际请求预算已用尽")
        self.used += 1


_current_budget: ContextVar[ModelAttemptBudget | None] = ContextVar("model_attempt_budget", default=None)


@contextmanager
def bind_model_attempt_budget(budget: ModelAttemptBudget) -> Iterator[None]:
    token = _current_budget.set(budget)
    try:
        yield
    finally:
        _current_budget.reset(token)


def charge_model_attempt() -> None:
    from .execution_ledger import charge_external

    """Called by a supporting adapter immediately before each HTTP attempt."""
    budget = _current_budget.get()
    if budget is not None and budget.used >= budget.limit:
        raise ModelBudgetExceeded("本轮模型实际请求预算已用尽")
    charge_external("model_http_attempts")
    if budget is not None:
        budget.charge()
