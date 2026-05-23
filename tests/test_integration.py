def test_full_gateway_to_account_flow(gateway_client, account_client, sample_event):
    create = gateway_client.post("/events", json=sample_event)
    assert create.status_code == 201
    body = create.json()
    assert body["eventId"] == "evt-001"

    fetched = gateway_client.get("/events/evt-001")
    assert fetched.status_code == 200
    assert fetched.json() == body

    listed = gateway_client.get("/events", params={"account": "acct-123"})
    assert len(listed.json()) == 1

    balance = account_client.get("/accounts/acct-123/balance")
    assert balance.json()["balance"] == 150.0

    gateway_health = gateway_client.get("/health")
    assert gateway_health.status_code == 200
    assert gateway_health.json()["databaseConnected"] is True

    account_health = account_client.get("/health")
    assert account_health.status_code == 200
    assert account_health.json()["databaseConnected"] is True
