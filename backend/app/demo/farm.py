"""Read-only demo identity."""

from app.repositories.users import DEMO_USER_ID, User, UserSettings


def account():
    return User(
        id=DEMO_USER_ID,
        email="demo",
        full_name="Demo Farmer",
        auth_version=0,
        settings=UserSettings(
            farm_name="Demo farm",
            location="",
            latitude=None,
            longitude=None,
            season="2026",
            time_zone="America/Chicago",
            units="metric",
            theme="light",
            language="en",
            session_lifetime_hours=4,
        ),
    )
