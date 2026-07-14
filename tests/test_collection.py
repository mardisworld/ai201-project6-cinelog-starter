"""
tests/test_collection.py — CineLog

Tests for the collection service.
These tests demonstrate the patterns used across the codebase — read them
before writing your own tests for the watchlist feature (see Comment 4).
"""

import pytest
from app import create_app, db
from models import User, Film, CollectionEntry, WatchlistEntry
from services.collection_service import (
    add_to_collection,
    remove_from_collection,
    get_collection,
    FilmNotFoundError,
    AlreadyInCollectionError,
    NotInCollectionError,
)
from services.watchlist_service import (
    add_to_watchlist,
    remove_from_watchlist,
    get_watchlist,
    AlreadyInWatchlistError,
    NotInWatchlistError,
)


@pytest.fixture
def app():
    """Create an isolated test app with an in-memory database."""
    app = create_app(config={
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def sample_user(app):
    """A user to use in tests."""
    with app.app_context():
        user = User(username="testuser", email="test@example.com")
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def sample_film(app):
    """A film to use in tests."""
    with app.app_context():
        film = Film(title="Paddington 2", year=2017, genre="Comedy")
        db.session.add(film)
        db.session.commit()
        return film.id


# ── Basic add ───────────────────────────────────────────────────────────────

def test_add_to_collection_creates_entry(app, sample_user, sample_film):
    """
    Adding a valid film should create a CollectionEntry in the database.
    """
    with app.app_context():
        entry = add_to_collection(user_id=sample_user, film_id=sample_film)

        assert entry is not None
        assert entry.user_id == sample_user
        assert entry.film_id == sample_film

        # Verify it persisted
        in_db = CollectionEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).first()
        assert in_db is not None


def test_add_to_watchlist_creates_entry(app, sample_user, sample_film):
    """
    Adding a valid film should create a WatchlistEntry in the database.
    """
    with app.app_context():
        entry = add_to_watchlist(user_id=sample_user, film_id=sample_film)

        assert entry is not None
        assert entry.user_id == sample_user
        assert entry.film_id == sample_film

        in_db = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).first()
        assert in_db is not None


# ── Deduplication ────────────────────────────────────────────────────────────

def test_add_to_collection_duplicate_raises(app, sample_user, sample_film):
    """
    Adding the same film twice should raise AlreadyInCollectionError,
    not silently create a duplicate entry.
    """
    with app.app_context():
        add_to_collection(user_id=sample_user, film_id=sample_film)

        with pytest.raises(AlreadyInCollectionError):
            add_to_collection(user_id=sample_user, film_id=sample_film)

        # Confirm only one entry exists
        count = CollectionEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).count()
        assert count == 1


def test_add_to_watchlist_duplicate_raises(app, sample_user, sample_film):
    """
    Adding the same film twice should raise AlreadyInWatchlistError,
    not silently create a duplicate entry.
    """
    with app.app_context():
        add_to_watchlist(user_id=sample_user, film_id=sample_film)

        with pytest.raises(AlreadyInWatchlistError):
            add_to_watchlist(user_id=sample_user, film_id=sample_film)

        count = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).count()
        assert count == 1


def test_add_to_watchlist_route_missing_film_id_returns_400(app, sample_user):
    """
    POST /watchlist/<user_id>/add should reject requests without film_id.
    """
    client = app.test_client()

    response = client.post(f"/watchlist/{sample_user}/add", json={})

    assert response.status_code == 400
    assert response.get_json() == {"error": "film_id is required"}


def test_add_to_watchlist_route_duplicate_returns_409(app, sample_user, sample_film):
    """
    POST /watchlist/<user_id>/add should return 409 for duplicate entries.
    """
    client = app.test_client()
    payload = {"film_id": sample_film}

    first_response = client.post(f"/watchlist/{sample_user}/add", json=payload)
    second_response = client.post(f"/watchlist/{sample_user}/add", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert "already in this user's watchlist" in second_response.get_json()["error"]


# ── Nonexistent film ─────────────────────────────────────────────────────────

def test_add_to_watchlist_nonexistent_film_raises(app, sample_user):
    """
    Adding a film_id that doesn't exist in the database should raise
    FilmNotFoundError, not a database integrity error — and should not
    create a WatchlistEntry.
    """
    with app.app_context():
        fake_film_id = "00000000-0000-0000-0000-000000000000"

        with pytest.raises(FilmNotFoundError):
            add_to_watchlist(user_id=sample_user, film_id=fake_film_id)

        # Nothing should have been persisted.
        count = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=fake_film_id
        ).count()
        assert count == 0


# ── Remove from watchlist ────────────────────────────────────────────────────

