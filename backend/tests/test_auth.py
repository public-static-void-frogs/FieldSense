import unittest
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select
from support import TEST_ISSUER, TEST_SECRET, isolated_app, register

from app.core.security import passwords
from app.main import create_app
from app.repositories.users import User, UserSettings

BASE = "/api/v1"
COOKIE = "fieldshift_access"


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.directory, self.app = isolated_app()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.app.state.engine.dispose)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def signup(self, client=None, email="farmer@example.com", **values):
        response = register(client or self.client, email, **values)
        self.assertEqual(response.status_code, 201, response.text)
        return response

    def settings(self, client=None):
        response = (client or self.client).get(BASE + "/users/me/settings")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def claims(self, token=None):
        return jwt.decode(
            token or self.client.cookies.get(COOKIE),
            TEST_SECRET,
            algorithms=["HS256"],
            issuer=TEST_ISSUER,
        )

    def test_registration_hashes_password_and_sets_one_day_http_only_cookie(self):
        response = self.signup()
        self.assertEqual(set(response.json()), {"id", "email", "fullName"})
        with self.app.state.sessions() as session:
            user = session.scalar(select(User))
            self.assertTrue(user.password_hash.startswith("$argon2id$"))
            self.assertTrue(passwords.verify("Test-password-123", user.password_hash))
            self.assertEqual(session.get(UserSettings, user.id).session_lifetime_hours, 24)
        cookie = response.headers["set-cookie"]
        for attribute in ["HttpOnly", "Max-Age=86400", "SameSite=lax", "Path=/api/v1"]:
            self.assertIn(attribute, cookie)
        claims = self.claims()
        self.assertEqual(claims["exp"] - claims["iat"], 86400)
        self.assertEqual(claims["sub"], response.json()["id"])
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_duplicate_emails_normalized_and_validation_rejects_bad_registration(self):
        self.signup(email="Farmer@EXAMPLE.com")
        self.assertEqual(register(self.client, "farmer@example.com").status_code, 409)
        for values in [
            {"password": "short"},
            {"fullName": "   "},
            {"email": "bad"},
            {"role": "admin"},
        ]:
            self.assertEqual(
                register(self.client, **{"email": "other@example.com", **values}).status_code, 422
            )
        with self.app.state.sessions() as session:
            self.assertEqual(len(session.scalars(select(User)).all()), 1)
            self.assertEqual(len(session.scalars(select(UserSettings)).all()), 1)

    def test_login_wrong_and_unknown_credentials_return_the_same_error(self):
        self.signup()
        self.client.cookies.clear()
        for email in ["farmer@example.com", "unknown@example.com"]:
            response = self.client.post(
                BASE + "/auth/login", json={"email": email, "password": "incorrect"}
            )
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json(), {"detail": "Invalid email or password"})
            self.assertNotIn("set-cookie", response.headers)
        response = self.client.post(
            BASE + "/auth/login",
            json={"email": "FARMER@example.com", "password": "Test-password-123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(BASE + "/auth/me").status_code, 200)

    def test_all_resource_routes_require_a_session_and_public_docs_stay_public(self):
        for path in [
            "/auth/me",
            "/users/me/settings",
            "/farm/profile",
            "/fields",
            "/weather/current",
            "/planning/events",
            "/maps/geojson",
        ]:
            self.assertEqual(self.client.get(BASE + path).status_code, 401, path)
        self.assertEqual(
            self.client.post(
                BASE + "/fields", json={"parcelId": 6, "name": "No", "crop": "Corn"}
            ).status_code,
            401,
        )
        for path in ["/", "/docs", "/openapi.json"]:
            self.assertEqual(self.client.get(path).status_code, 200)
        schema = self.client.get("/openapi.json").json()
        self.assertIn("security", schema["paths"][BASE + "/fields"]["get"])

    def test_two_users_have_independent_settings_and_profile(self):
        first = self.signup().json()
        other = TestClient(self.app)
        self.addCleanup(other.close)
        self.signup(other, "second@example.com", fullName="Second Farmer", farmName="Second Farm")
        original = self.settings(other)
        changed = dict(
            self.settings(),
            units="imperial",
            theme="dark",
            language="uk",
            farmName="Updated farm",
            location="Lviv",
            timeZone="Europe/Kyiv",
            sessionLifetimeHours=48,
        )
        response = self.client.put(BASE + "/users/me/settings", json=changed)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), changed)
        self.assertEqual(self.settings(other), original)
        profile = self.client.get(BASE + "/farm/profile").json()
        self.assertEqual(profile["farmName"], "Updated farm")
        self.assertEqual(profile["fullName"], "Test Farmer")
        self.assertEqual(profile["sessionLifetimeHours"], 48)
        self.assertEqual(self.client.get(f"{BASE}/users/{first['id']}/settings").status_code, 404)
        self.assertEqual(
            self.client.put(
                BASE + "/users/me/settings", json={**changed, "userId": first["id"]}
            ).status_code,
            422,
        )
        # New accounts have no preselected fields.
        self.assertEqual(
            self.client.get(BASE + "/fields").json(), other.get(BASE + "/fields").json()
        )

    def test_session_lifetime_reissues_current_cookie_and_controls_next_login(self):
        self.signup()
        settings = dict(self.settings(), sessionLifetimeHours=2)
        response = self.client.put(BASE + "/users/me/settings", json=settings)
        self.assertIn("Max-Age=7200", response.headers["set-cookie"])
        claims = self.claims()
        self.assertEqual(claims["exp"] - claims["iat"], 7200)
        self.client.cookies.clear()
        response = self.client.post(
            BASE + "/auth/login",
            json={"email": "farmer@example.com", "password": "Test-password-123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Max-Age=7200", response.headers["set-cookie"])

    def test_settings_validation_does_not_modify_saved_values(self):
        self.signup()
        original = self.settings()
        for key, values in {
            "sessionLifetimeHours": [0, -1, 721, 1.5, True],
            "units": ["invalid"],
            "language": ["fr"],
            "timeZone": ["Unknown/Zone"],
        }.items():
            for value in values:
                response = self.client.put(
                    BASE + "/users/me/settings", json={**original, key: value}
                )
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.settings(), original)

    def test_expired_tampered_wrong_algorithm_and_missing_claim_tokens_are_rejected(self):
        self.signup()
        claims = self.claims()
        expired = {
            **claims,
            "iat": datetime.now(timezone.utc) - timedelta(days=2),
            "exp": datetime.now(timezone.utc) - timedelta(days=1),
        }
        missing = {key: value for key, value in claims.items() if key != "exp"}
        tokens = [
            jwt.encode(expired, TEST_SECRET, algorithm="HS256"),
            jwt.encode(claims, "other-secret-key-which-is-more-than-32-bytes", algorithm="HS256"),
            jwt.encode(claims, TEST_SECRET, algorithm="HS384"),
            jwt.encode(missing, TEST_SECRET, algorithm="HS256"),
            "invalid-token",
        ]
        self.client.cookies.clear()
        for token in tokens:
            self.client.cookies.set(COOKIE, token)
            self.assertEqual(self.client.get(BASE + "/auth/me").status_code, 401)

    def test_logout_clears_cookie_and_revokes_copied_tokens(self):
        self.signup()
        copied = self.client.cookies.get(COOKIE)
        response = self.client.post(BASE + "/auth/logout")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Max-Age=0", response.headers["set-cookie"])
        self.assertEqual(self.client.get(BASE + "/auth/me").status_code, 401)
        self.client.cookies.set(COOKIE, copied)
        self.assertEqual(self.client.get(BASE + "/auth/me").status_code, 401)
        self.client.cookies.clear()
        self.assertEqual(
            self.client.post(
                BASE + "/auth/login",
                json={"email": "farmer@example.com", "password": "Test-password-123"},
            ).status_code,
            200,
        )

    def test_profile_update_and_duplicate_email_rollback(self):
        self.signup()
        other = TestClient(self.app)
        self.addCleanup(other.close)
        self.signup(other, "other@example.com")
        response = self.client.put(
            BASE + "/auth/me", json={"fullName": "Changed Farmer", "email": "CHANGED@example.com"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "changed@example.com")
        response = self.client.put(
            BASE + "/auth/me", json={"fullName": "Should rollback", "email": "other@example.com"}
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get(BASE + "/auth/me").json()["fullName"], "Changed Farmer")

    def test_users_settings_and_signing_key_survive_app_restart(self):
        self.signup()
        changed = dict(self.settings(), farmName="Persistent farm", language="uk")
        self.assertEqual(
            self.client.put(BASE + "/users/me/settings", json=changed).status_code, 200
        )
        second_app = create_app(self.app.state.config)
        self.addCleanup(second_app.state.engine.dispose)
        with TestClient(second_app) as restarted:
            restarted.cookies.set(COOKIE, self.client.cookies.get(COOKIE))
            self.assertEqual(self.settings(restarted), changed)
            restarted.cookies.clear()
            self.assertEqual(
                restarted.post(
                    BASE + "/auth/login",
                    json={"email": "farmer@example.com", "password": "Test-password-123"},
                ).status_code,
                200,
            )

    def test_cors_credentials_origin_protection_and_secure_cookie_configuration(self):
        response = self.client.options(
            BASE + "/auth/login",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")
        self.assertEqual(response.headers["access-control-allow-credentials"], "true")
        self.assertEqual(
            self.client.post(
                BASE + "/auth/register", headers={"Origin": "https://evil.example"}, json={}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                BASE + "/auth/logout", headers={"Sec-Fetch-Site": "cross-site"}
            ).status_code,
            403,
        )
        self.app.state.config.cookie_secure = True
        self.assertIn("Secure", self.signup().headers["set-cookie"])

    def test_missing_or_short_signing_secret_fails_at_startup(self):
        self.app.state.config.jwt_secret = "short"
        with self.assertRaisesRegex(ValueError, "JWT_SECRET"):
            with TestClient(self.app):
                pass

    def test_optional_farm_name_and_map_coordinates_are_saved(self):
        response = self.client.post(
            BASE + "/auth/register",
            json={
                "email": "map@example.com",
                "password": "Test-password-123",
                "fullName": "Map Farmer",
                "latitude": 50.4501,
                "longitude": 30.5234,
                "location": "50.45010, 30.52340",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        settings = self.settings()
        self.assertEqual(settings["farmName"], "")
        self.assertEqual(settings["latitude"], 50.4501)
        self.assertEqual(settings["longitude"], 30.5234)
        self.assertEqual(self.client.get(BASE + "/farm/profile").json()["latitude"], 50.4501)
        self.assertEqual(
            self.client.put(
                BASE + "/users/me/settings", json={**settings, "farmName": "  "}
            ).status_code,
            200,
        )
        self.assertEqual(self.settings()["farmName"], "")
        second_app = create_app(self.app.state.config)
        self.addCleanup(second_app.state.engine.dispose)
        with TestClient(second_app) as restarted:
            restarted.cookies.set(COOKIE, self.client.cookies.get(COOKIE))
            self.assertEqual(self.settings(restarted)["longitude"], 30.5234)

    def test_coordinate_validation_rejects_invalid_and_unpaired_points(self):
        self.signup()
        original = self.settings()
        for point in [
            {"latitude": 91, "longitude": 0},
            {"latitude": 0, "longitude": -181},
            {"latitude": 50.45},
            {"longitude": 30.52},
            {"latitude": True, "longitude": False},
        ]:
            self.assertEqual(
                self.client.put(
                    BASE + "/users/me/settings", json={**original, **point}
                ).status_code,
                422,
            )
        self.assertEqual(self.settings(), original)

    def test_configured_issuer_is_required_and_verified(self):
        self.signup()
        claims = self.claims()
        self.assertEqual(claims["iss"], TEST_ISSUER)
        token = jwt.encode({**claims, "iss": "other-issuer"}, TEST_SECRET, algorithm="HS256")
        self.client.cookies.clear()
        self.client.cookies.set(COOKIE, token)
        self.assertEqual(self.client.get(BASE + "/auth/me").status_code, 401)
        self.app.state.config.jwt_issuer = ""
        with self.assertRaisesRegex(ValueError, "JWT_ISSUER"):
            with TestClient(self.app):
                pass
