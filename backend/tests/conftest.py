import os

os.environ.setdefault("MODEL_API_KEY", "test")
os.environ.setdefault("GOOGLE_PLACES_API_KEY", "test")
# No test may reach real AWS: unknown credentials and an endpoint nothing listens on, so a
# store call that a test forgot to fake fails instead of touching a live table or bucket.
for _var in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_SESSION_TOKEN"):
    os.environ.pop(_var, None)
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_ENDPOINT_URL"] = "http://127.0.0.1:9"
os.environ["AWS_MAX_ATTEMPTS"] = "1"
os.environ["AWS_RETRY_MODE"] = "standard"

import pytest  # noqa: E402

from tests.fakes_rewards import FakeRewardsStore  # noqa: E402


@pytest.fixture(autouse=True)
def rewards_db():
    """Every test gets an empty in-memory rewards store (payout entries, bans, locks).

    Swapped in on the module itself, not with monkeypatch, so a test that calls
    monkeypatch.undo() keeps it."""
    from app.store import rewards_store

    fake = FakeRewardsStore()
    saved = {}
    for name in FakeRewardsStore.API:
        saved[name] = getattr(rewards_store, name)
        setattr(rewards_store, name, getattr(fake, name))
    try:
        yield fake
    finally:
        for name, fn in saved.items():
            setattr(rewards_store, name, fn)
