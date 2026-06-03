import pytest

from schwab.auth.oauth import SchwabAuth


@pytest.fixture
def auth(monkeypatch, tmp_path):
    monkeypatch.setenv("SCHWAB_APP_KEY", "test-key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "test-secret")
    monkeypatch.setenv("SCHWAB_CALLBACK_URL", "https://127.0.0.1")
    return SchwabAuth(env_path=tmp_path / ".env")


def test_get_auth_url_contains_client_and_redirect(auth):
    url = auth.get_auth_url()
    assert url.startswith("https://api.schwabapi.com/v1/oauth/authorize")
    assert "client_id=test-key" in url
    assert "redirect_uri=https%3A%2F%2F127.0.0.1" in url


def test_basic_auth_header_is_base64(auth):
    import base64

    header = auth._basic_auth_header()
    assert header.startswith("Basic ")
    decoded = base64.b64decode(header.split(" ", 1)[1]).decode()
    assert decoded == "test-key:test-secret"


def test_rewrite_env_updates_and_appends(auth, tmp_path):
    env = tmp_path / ".env"
    env.write_text("SCHWAB_APP_KEY=test-key\nOTHER=keep\n")
    auth.env_path = env
    auth._rewrite_env({"SCHWAB_ACCESS_TOKEN": "tok123", "OTHER": "keep"})
    text = env.read_text()
    assert "SCHWAB_ACCESS_TOKEN=tok123" in text
    assert "OTHER=keep" in text
    # existing unrelated key preserved exactly once
    assert text.count("OTHER=keep") == 1


def test_exchange_code_requires_code_param(auth):
    with pytest.raises(RuntimeError, match="code"):
        auth.exchange_code("https://127.0.0.1/?state=abc")
