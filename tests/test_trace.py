def test_trace_id_propagates_to_account_service(
    gateway_client, account_client, sample_event, monkeypatch
):
    received_trace_ids = []
    original_post = account_client.post

    def capturing_post(*args, **kwargs):
        headers = kwargs.get("headers") or {}
        received_trace_ids.append(headers.get("X-Trace-ID"))
        return original_post(*args, **kwargs)

    monkeypatch.setattr(account_client, "post", capturing_post)

    trace_id = "trace-abc-123"
    response = gateway_client.post(
        "/events",
        json=sample_event,
        headers={"X-Trace-ID": trace_id},
    )
    assert response.status_code == 201
    assert response.headers.get("X-Trace-ID") == trace_id
    assert received_trace_ids == [trace_id]
