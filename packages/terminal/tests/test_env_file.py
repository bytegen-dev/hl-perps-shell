from pathlib import Path

from hl_terminal.env_file import resolve_project_path, upsert_env_vars


def test_resolve_project_path_from_nested_cwd(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "hl-xfgen"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    nested = project / "packages" / "terminal"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    assert resolve_project_path(Path(".env")) == project / ".env"


def test_upsert_env_vars_uncomments_existing_keys(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "HL_NETWORK=testnet",
                "# HL_ACCOUNT_ADDRESS=0xold",
                "# HL_SECRET_KEY=0xoldkey",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    updated = upsert_env_vars(
        env_path,
        {
            "HL_ACCOUNT_ADDRESS": "0xnew",
            "HL_SECRET_KEY": "0xnewkey",
        },
    )

    text = env_path.read_text(encoding="utf-8")
    assert updated == ["HL_ACCOUNT_ADDRESS", "HL_SECRET_KEY"]
    assert "HL_ACCOUNT_ADDRESS=0xnew" in text
    assert "HL_SECRET_KEY=0xnewkey" in text
    assert "HL_NETWORK=testnet" in text


def test_upsert_env_vars_appends_missing_keys(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("HL_NETWORK=testnet\n", encoding="utf-8")

    updated = upsert_env_vars(env_path, {"HL_SECRET_KEY": "0xabc"})

    assert updated == ["HL_SECRET_KEY"]
    assert env_path.read_text(encoding="utf-8").endswith("HL_SECRET_KEY=0xabc\n")
