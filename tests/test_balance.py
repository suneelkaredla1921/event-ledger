def test_balance_is_credits_minus_debits(account_client):
    account_id = "acct-bal"
    transactions = [
        ("evt-c1", "CREDIT", 200.0),
        ("evt-d1", "DEBIT", 50.0),
        ("evt-c2", "CREDIT", 30.0),
        ("evt-d2", "DEBIT", 20.0),
    ]
    for event_id, tx_type, amount in transactions:
        response = account_client.post(
            f"/accounts/{account_id}/transactions",
            json={
                "eventId": event_id,
                "type": tx_type,
                "amount": amount,
                "currency": "USD",
                "eventTimestamp": "2026-05-15T14:02:11Z",
            },
        )
        assert response.status_code == 201

    balance = account_client.get(f"/accounts/{account_id}/balance")
    assert balance.json()["balance"] == 160.0
