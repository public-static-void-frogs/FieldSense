"""Aggregate selected field areas; observations stay empty until measured."""

COLORS = ["#476b3c", "#b8954d", "#345865", "#8c9e64", "#a46e56", "#7a7096"]


def charts(store, days, metric):
    totals = {}
    for field in store.fields():
        crop = field["crop"] or "Not supplied"
        totals[crop] = totals.get(crop, 0) + field["area"]
    return dict(
        trends=[],
        cropAreas=[
            dict(name=name, area=round(area, 1), fill=COLORS[index % len(COLORS)])
            for index, (name, area) in enumerate(totals.items())
        ],
    )
