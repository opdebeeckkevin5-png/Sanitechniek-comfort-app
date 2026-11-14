"""Maakt VERZONNEN testdata, zodat je de app kan proberen zonder de echte GBS-export.

Gebruik:  python maak_testdata.py
Resultaat: data/voorbeeld/gbs_voorbeeld.csv.gz en data/voorbeeld/voorbeeld_klachten.xlsx

Wat zit erin (bewust, om elke regel van de app te testen):
- 2 werkweken (ma 19/10 – vr 30/10/2026), met het winteruur op zo 25/10.
- Ma 26/10: warmteproductie levert niet tot 08:00 (aanvoer ± 19,5 °C, kringsetpoint 35 °C)
  → het is 's ochtends overal te koud.
- Zone 1.1: 's namiddags te warm (zon).
- Wo 21/10 11:40: 3 zones tegelijk 0,0 °C (voelerfout).
- Wo 28/10 10:00–13:00: datagat (alle punten tegelijk).
- Extra punten die de app moet weglaten (analog-output, AV164) en een device zonder zone (99).
- Klachten die elke beoordeling één keer geven, plus rijen die de controle moet weglaten.
"""

from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd

MAP = Path(__file__).parent / "data" / "voorbeeld"
TZ = "Europe/Brussels"
rng = np.random.default_rng(42)

ZONE_DEVICES = {"0.2": 4, "0.3": 5, "0.4": 6, "0.5": 15, "0.6": 3, "0.7": 2, "1.1": 7,
                "1.2": 8, "1.3": 9, "1.4": 10, "1.5": 11, "1.6": 12}
REFTER = "1.7"


def comfort_aan(t: pd.Timestamp) -> bool:
    """Klokprogramma: comfort ma–vr 06:00–18:00, anders stand-by."""
    return t.weekday() < 5 and 6 <= t.hour < 18


def maak_gbs() -> pd.DataFrame:
    tijden = pd.date_range("2026-10-19 00:00", "2026-10-30 23:45", freq="15min", tz=TZ)
    rijen = []
    temp = {z: 19.0 + rng.normal(0, 0.3) for z in [*ZONE_DEVICES, REFTER]}
    for t in tijden:
        koude_ochtend = t.date() == pd.Timestamp("2026-10-26").date() and t.hour < 8
        buiten = 9 + 4 * np.sin((t.hour - 9) / 24 * 2 * np.pi) + rng.normal(0, 0.3)
        kring = 35 + 0.3 * (10 - buiten) if comfort_aan(t) else 20.0
        aanvoer = 19.5 + rng.normal(0, 0.2) if koude_ochtend else kring + rng.normal(0, 0.8)
        jitter = pd.Timedelta(seconds=int(rng.integers(60, 120)))
        ts = (t + jitter).tz_convert("UTC").isoformat()
        rijen += [(ts, 500, "analog-input", 1, round(buiten, 1)),
                  (ts, 500, "analog-input", 12, round(aanvoer, 1)),
                  (ts, 500, "analog-value", 66, round(kring, 1)),
                  (ts, 500, "analog-value", 164, 435.0)]  # punt dat de app niet nodig heeft
        for zone in [*ZONE_DEVICES, REFTER]:
            sp_w = 21.0 if comfort_aan(t) else 16.0
            sp_k = 24.0 if comfort_aan(t) else 26.0
            zon = 3.5 if zone == "1.1" and 13 <= t.hour < 17 and t.weekday() < 5 else 0.0
            if comfort_aan(t) and not koude_ochtend:
                doel = sp_w + 0.5 + zon
            else:
                doel = max(16.5, buiten + 7) + zon
            temp[zone] += (doel - temp[zone]) * 0.15 + rng.normal(0, 0.05)
            waarde = round(temp[zone], 1)
            if zone in ("0.3", "0.6", "1.2") and t == pd.Timestamp("2026-10-21 11:30", tz=TZ):
                waarde = 0.0  # voelerfout
            if zone == REFTER:
                rijen += [(ts, 500, "analog-value", 191, waarde),
                          (ts, 500, "analog-value", 171, sp_w),
                          (ts, 500, "analog-value", 170, sp_k)]
            else:
                d = ZONE_DEVICES[zone]
                rijen += [(ts, d, "analog-value", 3, waarde),
                          (ts, d, "analog-value", 1, sp_w),
                          (ts, d, "analog-value", 2, sp_k),
                          (ts, d, "analog-output", 1, float(rng.integers(0, 100)))]  # kraanstand
        rijen.append((ts, 99, "analog-value", 3, 20.0))  # device zonder zone
    df = pd.DataFrame(rijen, columns=["ts", "device", "type", "instance", "waarde"])
    # datagat wo 28/10 10:00–13:00 (Belgische tijd), alle punten tegelijk
    tijd = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(TZ)
    gat = (tijd >= pd.Timestamp("2026-10-28 10:00", tz=TZ)) & (tijd < pd.Timestamp("2026-10-28 13:00", tz=TZ))
    # af en toe valt één meting weg (wordt 1 kwartier doorgetrokken)
    los = rng.random(len(df)) < 0.02
    return df[~gat & ~los].reset_index(drop=True)


