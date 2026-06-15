from app import crud
from app.services.telegram_commands import HELP_MESSAGE, handle_telegram_command


def test_upsert_telegram_subscriber_creates_and_updates(db_session):
    created = crud.upsert_telegram_subscriber(
        db_session,
        chat_id="123",
        from_id="456",
        username="first_user",
        first_name="First",
        chat_type="private",
    )
    db_session.commit()

    updated = crud.upsert_telegram_subscriber(
        db_session,
        chat_id="123",
        from_id="456",
        username="renamed_user",
        first_name="First",
        chat_type="private",
    )
    db_session.commit()

    assert created.id == updated.id
    assert updated.username == "renamed_user"
    assert crud.list_active_telegram_chat_ids(db_session) == ["123"]


def test_stop_command_deactivates_subscriber(db_session):
    crud.upsert_telegram_subscriber(db_session, chat_id="123", chat_type="private")
    db_session.commit()

    reply = handle_telegram_command("/stop", "123", db_session)

    assert "unsubscribed" in reply
    assert crud.list_active_telegram_chat_ids(db_session) == []


def test_help_command_returns_command_list(db_session):
    assert handle_telegram_command("/help", "123", db_session) == HELP_MESSAGE


def test_upcoming_command_handles_empty_database(db_session):
    reply = handle_telegram_command("/upcoming", "123", db_session)

    assert reply == "Upcoming concerts\nNo concerts found yet."


def test_watchlist_commands_add_list_and_remove_keyword(db_session):
    watch_reply = handle_telegram_command("/watch big bang", "123", db_session)
    list_reply = handle_telegram_command("/watchlist", "123", db_session)
    unwatch_reply = handle_telegram_command("/unwatch big bang", "123", db_session)

    assert "Watching: big bang" in watch_reply
    assert "- big bang" in list_reply
    assert unwatch_reply == "Removed from watchlist: big bang"
    assert handle_telegram_command("/watchlist", "123", db_session) == "Your watchlist is empty. Add one with /watch artist name"
