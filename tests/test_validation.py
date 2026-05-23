def test_rejects_missing_required_fields(gateway_client):
    response = gateway_client.post("/events", json={})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "eventId" in detail or "required" in detail.lower()


def test_rejects_invalid_type(gateway_client, sample_event):
    sample_event["type"] = "TRANSFER"
    response = gateway_client.post("/events", json=sample_event)
    assert response.status_code == 422
    assert "CREDIT" in response.json()["detail"] or "DEBIT" in response.json()["detail"]


def test_rejects_non_positive_amount(gateway_client, sample_event):
    sample_event["amount"] = 0
    response = gateway_client.post("/events", json=sample_event)
    assert response.status_code == 422
    assert "amount" in response.json()["detail"].lower()


def test_rejects_invalid_timestamp(gateway_client, sample_event):
    sample_event["eventTimestamp"] = "not-a-date"
    response = gateway_client.post("/events", json=sample_event)
    assert response.status_code == 422
    assert "eventTimestamp" in response.json()["detail"]


def test_accepts_optional_metadata(gateway_client, sample_event):
    sample_event["metadata"] = None
    response = gateway_client.post("/events", json=sample_event)
    assert response.status_code == 201