def maak_klachten() -> pd.DataFrame:
    kol = ["Datum", "Tijdstip", "Duur", "Zone", "Discipline", "Soort klacht", "Ernst",
           "Raam/deur open", "Zelf aangepast", "Gemeten temp (°C)", "Omschrijving",
           "Melder (initialen)", "Beoordeling", "Oorzaak", "Opmerking technische dienst"]
    d = pd.Timestamp
    rijen = [
        # verwacht: gegrond (te koud) – warmteproductie leverde niet
        [d("2026-10-26"), time(8, 30), "Halve dag", "1.2 Calculatie (Kantoor 4)", "CV (verwarming)", "Te koud", "2 - Storend"],
        # verwacht: ongegrond – binnen de band
        [d("2026-10-22"), time(10, 0), "< 30 min", "0.4 Receptie", "CV (verwarming)", "Te warm", "1 - Licht hinderlijk"],
        # verwacht: n.t.b. – geen meting (magazijn)
        [d("2026-10-20"), time(14, 0), "Hele dag", "0.9 Magazijn 2", "CV (verwarming)", "Te koud", "2 - Storend"],
        # verwacht: n.t.b. – geen data (datagat 28/10 10:00–13:00)
        [d("2026-10-28"), time(11, 0), "30 min - 2 uur", "1.5 Directie 1", "CV (verwarming)", "Te koud", "1 - Licht hinderlijk"],
        # verwacht: n.t.b. – ander thema
        [d("2026-10-21"), time(9, 0), "Hele dag", "0.2 Uitvoering (Kantoor 2)", "Akoestiek", "Lawaai van installatie", "2 - Storend"],
        # verwacht: gegrond (te warm) – zonder tijdstip → hele werkdag
        [d("2026-10-23"), None, "Halve dag", "1.1 Boekhouding (Kantoor 3)", "Koeling", "Te warm", "2 - Storend"],
        # verwacht: ongegrond – klacht te koud, maar het was te warm
        [d("2026-10-27"), time(15, 0), "< 30 min", "1.1 Boekhouding (Kantoor 3)", "CV (verwarming)", "Te koud", "1 - Licht hinderlijk"],
        # verwacht: n.t.b. – geen meting (0.1 heeft geen data)
        [d("2026-10-29"), time(9, 15), "Halve dag", "0.1 Nazorg (Kantoor 1)", "CV (verwarming)", "Te koud", "2 - Storend"],
        # verwacht: buiten kantooruren (zaterdag, stand-by)
        [d("2026-10-24"), time(11, 0), "30 min - 2 uur", "1.6 Directie 2", "CV (verwarming)", "Te koud", "1 - Licht hinderlijk"],
        # verwacht: weggelaten – geen datum
        [None, time(9, 0), "< 30 min", "1.3 Elektro & regeling (Kantoor 5)", "CV (verwarming)", "Te koud", "1 - Licht hinderlijk"],
        # verwacht: weggelaten – onbekende zone
        [d("2026-10-20"), time(10, 0), "< 30 min", "Kantoor X", "CV (verwarming)", "Te warm", "1 - Licht hinderlijk"],
    ]
    k = pd.DataFrame([r + [None] * (len(kol) - len(r)) for r in rijen], columns=kol)
    k["Omschrijving"] = "verzonnen testklacht"
    k["Melder (initialen)"] = "XX"
    return k


def main() -> None:
    MAP.mkdir(parents=True, exist_ok=True)
    gbs = maak_gbs()
    gbs.to_csv(MAP / "gbs_voorbeeld.csv.gz", sep=";", index=False, compression="gzip")
    with pd.ExcelWriter(MAP / "voorbeeld_klachten.xlsx") as xl:
        pd.DataFrame({"Instructie": ["VERZONNEN testdata voor de comfortapp."]}).to_excel(
            xl, sheet_name="Instructie", index=False)
        maak_klachten().to_excel(xl, sheet_name="Klachten", index=False)
    print(f"{len(gbs):,} GBS-rijen en {len(maak_klachten())} klachten geschreven naar {MAP}")


if __name__ == "__main__":
    main()
