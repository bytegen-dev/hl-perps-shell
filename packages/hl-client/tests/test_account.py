from hl_client.client import _extract_portfolio_pnl, _spot_usdc_amounts


def test_spot_usdc_amounts_from_clearinghouse_state() -> None:
    total, hold, available = _spot_usdc_amounts(
        {
            "balances": [
                {"coin": "USDC", "total": "9.913731", "hold": "0.0"},
                {"coin": "PURR", "total": "100.0", "hold": "10.0"},
            ]
        }
    )
    assert total == 9.913731
    assert hold == 0.0
    assert available == 9.913731


def test_spot_usdc_amounts_subtracts_hold() -> None:
    total, hold, available = _spot_usdc_amounts(
        {"balances": [{"coin": "USDC", "total": "100.0", "hold": "25.5"}]}
    )
    assert total == 100.0
    assert hold == 25.5
    assert available == 74.5


def test_spot_usdc_amounts_missing_usdc() -> None:
    assert _spot_usdc_amounts({"balances": []}) == (0.0, 0.0, 0.0)


def test_extract_portfolio_pnl_all_time() -> None:
    portfolio = [
        [
            "allTime",
            {
                "pnlHistory": [
                    [1_741_886_630_493, "0.0"],
                    [1_741_895_270_493, "12.34"],
                ]
            },
        ]
    ]
    assert _extract_portfolio_pnl(portfolio, "allTime") == 12.34


def test_extract_portfolio_pnl_missing_period() -> None:
    assert _extract_portfolio_pnl([], "allTime") is None
