from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ShadowFixture:
    fixture_id: str
    source_name: str
    business_keys: tuple[str, ...]
    rows: tuple[dict, ...]
    expected: tuple[dict, ...]


_ROWS = (
    {"order_id": 1, "amount": Decimal("100.00")},
    {"order_id": 2, "amount": Decimal("0.00")},
    {"order_id": 3, "amount": Decimal("-12.50")},
    {"order_id": 4, "amount": Decimal("10.125")},
    {"order_id": 5, "amount": None},
    {"order_id": 6, "amount": Decimal("0.01")},
)

ORDERS_DISCOUNT_V1 = ShadowFixture(
    fixture_id="orders_discount_v1",
    source_name="src_orders",
    business_keys=("order_id",),
    rows=_ROWS,
    expected=tuple(
        {"order_id": row["order_id"], "net_amount": row["amount"] * Decimal("0.90")}
        for row in _ROWS if row["amount"] is not None and row["amount"] * Decimal("0.90") > 0
    ),
)

FIXTURES = {ORDERS_DISCOUNT_V1.fixture_id: ORDERS_DISCOUNT_V1}


def get_fixture(fixture_id: str) -> ShadowFixture | None:
    return FIXTURES.get(fixture_id)
