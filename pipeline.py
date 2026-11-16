"""Pijplijn comfortapp kantoor – één pure functie per stap, zonder Streamlit.

Elke stap geeft een tuple terug: (resultaat, StapInfo).
StapInfo zegt hoeveel rijen erin gingen, hoeveel eruit kwamen en waarom er rijen wegvielen.
Zo kan de app (en jij in het no-AI gesprek) elke stap apart tonen en narekenen.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

TZ = "Europe/Brussels"
KWARTIER = pd.Timedelta(minutes=15)
DATA_MAP = Path(__file__).parent / "data"

# Standaardband (Typebestek 105, tabel B1.2.-1, uit NBN EN ISO 7730 cat. B)
STANDAARD_BAND = {"winter": (20.0, 24.0), "zomer": (23.0, 26.0)}
WINTERMAANDEN = {10, 11, 12, 1, 2, 3, 4}  # okt t.e.m. apr

# Kantooruren: ma–vr, kwartieren 08:00 t.e.m. 16:45 (dus tot 17:00)
KANTOOR_START_UUR = 8
KANTOOR_EINDE_UUR = 17

CENTRAAL_DEVICE = 500
CENTRAAL = "centraal"

# Welke BACnet-punten hebben we nodig? (type, instance) -> grootheid
ZONE_PUNTEN = {
    ("analog-value", 3): "ruimtetemp",
    ("analog-value", 1): "sp_verwarmen",
    ("analog-value", 2): "sp_koelen",
}
REFTER_PUNTEN = {  # device 500, VAV-voeler zone 1.7
    ("analog-value", 191): "ruimtetemp",
    ("analog-value", 171): "sp_verwarmen",
    ("analog-value", 170): "sp_koelen",
}
CENTRALE_PUNTEN = {  # device 500
    ("analog-input", 1): "buitentemp",
    ("analog-input", 12): "aanvoer",
    ("analog-value", 66): "kringsetpoint",
}

VOELER_MIN, VOELER_MAX = 10.0, 35.0
VENSTER = pd.Timedelta(minutes=30)
OORZAAK_DREMPEL = 3.0  # aanvoer > 3 °C onder kringsetpoint = warmteproductie levert niet
GEMETEN_DREMPEL = 2.0  # zelf gemeten temp > 2 °C buiten het GBS-bereik = markeren (geen invloed op beoordeling)

# Categorieën
BINNEN, TE_KOUD, TE_WARM, GEEN_DATA = "binnen band", "te koud", "te warm", "geen data"
GEGROND = "gegrond"
ONGEGROND = "ongegrond"
NTB_DATA = "niet te beoordelen – geen data"
NTB_METING = "niet te beoordelen – geen meting"
NTB_THEMA = "niet te beoordelen – ander thema"

PRIVACY_KOLOMMEN = ["Melder (initialen)", "Omschrijving"]


@dataclass
class StapInfo:
    nr: str
    naam: str
    rijen_in: int | None
    rijen_uit: int
    weg: dict[str, int] = field(default_factory=dict)  # reden -> aantal rijen
    soort: str = "filter"  # "filter" (rijen vallen weg) of "omvormen" (rijen samengevoegd/omgezet)
    uitleg: str = ""

    @property
    def totaal_weg(self) -> int:
        return sum(self.weg.values())

    @property
    def klopt(self) -> bool | None:
        """Controle: rijen in = rijen uit + weggevallen rijen (enkel bij filterstappen)."""
        if self.soort != "filter" or self.rijen_in is None:
            return None
        return self.rijen_in == self.rijen_uit + self.totaal_weg


# ---------------------------------------------------------------------------
# Referentiedata
# ---------------------------------------------------------------------------

def naar_kwartier(tijden):
    """Afronden naar het begin van het kwartier. Gebeurt in UTC, want op de nacht van het
    winteruur (25/10) bestaat 02:00–03:00 Belgische tijd twee keer."""
    return tijden.dt.tz_convert("UTC").dt.floor("15min").dt.tz_convert(TZ)


def lees_zones(pad: str | Path = DATA_MAP / "zones_koppeling.csv") -> pd.DataFrame:
    zones = pd.read_csv(pad, sep=";", dtype={"gbs_device": "Int64"})
    zones["zone"] = zones["formulier_zone"].str.split(" ").str[0]  # "1.2 Calculatie (…)" -> "1.2"
    zones["naam"] = zones["formulier_zone"]
    return zones


def lees_feestdagen(pad: str | Path = DATA_MAP / "feestdagen.csv") -> set:
    f = pd.read_csv(pad, sep=";", parse_dates=["datum"])
    return set(f["datum"].dt.date)


def comfortzones(zones: pd.DataFrame) -> pd.DataFrame:
    """Zones waarvoor we comfort berekenen: geklimatiseerde kantoren (ook 0.1 zonder data)."""
    return zones[zones["zonetype"] == "kantoor geklimatiseerd"]


# ---------------------------------------------------------------------------
# Stap 1–7: GBS-data
# ---------------------------------------------------------------------------

def stap1_inlezen(bestand) -> tuple[pd.DataFrame, StapInfo]:
    """GBS-export inlezen (.csv.gz, ;-gescheiden, kolommen ts;device;type;instance;waarde)."""
    df = pd.read_csv(bestand, sep=";", compression="gzip")
    verwacht = {"ts", "device", "type", "instance", "waarde"}
    ontbreekt = verwacht - set(df.columns)
    if ontbreekt:
        raise ValueError(f"Kolommen ontbreken in de GBS-export: {sorted(ontbreekt)}")
    info = StapInfo("1", "GBS-data inlezen", None, len(df), soort="omvormen",
                    uitleg="Elke rij = één meting van één BACnet-punt. Tijd staat in UTC.")
    return df, info


def stap2_nodige_punten(df: pd.DataFrame) -> tuple[pd.DataFrame, StapInfo]:
    """Enkel de BACnet-punten houden die we nodig hebben en ze een naam (grootheid) geven."""
    sleutel = list(zip(df["type"], df["instance"]))
    is_500 = df["device"] == CENTRAAL_DEVICE
    punten_500 = {**REFTER_PUNTEN, **CENTRALE_PUNTEN}
    grootheid = [
        (punten_500 if c else ZONE_PUNTEN).get(k)
        for k, c in zip(sleutel, is_500)
    ]
    uit = df.assign(grootheid=grootheid)
    uit = uit[uit["grootheid"].notna()].copy()
    n_nodig = len(uit)
    # Een ruwe export bevat ook binaire punten ("active"/"inactive"), waardoor pandas de hele
    # kolom als tekst inleest. Na het filteren zetten we 'waarde' om naar een getal;
    # wat geen getal is, valt weg en wordt geteld.
    uit["waarde"] = pd.to_numeric(uit["waarde"], errors="coerce")
    uit = uit[uit["waarde"].notna()]
    # Refter-punten van device 500 krijgen later zone 1.7; centrale punten krijgen "centraal"
    uit["is_refter"] = [
        (t, i) in REFTER_PUNTEN and d == CENTRAAL_DEVICE
        for t, i, d in zip(uit["type"], uit["instance"], uit["device"])
    ]
    info = StapInfo("2", "Enkel de nodige punten houden", len(df), len(uit),
                    {"ander BACnet-punt (niet nodig)": len(df) - n_nodig,
                     "waarde is geen getal (leeg of tekst)": n_nodig - len(uit)},
                    uitleg="Zones: AV3 ruimtetemp, AV1 SP verwarmen, AV2 SP koelen. "
                           "Device 500: AI1 buitentemp, AI12 aanvoer, AV66 kringsetpoint, "
                           "AV191/171/170 refter (VAV-voeler).")
    return uit, info


def stap3_zone_koppelen(df: pd.DataFrame, zones: pd.DataFrame) -> tuple[pd.DataFrame, StapInfo]:
    """Device -> zone via zones_koppeling.csv. Centrale punten krijgen zone 'centraal'."""
    koppel = zones.dropna(subset=["gbs_device"])
    koppel = koppel[koppel["gbs_device"] != CENTRAAL_DEVICE]
    device_naar_zone = dict(zip(koppel["gbs_device"].astype(int), koppel["zone"]))
    zone_17 = zones.loc[zones["gbs_device"] == CENTRAAL_DEVICE, "zone"]
    zone_17 = zone_17.iloc[0] if len(zone_17) else "1.7"

    zone = df["device"].map(device_naar_zone)
    zone = zone.where(~df["is_refter"], zone_17)
    centraal = (df["device"] == CENTRAAL_DEVICE) & ~df["is_refter"]
    zone = zone.where(~centraal, CENTRAAL)
    uit = df.assign(zone=zone)
    uit = uit[uit["zone"].notna()].drop(columns=["is_refter"])
    info = StapInfo("3", "Zone koppelen", len(df), len(uit),
                    {"device zonder zone": len(df) - len(uit)},
                    uitleg="Koppeling volgens het inrichtingsplan 2018 (data/zones_koppeling.csv).")
    return uit, info


def stap3b_voelerfout(df: pd.DataFrame) -> tuple[pd.DataFrame, StapInfo]:
    """Onmogelijke ruimtetemperaturen (< 10 °C of > 35 °C) weglaten. Andere punten blijven."""
    fout = (df["grootheid"] == "ruimtetemp") & ~df["waarde"].between(VOELER_MIN, VOELER_MAX)
    uit = df[~fout]
    info = StapInfo("3b", "Onmogelijke temperaturen weglaten", len(df), len(uit),
                    {f"voelerfout (ruimtetemp < {VOELER_MIN:g} of > {VOELER_MAX:g} °C)": int(fout.sum())},
                    uitleg="Enkel op ruimtetemperaturen: buitentemp < 10 °C en aanvoer > 35 °C zijn normaal.")
    return uit, info


def voelerfouten(df: pd.DataFrame) -> pd.DataFrame:
    """De rijen die stap 3b weglaat (om te tonen in de app)."""
    fout = (df["grootheid"] == "ruimtetemp") & ~df["waarde"].between(VOELER_MIN, VOELER_MAX)
    return df[fout]


def stap4_tijdzone(df: pd.DataFrame) -> tuple[pd.DataFrame, StapInfo]:
    """UTC -> Belgische tijd (Europe/Brussels, houdt rekening met zomer-/winteruur)."""
    ts = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    uit = df.assign(tijd=ts.dt.tz_convert(TZ))
    ongeldig = uit["tijd"].isna()
    uit = uit[~ongeldig].drop(columns=["ts"])
    info = StapInfo("4", "UTC → Belgische tijd", len(df), len(uit),
                    {"ongeldig tijdstip": int(ongeldig.sum())},
                    uitleg="Winteruur op zo 25/10: 03:00 zomertijd wordt 02:00 wintertijd.")
    return uit, info


def stap5_per_kwartier(df: pd.DataFrame, zones: pd.DataFrame) -> tuple[pd.DataFrame, StapInfo]:
    """Per kwartier gelijkzetten (lang formaat: kwartier, zone, grootheid, waarde).

    - Kwartier krijgt het label van zijn begin: '08:15' = metingen 08:15:00–08:29:59.
    - Waarde = laatste meting van dat kwartier.
    - Ontbreekt een kwartier: vorige waarde max. 1 kwartier doortrekken; daarna leeg.
    - Elke comfortzone krijgt een volledig rooster, ook zones zonder data (0.1).
    """
    df = df.assign(kwartier=naar_kwartier(df["tijd"]))
    rooster = pd.date_range(df["kwartier"].min(), df["kwartier"].max(), freq="15min")
    laatste = (df.sort_values("tijd")
                 .groupby(["zone", "grootheid", "kwartier"], observed=True)["waarde"].last())

    combinaties = {(z, g) for z in comfortzones(zones)["zone"]
                   for g in ("ruimtetemp", "sp_verwarmen", "sp_koelen")}
    combinaties |= {(CENTRAAL, g) for g in CENTRALE_PUNTEN.values()}
    combinaties |= set(laatste.index.droplevel("kwartier").unique())

    stukken = []
    for zone, grootheid in sorted(combinaties):
        try:
            reeks = laatste.loc[(zone, grootheid)]
        except KeyError:
            reeks = pd.Series(dtype=float)
        reeks = reeks.reindex(rooster)
        gemeten = reeks.notna()
        gevuld = reeks.ffill(limit=1)
        stukken.append(pd.DataFrame({
            "kwartier": rooster, "zone": zone, "grootheid": grootheid,
            "waarde": gevuld.to_numpy(),
            "doorgetrokken": (~gemeten & gevuld.notna()).to_numpy(),
        }))
    uit = pd.concat(stukken, ignore_index=True)
    info = StapInfo("5", "Per kwartier gelijkzetten", len(df), len(uit), soort="omvormen",
                    uitleg=(f"{len(df):,} metingen samengevoegd tot een rooster van {len(rooster):,} kwartieren "
                            f"× {len(combinaties)} reeksen. {int(uit['doorgetrokken'].sum()):,} kwartieren "
                            f"doorgetrokken (1 kwartier), {int(uit['waarde'].isna().sum()):,} kwartieren leeg."
                            ).replace(",", "."))
    return uit, info


def breed_per_zone(kwartier: pd.DataFrame) -> pd.DataFrame:
    """Lang -> breed: per (kwartier, zone) de kolommen ruimtetemp, sp_verwarmen, sp_koelen."""
    z = kwartier[kwartier["zone"] != CENTRAAL]
    breed = z.pivot_table(index=["kwartier", "zone"], columns="grootheid", values="waarde",
                          aggfunc="first", dropna=False).reset_index()
    breed.columns.name = None
    for kol in ("ruimtetemp", "sp_verwarmen", "sp_koelen"):
        if kol not in breed:
            breed[kol] = float("nan")
    return breed


def centraal_breed(kwartier: pd.DataFrame) -> pd.DataFrame:
    c = kwartier[kwartier["zone"] == CENTRAAL]
    breed = c.pivot_table(index="kwartier", columns="grootheid", values="waarde",
                          aggfunc="first", dropna=False)
    breed.columns.name = None
    for kol in CENTRALE_PUNTEN.values():
        if kol not in breed:
            breed[kol] = float("nan")
    return breed


def is_kantooruur(tijden: pd.Series, feestdagen: set) -> pd.Series:
    t = pd.to_datetime(tijden)
    return ((t.dt.weekday < 5)
            & (t.dt.hour >= KANTOOR_START_UUR) & (t.dt.hour < KANTOOR_EINDE_UUR)
            & ~t.dt.date.isin(feestdagen))


def stap6_kantooruren(breed: pd.DataFrame, zones: pd.DataFrame, feestdagen: set
                      ) -> tuple[pd.DataFrame, StapInfo]:
    """Kantooruren aanduiden (ma–vr 8–17 u, zonder feestdagen). Enkel comfortzones blijven."""
    comfort = set(comfortzones(zones)["zone"])
    uit = breed[breed["zone"].isin(comfort)].copy()
    uit["kantooruur"] = is_kantooruur(uit["kwartier"], feestdagen)
    uit["dag"] = uit["kwartier"].dt.date
    n_kantoor = int(uit["kantooruur"].sum())
    info = StapInfo("6", "Kantooruren aanduiden", len(breed), len(uit),
                    {"geen comfortzone": len(breed) - len(uit)},
                    uitleg=(f"{n_kantoor:,} van {len(uit):,} zone-kwartieren vallen in de kantooruren. "
                            "De rest (nacht, weekend, feestdag) blijft staan maar telt niet mee "
                            "voor het comfort, tenzij je 'ook nacht/weekend' aanvinkt.").replace(",", "."))
    return uit, info


def band_voor(tijden: pd.Series, band: dict) -> tuple[pd.Series, pd.Series]:
    """Ondergrens en bovengrens per tijdstip volgens het seizoen (maand)."""
    winter = pd.to_datetime(tijden).dt.month.isin(WINTERMAANDEN)
    onder = winter.map({True: band["winter"][0], False: band["zomer"][0]}).astype(float)
    boven = winter.map({True: band["winter"][1], False: band["zomer"][1]}).astype(float)
    return onder, boven


def stap7_toestand(df: pd.DataFrame, band: dict = STANDAARD_BAND) -> tuple[pd.DataFrame, StapInfo]:
    """Toestand per kwartier: binnen band / te koud / te warm / geen data."""
    onder, boven = band_voor(df["kwartier"], band)
    t = df["ruimtetemp"]
    toestand = pd.Series(BINNEN, index=df.index)
    toestand[t < onder] = TE_KOUD
    toestand[t > boven] = TE_WARM
    toestand[t.isna()] = GEEN_DATA
    uit = df.assign(ondergrens=onder, bovengrens=boven, toestand=toestand)
    telling = uit["toestand"].value_counts().to_dict()
    info = StapInfo("7", "Toestand per kwartier", len(df), len(uit), soort="omvormen",
                    uitleg="Alle kwartieren: " + " · ".join(f"{k}: {v:,}".replace(",", ".")
                                                             for k, v in telling.items()))
    return uit, info


# ---------------------------------------------------------------------------
# Samenvattingen voor de app
# ---------------------------------------------------------------------------

def per_zone(toestand: pd.DataFrame, zones: pd.DataFrame) -> pd.DataFrame:
    """A1: per zone het % binnen/te koud/te warm (van de kwartieren mét data) en % geen data."""
    tel = pd.crosstab(toestand["zone"], toestand["toestand"])
    for k in (BINNEN, TE_KOUD, TE_WARM, GEEN_DATA):
        if k not in tel:
            tel[k] = 0
    met_data = tel[BINNEN] + tel[TE_KOUD] + tel[TE_WARM]
    totaal = met_data + tel[GEEN_DATA]
    noemer = met_data.where(met_data > 0)
    uit = pd.DataFrame({
        "kwartieren met data": met_data,
        "% buiten band": (tel[TE_KOUD] + tel[TE_WARM]) / noemer * 100,
        "% te koud": tel[TE_KOUD] / noemer * 100,
        "% te warm": tel[TE_WARM] / noemer * 100,
        "% geen data": tel[GEEN_DATA] / totaal.where(totaal > 0) * 100,
    })
    namen = dict(zip(zones["zone"], zones["naam"]))
    uit.index = [namen.get(z, z) for z in uit.index]
    uit.index.name = "Zone"
    return uit.sort_values("% buiten band", ascending=False, na_position="last")


def per_zone_dag(toestand: pd.DataFrame) -> pd.DataFrame:
    """A2: % kwartieren buiten band per zone × dag (van de kwartieren mét data)."""
    d = toestand.assign(buiten=toestand["toestand"].isin([TE_KOUD, TE_WARM]),
                        met_data=toestand["toestand"] != GEEN_DATA)
    g = d.groupby(["zone", "dag"]).agg(buiten=("buiten", "sum"), met_data=("met_data", "sum"))
    g["% buiten"] = g["buiten"] / g["met_data"].where(g["met_data"] > 0) * 100
    return g["% buiten"].unstack("dag")


def datagaten(kwartier: pd.DataFrame, feestdagen: set) -> pd.DataFrame:
    """Periodes waarin ALLE gemeten reeksen tegelijk leeg zijn, en hoeveel kantoorkwartieren erin vallen."""
    gemeten = kwartier.groupby(["zone", "grootheid"])["waarde"].transform(lambda s: s.notna().any())
    k = kwartier[gemeten]
    leeg = k.groupby("kwartier")["waarde"].apply(lambda s: s.isna().all())
    if not leeg.any():
        return pd.DataFrame(columns=["van", "tot", "kwartieren", "kantoorkwartieren"])
    groep = (leeg != leeg.shift()).cumsum()
    rijen = []
    for _, blok in leeg[leeg].groupby(groep[leeg]):
        kw = blok.index.to_series()
        rijen.append({"van": kw.min(), "tot": kw.max() + KWARTIER, "kwartieren": len(kw),
                      "kantoorkwartieren": int(is_kantooruur(kw, feestdagen).sum())})
    return pd.DataFrame(rijen)


# ---------------------------------------------------------------------------
# Stap 8–10: klachten
# ---------------------------------------------------------------------------

def _tijd_naar_timedelta(x) -> pd.Timedelta | None:
    if x is None or (isinstance(x, float) and pd.isna(x)) or x is pd.NaT:
        return None
    if hasattr(x, "hour") and hasattr(x, "minute"):  # datetime.time of datetime
        return pd.Timedelta(hours=x.hour, minutes=x.minute)
    if isinstance(x, (int, float)) and 0 <= x < 1:  # Excel-fractie van een dag
        return pd.Timedelta(days=float(x)).round("1min")
    try:
        t = pd.to_datetime(str(x).strip(), format="mixed")
        return pd.Timedelta(hours=t.hour, minutes=t.minute)
    except (ValueError, TypeError):
        return None


def lees_klachtenbestand(bestand) -> pd.DataFrame:
    """Klachtenformulier inlezen: Excel (blad 'Klachten') of CSV (download uit Excel / OneDrive).

    CSV: scheidingsteken (, of ;) en tekenset (UTF-8 of Windows) worden herkend; de lege kolommen
    die Excel meeschrijft ('Unnamed: …') vallen weg. Kolommen Melder en Omschrijving gaan meteen weg."""
    data = bestand.read() if hasattr(bestand, "read") else Path(bestand).read_bytes()
    if data[:2] == b"PK":  # .xlsx is een zip-bestand
        k = pd.read_excel(io.BytesIO(data), sheet_name="Klachten")
    else:
        for tekenset in ("utf-8-sig", "cp1252"):
            try:
                tekst = data.decode(tekenset)
                break
            except UnicodeDecodeError:
                continue
        eerste = tekst.splitlines()[0] if tekst else ""
        sep = csv.Sniffer().sniff(eerste, delimiters=",;\t").delimiter if eerste else ","
        k = pd.read_csv(io.StringIO(tekst), sep=sep, dtype=str, keep_default_na=True,
                        usecols=lambda c: not str(c).startswith("Unnamed"))
        k = k.apply(lambda s: s.str.strip())
    return k.drop(columns=[c for c in PRIVACY_KOLOMMEN if c in k.columns])  # privacy: meteen weg


DATUM_DMJ = re.compile(r"^\s*(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})")


def lees_datums(reeks: pd.Series) -> tuple[pd.Series, str]:
    """Datums lezen en de volgorde (dag/maand of maand/dag) per bestand bepalen.

    Excel-cellen met een echte datum zijn eenduidig. Tekst zoals '11/9/2026' niet:
    - een tweede getal > 12 ergens in het bestand ('10/26/2026') → maand/dag (Amerikaans, bv. Excel Online);
    - een eerste getal > 12 ('26/10/2026') → dag/maand (Belgisch);
    - geen van beide → dag/maand aangenomen, met een waarschuwing.
    Teruggave: (datums, uitleg)."""
    tekst = reeks.dropna().astype(str)
    delen = tekst.str.extract(DATUM_DMJ).dropna().astype(int)
    if delen.empty:
        uitleg, maand_eerst = "", False
    elif (delen[1] > 12).any():
        uitleg, maand_eerst = "Datums gelezen als maand/dag/jaar (Amerikaans formaat herkend, bv. 10/26/2026).", True
    elif (delen[0] > 12).any():
        uitleg, maand_eerst = "Datums gelezen als dag/maand/jaar.", False
    else:
        uitleg, maand_eerst = ("⚠️ Datumvolgorde niet eenduidig (alle getallen ≤ 12): dag/maand/jaar aangenomen. "
                               "Controleer de datums of gebruik het formaat jjjj-mm-dd."), False

    def een(x):
        if pd.isna(x) or str(x).strip() == "":
            return pd.NaT
        if hasattr(x, "year"):  # al een datum (Excel)
            return pd.Timestamp(x)
        s = str(x).strip()
        m = DATUM_DMJ.match(s)
        if m:
            a, b, j = (int(g) for g in m.groups())
            d, mnd = (b, a) if maand_eerst else (a, b)
            try:
                return pd.Timestamp(year=j, month=mnd, day=d)
            except ValueError:
                return pd.NaT
        return pd.to_datetime(s, errors="coerce")  # bv. 2026-11-09

    return pd.to_datetime(reeks.map(een), errors="coerce").dt.normalize(), uitleg


def stap8_klachten(bestand, zones: pd.DataFrame) -> tuple[pd.DataFrame, StapInfo]:
    """Klachtenformulier (Excel of CSV) inlezen en controleren."""
    k = lees_klachtenbestand(bestand)
    rijen_in = len(k)
    weg: dict[str, int] = {}

    leeg = k[["Datum", "Zone", "Soort klacht"]].isna().all(axis=1)
    weg["lege rij"] = int(leeg.sum())
    k = k[~leeg].copy()

    k["datum"], datum_uitleg = lees_datums(k["Datum"])
    ongeldig = k["datum"].isna()
    weg["geen geldige datum"] = int(ongeldig.sum())
    k = k[~ongeldig].copy()

    bekend = set(zones["formulier_zone"])
    onbekend = ~k["Zone"].isin(bekend)
    weg["lege of onbekende zone"] = int(onbekend.sum())
    k = k[~onbekend].copy()

    k["uur"] = k["Tijdstip"].map(_tijd_naar_timedelta)
    k["zone"] = k["Zone"].map(dict(zip(zones["formulier_zone"], zones["zone"])))
    k = k.reset_index(drop=True)
    k.insert(0, "klacht_nr", range(1, len(k) + 1))
    info = StapInfo("8", "Klachten inlezen + controleren", rijen_in, len(k), weg,
                    uitleg="Kolommen Melder en Omschrijving worden meteen verwijderd (privacy). "
                           f"{int(k['uur'].isna().sum())} klacht(en) zonder geldig tijdstip → "
                           "hele werkdag (8–17 u) bekijken. " + datum_uitleg)
    return k, info


def klachten_zonder_datum(bestand, zones: pd.DataFrame) -> pd.DataFrame:
    """Klachten die stap 8 weglaat omdat de datum ontbreekt, maar die wel een zone of soort hebben.
    Ze worden niet beoordeeld (geen moment om te koppelen), maar de app toont ze apart als
    'algemene klacht', zodat ze niet onzichtbaar worden."""
    k = lees_klachtenbestand(bestand)
    k = k[~k[["Datum", "Zone", "Soort klacht"]].isna().all(axis=1)]
    zonder = k[lees_datums(k["Datum"])[0].isna()]
    kolommen = [c for c in ("Zone", "Discipline", "Soort klacht", "Ernst", "Zelf aangepast") if c in zonder]
    return zonder[kolommen].reset_index(drop=True)


def zelf_gemeten_vergelijken(beoordeeld: pd.DataFrame) -> pd.DataFrame:
    """Zelf gemeten temperatuur (formulier) naast het GBS zetten.

    'verschil met GBS' = hoeveel °C de eigen meting buiten het GBS-bereik (temp min–max) ligt.
    Groter dan GEMETEN_DREMPEL → markeren. De beoordeling blijft op het GBS gebaseerd."""
    kol = next((c for c in beoordeeld.columns if str(c).startswith("Gemeten temp")), None)
    gemeten = (pd.to_numeric(beoordeeld[kol].astype(str).str.replace(",", ".", regex=False),
                             errors="coerce") if kol
               else pd.Series(float("nan"), index=beoordeeld.index))  # "16,0" (decimale komma) → 16.0
    onder = (beoordeeld["temp min"] - gemeten).clip(lower=0)
    boven = (gemeten - beoordeeld["temp max"]).clip(lower=0)
    verschil = onder.fillna(0) + boven.fillna(0)
    verschil = verschil.where(gemeten.notna() & beoordeeld["temp min"].notna())
    return beoordeeld.assign(**{"zelf gemeten": gemeten, "verschil met GBS": verschil,
                                "afwijkende eigen meting": verschil > GEMETEN_DREMPEL})


def klachtvenster(datum: pd.Timestamp, uur: pd.Timedelta | None) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Eerste en laatste kwartier (begin-label) dat meetelt voor een klacht."""
    if uur is None or pd.isna(uur):
        dag = pd.Timestamp(datum).tz_localize(TZ)
        return dag + pd.Timedelta(hours=KANTOOR_START_UUR), dag + pd.Timedelta(hours=KANTOOR_EINDE_UUR) - KWARTIER
    moment = (pd.Timestamp(datum) + uur).tz_localize(TZ, ambiguous=True, nonexistent="shift_forward")
    kw = moment.tz_convert("UTC").floor("15min").tz_convert(TZ)
    return kw - VENSTER, kw + VENSTER