def test_remove_from_watchlist_deletes_entry(app, sample_user, sample_film):
    """
    Removing a watchlist film should delete the WatchlistEntry from the database.
    """
    with app.app_context():
        add_to_watchlist(user_id=sample_user, film_id=sample_film)

        removed = remove_from_watchlist(user_id=sample_user, film_id=sample_film)

        assert removed is True
        in_db = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).first()
        assert in_db is None


def test_remove_from_watchlist_missing_entry_raises(app, sample_user, sample_film):
    """
    Removing a film that is not on the watchlist should raise NotInWatchlistError.
    """
    with app.app_context():
        with pytest.raises(NotInWatchlistError):
            remove_from_watchlist(user_id=sample_user, film_id=sample_film)


def test_remove_from_watchlist_route_deletes_entry(app, sample_user, sample_film):
    """
    DELETE /watchlist/<user_id>/remove should remove an existing watchlist entry.
    """
    client = app.test_client()
    with app.app_context():
        add_to_watchlist(user_id=sample_user, film_id=sample_film)

    response = client.delete(
        f"/watchlist/{sample_user}/remove",
        json={"film_id": sample_film},
    )

    assert response.status_code == 200
    assert response.get_json() == {"message": "Removed from watchlist"}
    with app.app_context():
        in_db = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).first()
        assert in_db is None


def test_remove_from_watchlist_route_missing_entry_returns_404(
    app, sample_user, sample_film
):
    """
    DELETE /watchlist/<user_id>/remove should return 404 for a missing entry.
    """
    client = app.test_client()

    response = client.delete(
        f"/watchlist/{sample_user}/remove",
        json={"film_id": sample_film},
    )

    assert response.status_code == 404
    assert "is not in this user's watchlist" in response.get_json()["error"]


# ── get_collection sort order ────────────────────────────────────────────────

def test_get_collection_returns_newest_first(app, sample_user):
    """
    get_collection() should return films sorted by date_added descending
    (most recently added first).
    """
    with app.app_context():
        from datetime import datetime, timezone, timedelta
        from models import Film, CollectionEntry

        film_a = Film(title="Alien", year=1979, genre="Horror")
        film_b = Film(title="Blade Runner", year=1982, genre="Sci-Fi")
        db.session.add_all([film_a, film_b])
        db.session.commit()

        earlier = datetime.now(timezone.utc) - timedelta(days=5)
        later = datetime.now(timezone.utc)

        entry_a = CollectionEntry(user_id=sample_user, film_id=film_a.id, date_added=earlier)
        entry_b = CollectionEntry(user_id=sample_user, film_id=film_b.id, date_added=later)
        db.session.add_all([entry_a, entry_b])
        db.session.commit()

        collection = get_collection(sample_user)
        titles = [f["title"] for f in collection]

        # Blade Runner was added later, so it should come first
        assert titles[0] == "Blade Runner"
        assert titles[1] == "Alien"


# ── get_watchlist sort order ─────────────────────────────────────────────────

def test_get_watchlist_returns_newest_first(app, sample_user):
    """
    get_watchlist() should return films sorted by date_added descending
    (most recently added first).
    """
    with app.app_context():
        from datetime import datetime, timezone, timedelta
        from models import Film, WatchlistEntry

        film_a = Film(title="Alien", year=1979, genre="Horror")
        film_b = Film(title="Blade Runner", year=1982, genre="Sci-Fi")
        db.session.add_all([film_a, film_b])
        db.session.commit()

        earlier = datetime.now(timezone.utc) - timedelta(days=5)
        later = datetime.now(timezone.utc)

        entry_a = WatchlistEntry(user_id=sample_user, film_id=film_a.id, date_added=earlier)
        entry_b = WatchlistEntry(user_id=sample_user, film_id=film_b.id, date_added=later)
        db.session.add_all([entry_a, entry_b])
        db.session.commit()

        watchlist = get_watchlist(sample_user)
        titles = [f["title"] for f in watchlist]

        # Blade Runner was added later, so it should come first
        assert titles[0] == "Blade Runner"
        assert titles[1] == "Alien"


def test_get_watchlist_empty_user_returns_empty_list(app, sample_user):
    """
    get_watchlist() should return an empty list when a user has no entries.
    """
    with app.app_context():
        assert get_watchlist(sample_user) == []


def test_get_watchlist_only_returns_entries_for_requested_user(app, sample_film):
    """
    get_watchlist() should not leak another user's watchlist entries.
    """
    with app.app_context():
        user_a = User(username="usera", email="usera@example.com")
        user_b = User(username="userb", email="userb@example.com")
        db.session.add_all([user_a, user_b])
        db.session.commit()

        add_to_watchlist(user_id=user_a.id, film_id=sample_film)

        assert get_watchlist(user_b.id) == []
        user_a_watchlist = get_watchlist(user_a.id)
        assert len(user_a_watchlist) == 1
        assert user_a_watchlist[0]["id"] == sample_film
