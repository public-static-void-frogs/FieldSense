# Accounts, settings, and cookie authentication

Accounts, settings, the shared field catalog and per-user field selections use
PostgreSQL. Registration starts with no selected fields. Users can create catalog
fields or select existing entries; see [persistent fields](field-storage.md).
Weather comes from Open-Meteo, and no demo domain fixtures are loaded.

## Local setup

```sh
python -m pip install -r requirements.txt
cp .env.example .env
# Fill JWT_SECRET with the output of this command; keep the same secret across restarts.
python -c "import secrets; print(secrets.token_urlsafe(48))"
alembic upgrade head
python main.py
```

The example environment file configures the database URL as
`postgresql+psycopg://olehzapara:@localhost:5432/fieldshiftnasa` (empty password).
The database must already exist. `DATABASE_URL`, `JWT_SECRET`, and `JWT_ISSUER`
are loaded from environment variables (or the local `.env`); database credentials
and the JWT issuer are not embedded in application code. The initial migration creates `users`,
`user_settings`, and Alembic's version table. It does not import demo users or
seed fields. Migration 0003 adds `fields` and `user_fields`. Run `alembic upgrade head` after pulling new migrations;
`alembic check` checks the models against the migrated schema.

Open the frontend at `http://localhost:5173` and set its `VITE_API_BASE_URL` to
`http://localhost:8000/api/v1`. Both browser URLs must use the same hostname:
`localhost` and `127.0.0.1` are different cookie sites. For HTTPS hosting, set
`COOKIE_SECURE=true`, use frontend/API hosts on the same site, and explicitly
set `CORS_ORIGINS` to trusted frontend origins. The cookie has no Domain attribute.
The API rejects unsafe requests from untrusted origins or cross-site browsers.

## Contract

All paths below are relative to `/api/v1`. Requests and responses use JSON and
camelCase. The generated `openapi.json` describes the complete schema. The frontend
sends `credentials: 'include'`; no JavaScript token storage or Authorization header
is used. Account responses contain only `id`, `fullName`, and `email`.

| Method | Path | Behavior |
| --- | --- | --- |
| POST | `/auth/register` | Create an account and settings atomically; sign in; return 201 |
| POST | `/auth/login` | Verify email/password; sign in; return 200 |
| POST | `/auth/logout` | Revoke all existing sessions for this account and clear its cookie |
| GET | `/auth/me` | Current account |
| PUT | `/auth/me` | Replace fullName and email; reject duplicate email with 409 |
| GET | `/users/me/settings` | Current user's settings |
| PUT | `/users/me/settings` | Replace current user's settings and reissue the cookie |
| GET | `/farm/profile` | Current account and saved settings, plus the saved season as availableSeasons |

Registration body:

```json
{
  "email": "farmer@example.com",
  "password": "unique-password-at-least-8-characters",
  "fullName": "Alex Farmer",
  "farmName": "My farm",
  "location": "50.45010, 30.52340",
  "latitude": 50.4501,
  "longitude": 30.5234,
  "language": "en"
}
```

`farmName`, `location`, `latitude`, `longitude`, and `language` are optional
at the API boundary. Farm name and location default to empty strings; coordinates
default to null and language to English. The frontend uses a two-step form and
requires a map selection before submission. With permission, browser geolocation
initializes the map; otherwise users can select a point manually. Coordinates are
stored in `user_settings`, with latitude in -90–90 and longitude in -180–180.
Both coordinates must be supplied together or both be null. Email is normalized to lowercase and unique. Names are
trimmed; passwords are not trimmed, are 8–128 characters at registration, and are
stored only as salted Argon2id hashes, never plaintext or reversible encryption.
There is no seeded login: register an account first.

Login body: `{"email":"farmer@example.com","password":"your-password"}`.
Unknown accounts and wrong passwords both return 401 with the same message.

Settings replacement body (farmName, coordinates, and sessionLifetimeHours have defaults):

```json
{
  "farmName": "My farm",
  "location": "50.45010, 30.52340",
  "latitude": 50.4501,
  "longitude": 30.5234,
  "season": "2026",
  "timeZone": "Europe/Kyiv",
  "units": "metric",
  "theme": "light",
  "language": "en",
  "sessionLifetimeHours": 24
}
```

A settings row belongs to one user through its primary/foreign key `user_id`.
Endpoints derive ownership from the verified JWT subject, never a client-supplied
user ID. Session lifetime accepts integer hours from 1 to 720, defaults to 24,
and determines both JWT expiry and cookie Max-Age. Saving settings renews the
current session; other sessions retain their original expiry. Invalid input
returns 422 without modifying saved settings. Conflicting account emails return 409.

JWTs use HS256 with required subject, issuer, issued-at, expiry, token ID, and
auth version claims. The API verifies signatures and expiry and checks the user's
current auth version on every protected request. Logout increments that version,
invalidating copied tokens and all existing sessions for the account. JWTs are
returned only in an HttpOnly, SameSite=Lax cookie scoped to `/api/v1`, with Secure
controlled by `COOKIE_SECURE`. Responses disable caching with `Cache-Control: no-store`.
Every resource endpoint requires a valid session; health, OpenAPI, and Swagger
remain public. Expired/missing/invalid cookies return 401. There is no refresh
token: users sign in again after expiry.

## Verification

`python -m unittest discover -s tests -v` uses isolated temporary SQLite databases
for repeatable API, persistence, validation, and user-isolation tests. It never
writes test accounts to the configured development PostgreSQL database.
Frontend integration tests start a temporary API and run the actual Alembic
migration against their own temporary database before using real HTTP requests.
