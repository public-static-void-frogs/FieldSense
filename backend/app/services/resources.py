"""Join farm ownership, help records, and map boundaries."""


def farm_profile(store, user):
    from app.schemas.auth import SettingsInput

    preferences = SettingsInput.model_validate(user.settings).model_dump(by_alias=True)
    return dict(
        preferences,
        availableSeasons=[user.settings.season],
        fullName=user.full_name,
        initials="".join(part[0] for part in user.full_name.split()[:2]).upper(),
        email=user.email,
        role="Farm owner",
        locationLabel=user.settings.location,
    )


def notifications(store):
    return []
