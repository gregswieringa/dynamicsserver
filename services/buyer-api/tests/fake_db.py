"""In-memory stand-in for AsyncSession, so router unit tests never touch Postgres.

It understands exactly the query shapes buyer-api's routers issue today: select()
and update() over User/Address with equality/is_ where-clauses, order_by, limit,
and offset. If a router starts issuing a new shape, extend _matches/_execute_*
here rather than adding ad-hoc special cases in tests.
"""
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.sql.dml import Update
from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList, True_
from sqlalchemy.sql.selectable import Select

from app.models import Address, PaymentMethod, User

_TABLE_TO_MODEL = {
    User.__table__: User,
    Address.__table__: Address,
    PaymentMethod.__table__: PaymentMethod,
}


def _apply_column_defaults(obj: Any) -> None:
    """Mimic SQLAlchemy applying Python-side column defaults at flush/INSERT time."""
    for column in sa_inspect(obj).mapper.columns:
        if column.default is None or getattr(obj, column.key) is not None:
            continue
        default = column.default
        value = default.arg(None) if default.is_callable else default.arg
        setattr(obj, column.key, value)


def _clause_value(clause: Any) -> Any:
    if isinstance(clause, True_):
        return True
    return getattr(clause, "value", clause)


def _matches(obj: Any, clause: Any) -> bool:
    if clause is None:
        return True
    if isinstance(clause, BooleanClauseList):
        results = [_matches(obj, c) for c in clause.clauses]
        return all(results) if clause.operator.__name__ == "and_" else any(results)
    if isinstance(clause, BinaryExpression):
        attr = getattr(obj, clause.left.key)
        target = _clause_value(clause.right)
        op = clause.operator.__name__
        if op == "eq":
            return attr == target
        if op == "is_":
            return attr is target
        raise NotImplementedError(f"fake_db: unsupported operator {op!r}")
    raise NotImplementedError(f"fake_db: unsupported where clause {clause!r}")


class FakeResult:
    def __init__(self, items: list[Any]):
        self._items = items

    def scalars(self) -> "FakeResult":
        return self

    def all(self) -> list[Any]:
        return list(self._items)

    def first(self) -> Any | None:
        return self._items[0] if self._items else None


class FakeSession:
    """Dict-backed double for AsyncSession used via the get_db dependency override."""

    def __init__(self) -> None:
        self.store: dict[tuple[type, Any], Any] = {}
        self._pending: list[Any] = []
        self.raise_on_commit: Exception | None = None

    def add(self, obj: Any) -> None:
        self._pending.append(obj)

    async def flush(self) -> None:
        for obj in self._pending:
            _apply_column_defaults(obj)
            self.store[(type(obj), obj.id)] = obj
        self._pending.clear()

    async def commit(self) -> None:
        if self.raise_on_commit is not None:
            raise self.raise_on_commit
        await self.flush()

    async def rollback(self) -> None:
        self._pending.clear()

    async def refresh(self, obj: Any) -> None:
        pass

    async def get(self, model: type, pk: Any) -> Any | None:
        return self.store.get((model, pk))

    async def execute(self, stmt: Any) -> FakeResult:
        if isinstance(stmt, Select):
            return self._execute_select(stmt)
        if isinstance(stmt, Update):
            return self._execute_update(stmt)
        raise NotImplementedError(f"fake_db: unsupported statement {stmt!r}")

    def _items_for(self, model: type) -> list[Any]:
        return [obj for (m, _pk), obj in self.store.items() if m is model]

    def _execute_select(self, stmt: Select) -> FakeResult:
        model = stmt.column_descriptions[0]["entity"]
        items = [o for o in self._items_for(model) if _matches(o, stmt.whereclause)]
        for col in reversed(stmt._order_by_clauses):
            items.sort(key=lambda o: getattr(o, col.key))
        offset = stmt._offset_clause.value if stmt._offset_clause is not None else 0
        limit = stmt._limit_clause.value if stmt._limit_clause is not None else None
        items = items[offset:]
        if limit is not None:
            items = items[:limit]
        return FakeResult(items)

    def _execute_update(self, stmt: Update) -> FakeResult:
        model = _TABLE_TO_MODEL[stmt.table]
        values = {col.key: _clause_value(val) for col, val in stmt._values.items()}
        items = [o for o in self._items_for(model) if _matches(o, stmt.whereclause)]
        for obj in items:
            for key, value in values.items():
                setattr(obj, key, value)
        return FakeResult(items)


def make_integrity_error(constraint_name: str, message: str):
    """Build a fake IntegrityError matching the asyncpg wrap/__cause__ chain that
    routers/users.py unwraps (see CLAUDE.md's "Integrity-error handling pattern").
    """
    from sqlalchemy.exc import IntegrityError

    cause = Exception(message)
    cause.constraint_name = constraint_name
    cause.message = message
    orig = Exception("db error")
    orig.__cause__ = cause
    return IntegrityError("statement", {}, orig)