def _oorzaak_tekst(centraal: pd.DataFrame, zone_rijen: pd.DataFrame, van, tot, soort: str) -> str:
    """Korte 'grondige reden' voor een gegronde klacht."""
    redenen = []
    if soort == "Te koud":
        c = centraal.loc[van - pd.Timedelta(hours=2): tot]
        tekort = (c["kringsetpoint"] - c["aanvoer"]) > OORZAAK_DREMPEL
        if tekort.any():
            r = c[tekort]
            redenen.append(f"warmteproductie leverde niet: aanvoer gem. {r['aanvoer'].mean():.1f} °C "
                           f"vs kringsetpoint gem. {r['kringsetpoint'].mean():.1f} °C")
        sp = zone_rijen["sp_verwarmen"]
        if sp.notna().any() and (sp < zone_rijen["ondergrens"]).any():
            redenen.append(f"setpoint verwarmen ({sp.min():.1f} °C) lager dan de band → stand-by of verdraaid")
    elif soort == "Te warm":
        sp = zone_rijen["sp_koelen"]
        if sp.notna().any() and (sp > zone_rijen["bovengrens"]).any():
            redenen.append(f"setpoint koelen ({sp.max():.1f} °C) hoger dan de band → stand-by of verdraaid")
    return "; ".join(redenen) if redenen else "geen duidelijke oorzaak in aanvoer of setpoints"


