from hl_terminal.responses import _order_status_lines, print_exchange_result
from rich.console import Console


def test_order_status_lines_filled() -> None:
    raw = {
        "status": "ok",
        "response": {
            "type": "order",
            "data": {
                "statuses": [
                    {"filled": {"totalSz": "0.01", "avgPx": "1880.5", "oid": 123}}
                ]
            },
        },
    }
    lines = _order_status_lines(raw)
    assert lines == [("ok", "Filled 0.01 @ avg 1880.5 (oid 123)")]


def test_order_status_lines_error() -> None:
    raw = {
        "status": "ok",
        "response": {
            "type": "order",
            "data": {"statuses": [{"error": "Order must have minimum value of $10."}]},
        },
    }
    lines = _order_status_lines(raw)
    assert lines == [("error", "Order must have minimum value of $10.")]


def test_print_exchange_result_leverage_headline(capsys) -> None:
    console = Console(width=120, force_terminal=True, color_system=None)
    print_exchange_result(
        console,
        {"status": "ok", "response": {"type": "default"}},
        headline="ETH leverage set to 5x (isolated)",
    )
    output = capsys.readouterr().out
    assert "ETH leverage set to 5x (isolated)" in output
