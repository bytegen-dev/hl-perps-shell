import pytest
from hl_client.exceptions import HyperliquidClientError
from hl_client.tpsl import validate_tpsl_trigger


def test_validate_long_tp_requires_trigger_above_mark() -> None:
    validate_tpsl_trigger(kind="tp", is_long=True, trigger_px=2100.0, mark_px=2000.0)
    with pytest.raises(HyperliquidClientError, match="above mark"):
        validate_tpsl_trigger(kind="tp", is_long=True, trigger_px=1900.0, mark_px=2000.0)


def test_validate_long_sl_requires_trigger_below_mark() -> None:
    validate_tpsl_trigger(kind="sl", is_long=True, trigger_px=1900.0, mark_px=2000.0)
    with pytest.raises(HyperliquidClientError, match="below mark"):
        validate_tpsl_trigger(kind="sl", is_long=True, trigger_px=2100.0, mark_px=2000.0)


def test_validate_short_tp_requires_trigger_below_mark() -> None:
    validate_tpsl_trigger(kind="tp", is_long=False, trigger_px=1900.0, mark_px=2000.0)
    with pytest.raises(HyperliquidClientError, match="below mark"):
        validate_tpsl_trigger(kind="tp", is_long=False, trigger_px=2100.0, mark_px=2000.0)


def test_validate_short_sl_requires_trigger_above_mark() -> None:
    validate_tpsl_trigger(kind="sl", is_long=False, trigger_px=2100.0, mark_px=2000.0)
    with pytest.raises(HyperliquidClientError, match="above mark"):
        validate_tpsl_trigger(kind="sl", is_long=False, trigger_px=1900.0, mark_px=2000.0)