def stap9_beoordelen(klachten: pd.DataFrame, toestand: pd.DataFrame, centraal: pd.DataFrame,
                     zones: pd.DataFrame, feestdagen: set) -> tuple[pd.DataFrame, StapInfo]:
    """Elke klacht beoordelen volgens de regels van het beslissingslogboek."""
    zones_met_meting = set(comfortzones(zones).dropna(subset=["gbs_device"])["zone"])
    t_idx = toestand.set_index(["zone", "kwartier"]).sort_index()
    rijen = []
    for _, k in klachten.iterrows():
        van, tot = klachtvenster(k["datum"], k["uur"])
        moment = van + VENSTER if k["uur"] is not None and not pd.isna(k["uur"]) else None
        r = {"klacht_nr": k["klacht_nr"], "van": van, "tot": tot,
             "buiten kantooruren": bool(moment is not None
                                        and not is_kantooruur(pd.Series([moment]), feestdagen).iloc[0]),
             "temp min": float("nan"), "temp max": float("nan"), "reden": "", "mogelijke oorzaak": ""}
        soort = k.get("Soort klacht")
        if soort not in ("Te koud", "Te warm"):
            r["beoordeling"], r["reden"] = NTB_THEMA, f"soort klacht '{soort}' is geen temperatuurklacht"
        elif k["zone"] not in zones_met_meting:
            r["beoordeling"], r["reden"] = NTB_METING, "geen ruimtetemperatuur gemeten in deze zone"
        else:
            try:
                venster = t_idx.loc[(k["zone"], slice(van, tot)), :]
            except KeyError:
                venster = t_idx.iloc[0:0]
            verwacht = int((tot - van) / KWARTIER) + 1
            richting = TE_KOUD if soort == "Te koud" else TE_WARM
            r["temp min"], r["temp max"] = venster["ruimtetemp"].min(), venster["ruimtetemp"].max()
            n_data = int(venster["ruimtetemp"].notna().sum())
            if (venster["toestand"] == richting).any():
                n = int((venster["toestand"] == richting).sum())
                r["beoordeling"] = GEGROND
                r["reden"] = f"{n} van {verwacht} kwartieren {richting}"
                r["mogelijke oorzaak"] = _oorzaak_tekst(centraal, venster.reset_index(), van, tot, soort)
            elif n_data < verwacht:
                r["beoordeling"] = NTB_DATA
                r["reden"] = f"{verwacht - n_data} van {verwacht} kwartieren zonder meting (datagat)"
            else:
                r["beoordeling"] = ONGEGROND
                andere = TE_WARM if richting == TE_KOUD else TE_KOUD
                if (venster["toestand"] == andere).any():
                    r["reden"] = f"temperatuur was {andere}, niet {richting}"
                else:
                    r["reden"] = f"alle {verwacht} kwartieren binnen de band"
        rijen.append(r)
    beoordeeld = klachten.merge(pd.DataFrame(rijen), on="klacht_nr", how="left")
    beoordeeld = zelf_gemeten_vergelijken(beoordeeld)
    telling = beoordeeld["beoordeling"].value_counts().to_dict()
    info = StapInfo("9", "Klacht ↔ meting (±30 min) beoordelen", len(klachten), len(beoordeeld),
                    soort="omvormen",
                    uitleg=" · ".join(f"{k}: {v}" for k, v in telling.items()) or "geen klachten")
    return beoordeeld, info


