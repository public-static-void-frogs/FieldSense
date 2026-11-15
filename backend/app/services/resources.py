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
        role="Demo visitor" if user.is_demo else "Farm owner",
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
        roles="Data engineer, AI engineer",
        alt="Kate, a curious frog scientist in glasses and a lab coat holding a seedling vial",
        linkedin="https://www.linkedin.com/in/kateryna-prylutska/",
    ),
    dict(
        id="polina",
        name="Polina Shuhaieva",
        roles="Machine learning and computer vision engineer",
        alt="Polina, a cheerful frog with a lavender bow examining a leaf with a camera",
        linkedin="https://www.linkedin.com/in/polina-shuhaieva-018435445/",
    ),
    dict(
        id="volodymyr",
        name="Volodymyr Shargorodskyy",
        roles="Machine learning and computer vision engineer",
        alt="Volodymyr, an athletic frog in a blue tank top with a dumbbell and a notebook",
        linkedin="https://www.linkedin.com/in/volodymyr-shargorodskyy/",
    ),
    dict(
        id="roman",
        name="Roman Piznak",
        roles="Machine learning engineer, data scientist",
        alt="Roman, an energetic frog researcher juggling a notebook and a laptop",
        linkedin="https://www.linkedin.com/in/roman-piznak/",
    ),
]


def team():
    return [dict(member) for member in TEAM]


SOURCES = [
    dict(
        key="power",
        name="NASA POWER (Prediction Of Worldwide Energy Resources), daily, AG community",
        url="https://power.larc.nasa.gov/",
    ),
    dict(
        key="gpm-imerg",
        name="GPM IMERG Final Precipitation, Level 3, daily, 0.1°, Version 07 (GPM_3IMERGDF)",
        url="https://www.earthdata.nasa.gov/data/catalog/ges-disc-gpm-3imergdf-07",
    ),
    dict(
        key="smap-l4",
        name="SMAP L4 Global 3-hourly 9 km Surface and Root Zone Soil Moisture (SPL4SMGP, version 8)",
        url="https://nsidc.org/data/spl4smgp/versions/8",
    ),
    dict(
        key="hls",
        name="NASA Harmonized Landsat Sentinel-2 (HLS) v2.0: HLSS30 and HLSL30",
        url="https://www.earthdata.nasa.gov/data/projects/hls",
    ),
    dict(
        key="nex-gddp-cmip6",
        name="NASA NEX-GDDP-CMIP6",
        url="https://www.nccs.nasa.gov/services/data-collections/land-based-products/nex-gddp-cmip6",
    ),
    dict(
        key="nass-csb",
        name="USDA NASS Crop Sequence Boundaries (CSB) with Cropland Data Layer (CDL) crop codes",
        url="https://www.nass.usda.gov/research-and-science/crop-sequence-boundaries",
    ),
    dict(
        key="nass-yields",
        name="USDA NASS Quick Stats: county crop yields",
        url="https://quickstats.nass.usda.gov/",
    ),
    dict(
        key="nass-progress",
        name="USDA NASS Quick Stats: Crop Progress",
        url="https://quickstats.nass.usda.gov/",
    ),
    dict(
        key="sentinel-1",
        name="Copernicus Sentinel-1 IW GRD, Radiometrically Terrain Corrected (Microsoft Planetary Computer sentinel-1-rtc)",
        url="https://planetarycomputer.microsoft.com/dataset/sentinel-1-rtc",
    ),
    dict(
        key="gridmet",
        name="gridMET (University of Idaho)",
        url="https://salusmodel.ees.msu.edu/GRIDMET",
    ),
    dict(
        key="eddi",
        name="NOAA PSL Evaporative Demand Drought Index (EDDI)",
        url="https://psl.noaa.gov/eddi/",
    ),
    dict(
        key="usdm",
        name="U.S. Drought Monitor (USDM)",
        url="https://droughtmonitor.unl.edu/",
    ),
    dict(
        key="rma-col",
        name="USDA RMA Cause of Loss (Summary of Business, month of loss, “colsom”)",
        url="https://pubfs-rma.fpac.usda.gov/pub/Web_Data_Files/Summary_of_Business/cause_of_loss/index.html",
    ),
    dict(
        key="ssurgo",
        name="USDA NRCS gSSURGO / gNATSGO via Soil Data Access (SDA)",
        url="https://www.nrcs.usda.gov/resources/data-and-reports/soil-survey-geographic-database-ssurgo",
    ),
]


def sources():
    return [dict(source) for source in SOURCES]
