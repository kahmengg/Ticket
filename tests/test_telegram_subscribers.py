from app import crud


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
