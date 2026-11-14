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


TEAM = [
    dict(
        id="oleh",
        name="Oleh Zapara",
        roles="Full-stack engineer, product owner, project manager",
        alt="Oleh, a friendly frog farmer with a straw hat, working on a laptop",
        linkedin="https://www.linkedin.com/in/oleh-zapara/",
    ),
    dict(
        id="kate",
        name="Kateryna Prylutska",
        roles="Data engineer, data scientist",
        alt="Kate, a curious frog scientist in glasses and a lab coat holding a seedling vial",
        linkedin="https://www.linkedin.com/in/kateryna-prylutska/",
    ),
    dict(
        id="polina",
        name="Polina Shuhaieva",
        roles="ML and computer vision",
        alt="Polina, a cheerful frog with a lavender bow examining a leaf with a camera",
        linkedin="https://www.linkedin.com/in/polina-shuhaieva-018435445/",
    ),
    dict(
        id="volodymyr",
        name="Volodymyr Shargorodskyy",
        roles="ML, data and research",
        alt="Volodymyr, an athletic frog in a blue tank top with a dumbbell and a notebook",
        linkedin="https://www.linkedin.com/in/volodymyr-shargorodskyy/",
    ),
    dict(
        id="roman",
        name="Roman Piznak",
        roles="ML, data and research",
        alt="Roman, an energetic frog researcher juggling a notebook and a laptop",
        linkedin="https://www.linkedin.com/in/roman-piznak/",
    ),
]


def team():
    return [dict(member) for member in TEAM]
