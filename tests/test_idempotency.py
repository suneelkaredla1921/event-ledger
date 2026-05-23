def test_duplicate_event_returns_original_without_double_balance(
    gateway_client, account_client, sample_event
):
    first = gateway_client.post("/events", json=sample_event)
    assert first.status_code == 201

    duplicate = gateway_client.post("/events", json=sample_event)
    assert duplicate.status_code == 200
    assert duplicate.json() == first.json()

    balance = account_client.get("/accounts/acct-123/balance")
    assert balance.json()["balance"] == 150.0

    listed = gateway_client.get("/events", params={"account": "acct-123"})
    assert len(listed.json()) == 1
