"""The per-request Supabase client must talk to the database as the signed-in user."""

from supabase import ClientOptions, create_client


def test_user_token_is_sent_to_postgrest_and_never_shared_between_requests():
    def client_for(token):
        options = ClientOptions(headers={"Authorization": f"Bearer {token}"}, auto_refresh_token=False, persist_session=False)
        return create_client("https://abc.supabase.co", "sb_publishable_key", options)

    a, b = client_for("JWT-A"), client_for("JWT-B")
    headers_a = a.postgrest.session.headers
    assert headers_a["authorization"] == "Bearer JWT-A"  # not the publishable key: RLS sees the user
    assert headers_a["apikey"] == "sb_publishable_key"
    assert b.postgrest.session.headers["authorization"] == "Bearer JWT-B"
    assert a.postgrest.session.headers["authorization"] == "Bearer JWT-A"
