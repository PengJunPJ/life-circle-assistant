"""逻辑路线对及百度 HTTP 尝试双重预算；缓存命中不扣减外部请求预算。"""

from contextvars import ContextVar

from .maps.provider import MapProviderError
from .model_budget import ModelAttemptBudget, bind_model_attempt_budget

ANALYSIS_ROUTE_PAIR_LIMIT = 5000


class RoutePairLedger:
    def __init__(self, limit: int):
        self.limit, self.used = limit, 0

    def charge(self, pairs: int) -> None:
        # 不含 await：共享到并行子任务的同一账本，检查与扣减不可被事件循环打断。
        if self.used + pairs > self.limit:
            raise MapProviderError("真实步行请求路线对预算已用尽，未发送新的 HTTP 请求", code="route_budget_exhausted")
        self.used += pairs


_route_pair_ledger: ContextVar[RoutePairLedger | None] = ContextVar("route_pair_ledger", default=None)


def charge_physical_route_pairs(pairs: int, extra_charges=None) -> None:
    from .execution_ledger import charge_external_many

    ledger = _route_pair_ledger.get()
    if ledger is not None and ledger.used + pairs > ledger.limit:
        raise MapProviderError("真实步行请求路线对预算已用尽，未发送新的 HTTP 请求", code="route_budget_exhausted")
    charge_external_many({"route_pairs": pairs, **(extra_charges or {})})
    if ledger is not None:
        ledger.charge(pairs)


class BudgetMapProvider:
    def __init__(self, provider, limit: int = ANALYSIS_ROUTE_PAIR_LIMIT, cancelled=None):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("路线对预算必须为非负整数")
        self.provider, self.limit, self.used = provider, limit, 0
        self.cancelled = cancelled
        self.physical_ledger = RoutePairLedger(limit)

    @property
    def physical_route_pairs_used(self):
        return self.physical_ledger.used

    def __getattr__(self, name):
        return getattr(self.provider, name)

    async def walking_matrix(self, origins, destinations):
        import asyncio

        if self.cancelled and self.cancelled():
            raise asyncio.CancelledError()
        requested = len(origins) * len(destinations)
        if requested == 0:
            return [[] for _ in origins]
        if self.used + requested > self.limit:
            raise MapProviderError("本次路线对预算已用尽，未测位置保持未知", code="route_budget_exhausted")
        self.used += requested
        existing = _route_pair_ledger.get()
        # 嵌套包装沿用上层账本，避免创建新计费空间绕过总预算。
        token = _route_pair_ledger.set(existing or self.physical_ledger)
        try:
            return await self.provider.walking_matrix(origins, destinations)
        finally:
            _route_pair_ledger.reset(token)


class BudgetLLMProvider:
    def __init__(self, provider, limit=7):
        self.provider = provider
        self.attempt_budget = ModelAttemptBudget(limit)

    @property
    def limit(self):
        return self.attempt_budget.limit

    @property
    def used(self):
        return self.attempt_budget.used

    @property
    def supports_physical_attempt_budget(self):
        return bool(getattr(self.provider, "supports_physical_attempt_budget", False))

    def restrict_remaining(self, remaining):
        self.attempt_budget.limit = min(self.limit, self.used + remaining)

    @property
    def model(self):
        return self.provider.model

    async def generate(self, **kwargs):
        if not self.supports_physical_attempt_budget:
            self.attempt_budget.charge()
        with bind_model_attempt_budget(self.attempt_budget):
            return await self.provider.generate(**kwargs)

    async def generate_tools(self, **kwargs):
        if not self.supports_physical_attempt_budget:
            self.attempt_budget.charge()
        with bind_model_attempt_budget(self.attempt_budget):
            return await self.provider.generate_tools(**kwargs)
