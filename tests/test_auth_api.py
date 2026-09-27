"""Authentication: login per role, invalid/inactive accounts, registration rules."""

import pytest

from app.db.models import UserRole
from tests.helpers import API, PASSWORD, auth, make_user

pytestmark = pytest.mark.db


async def test_auth_status(client):
    res = await client.get(f"{API}/auth/status")
    assert res.status_code == 200
    assert res.json()["auth_enabled"] is True


@pytest.mark.parametrize("role", [UserRole.PROFESSOR, UserRole.TA])
async def test_login_returns_role_and_me_matches(client, session, role):
    user = await make_user(session, f"{role.value}@uni.edu", role)
    res = await client.post(f"{API}/auth/login", json={"email": user.email, "password": PASSWORD})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["user"]["role"] == role.value
    me = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["role"] == role.value
    assert me.json()["email"] == user.email


async def test_invalid_login(client, session):
    await make_user(session, "prof@uni.edu", UserRole.PROFESSOR)
    wrong_pw = await client.post(f"{API}/auth/login", json={"email": "prof@uni.edu", "password": "nope-nope"})
    unknown = await client.post(f"{API}/auth/login", json={"email": "ghost@uni.edu", "password": PASSWORD})
    assert wrong_pw.status_code == 401
    assert unknown.status_code == 401
    assert wrong_pw.json()["detail"] == unknown.json()["detail"]  # no account enumeration


async def test_inactive_account_cannot_login_or_use_token(client, session):
    user = await make_user(session, "gone@uni.edu", UserRole.TA, active=False)
    res = await client.post(f"{API}/auth/login", json={"email": user.email, "password": PASSWORD})
    assert res.status_code == 403
    # A token issued before deactivation stops working too.
    me = await client.get(f"{API}/auth/me", headers=auth(user))
    assert me.status_code == 401


async def test_garbage_token_rejected(client, db_clean):
    res = await client.get(f"{API}/ta/dashboard", headers={"Authorization": "Bearer not-a-jwt"})
    assert res.status_code == 401


async def test_register_creates_ta_only(client, db_clean):
    res = await client.post(
        f"{API}/auth/register", json={"email": "new@uni.edu", "password": "longpassword", "full_name": "New TA"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["user"]["role"] == "ta"


async def test_first_user_cannot_self_register_as_professor(client, db_clean):
    # The old code made the very first registrant an instructor.
    res = await client.post(f"{API}/auth/register", json={"email": "first@uni.edu", "password": "longpassword"})
    assert res.json()["user"]["role"] == "ta"
    res = await client.post(
        f"{API}/auth/register",
        json={"email": "evil@uni.edu", "password": "longpassword", "role": "professor"},
    )
    assert res.status_code == 403


async def test_register_duplicate_email(client, session):
    await make_user(session, "dup@uni.edu", UserRole.TA)
    res = await client.post(f"{API}/auth/register", json={"email": "DUP@uni.edu", "password": "longpassword"})
    assert res.status_code == 400


async def test_role_claim_in_token_is_not_trusted(client, session):
    """Authorization reads the role from the database, not the JWT."""
    from app.core.security import create_access_token

    ta = await make_user(session, "sneaky@uni.edu", UserRole.TA)
    forged_claim = create_access_token(ta.id, {"role": "professor"})
    res = await client.get(f"{API}/professor/dashboard", headers={"Authorization": f"Bearer {forged_claim}"})
    assert res.status_code == 403


async def test_change_password(client, session):
    user = await make_user(session, "pw@uni.edu", UserRole.TA)
    bad = await client.post(
        f"{API}/auth/change-password",
        json={"current_password": "wrong-one", "new_password": "new-password-1"},
        headers=auth(user),
    )
    assert bad.status_code == 400
    ok = await client.post(
        f"{API}/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "new-password-1"},
        headers=auth(user),
    )
    assert ok.status_code == 204
    login = await client.post(f"{API}/auth/login", json={"email": user.email, "password": "new-password-1"})
    assert login.status_code == 200
