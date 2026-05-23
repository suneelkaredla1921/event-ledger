def test_out_of_order_events_produce_correct_balance(gateway_client, account_client):
    events = [
        {
            "eventId": "evt-late",
            "accountId": "acct-oo",
            "type": "DEBIT",
            "amount": 40.0,
            "currency": "USD",
            "eventTimestamp": "2026-05-20T10:00:00Z",
        },
        {
            "eventId": "evt-early",
            "accountId": "acct-oo",
            "type": "CREDIT",
            "amount": 100.0,
            "currency": "USD",
            "eventTimestamp": "2026-05-10T10:00:00Z",
        },
        {
            "eventId": "evt-mid",
            "accountId": "acct-oo",
            "type": "CREDIT",
            "amount": 25.0,
            "currency": "USD",
            "eventTimestamp": "2026-05-15T10:00:00Z",
        },
    ]

    for event in events:
        response = gateway_client.post("/events", json=event)
        assert response.status_code == 201

    balance = account_client.get("/accounts/acct-oo/balance")
    assert balance.json()["balance"] == 85.0

    listed = gateway_client.get("/events", params={"account": "acct-oo"})
    timestamps = [e["eventTimestamp"] for e in listed.json()]
    assert timestamps == sorted(timestamps)