def stap10_oorzaak(centraal: pd.DataFrame, toestand: pd.DataFrame, zone: str,
                   van: pd.Timestamp, tot: pd.Timestamp) -> tuple[pd.DataFrame, list[str]]:
    """Aanvoer vs kringsetpoint + setpoints van de zone in een periode, met meldingen."""
    c = centraal.loc[van:tot]
    z = (toestand[(toestand["zone"] == zone)
                  & toestand["kwartier"].between(van, tot)]
         .set_index("kwartier")[["ruimtetemp", "sp_verwarmen", "sp_koelen", "ondergrens", "bovengrens"]])
    df = c.join(z, how="outer")
    meldingen = []
    tekort = (df["kringsetpoint"] - df["aanvoer"]) > OORZAAK_DREMPEL
    if tekort.any():
        groep = (tekort != tekort.shift()).cumsum()
        for _, blok in tekort[tekort].groupby(groep[tekort]):
            a, b = blok.index.min(), blok.index.max() + KWARTIER
            stuk = df.loc[blok.index]
            meldingen.append(
                f"{a:%d/%m %H:%M}–{b:%H:%M}: aanvoer gem. {stuk['aanvoer'].mean():.1f} °C, "
                f"> {OORZAAK_DREMPEL:g} °C onder het kringsetpoint (gem. {stuk['kringsetpoint'].mean():.1f} °C) "
                "→ warmteproductie leverde niet")
    return df, meldingen


def trechter(infos: list[StapInfo]) -> pd.DataFrame:
    """Rijen-trechter: per stap rijen in/uit, weg, % weg en de reden."""
    rijen = []
    for s in infos:
        reden = "; ".join(f"{r} ({n:,})".replace(",", ".") for r, n in s.weg.items() if n) or (
            "samenvoegen/omzetten, geen rijen weg" if s.soort == "omvormen" else "–")
        rijen.append({
            "Stap": f"{s.nr} {s.naam}", "Rijen in": s.rijen_in, "Rijen uit": s.rijen_uit,
            "Weg": s.totaal_weg if s.soort == "filter" else None,
            "% weg": (s.totaal_weg / s.rijen_in * 100) if s.soort == "filter" and s.rijen_in else None,
            "Waarom": reden,
            "Klopt (in = uit + weg)": {True: "✅", False: "❌", None: "–"}[s.klopt],
        })
    return pd.DataFrame(rijen)
