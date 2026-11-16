"""Tests op de verzonnen voorbeelddata. Draaien met:  python -m pytest"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

MAP = Path(__file__).parents[1]
sys.path.insert(0, str(MAP))
import pipeline as p  # noqa: E402

GBS = MAP / "data" / "voorbeeld" / "gbs_voorbeeld.csv.gz"
KLACHTEN = MAP / "data" / "voorbeeld" / "voorbeeld_klachten.xlsx"


@pytest.fixture(scope="module")
def run():
    zones, fd = p.lees_zones(), p.lees_feestdagen()
    infos = []
    df, i = p.stap1_inlezen(GBS); infos.append(i)
    for stap in (p.stap2_nodige_punten,):
        df, i = stap(df); infos.append(i)
    df, i = p.stap3_zone_koppelen(df, zones); infos.append(i)
    fouten = p.voelerfouten(df)
    df, i = p.stap3b_voelerfout(df); infos.append(i)
    df, i = p.stap4_tijdzone(df); infos.append(i)
    kw, i = p.stap5_per_kwartier(df, zones); infos.append(i)
    centraal = p.centraal_breed(kw)
    t6, i = p.stap6_kantooruren(p.breed_per_zone(kw), zones, fd); infos.append(i)
    t7, i = p.stap7_toestand(t6); infos.append(i)
    k, i8 = p.stap8_klachten(KLACHTEN, zones)
    b, i9 = p.stap9_beoordelen(k, t7, centraal, zones, fd)
    return {"infos": infos + [i8, i9], "fouten": fouten, "t7": t7, "kw": kw,
            "klachten": k, "beoordeeld": b, "zones": zones, "fd": fd, "centraal": centraal}


def test_trechter_klopt(run):
    for info in run["infos"]:
        assert info.klopt in (True, None), f"stap {info.nr}: in ≠ uit + weg"


def test_voelerfout_3_metingen(run):
    assert len(run["fouten"]) == 3
    assert (run["fouten"]["waarde"] == 0.0).all()


def test_buitentemp_onder_10_blijft(run):
    buiten = run["centraal"]["buitentemp"]
    assert (buiten < 10).any(), "buitentemp < 10 °C mag niet weggefilterd worden"


def test_winteruur_geen_dubbele_kwartieren(run):
    kw = run["kw"]
    assert not kw.duplicated(["kwartier", "zone", "grootheid"]).any()
    # zondag 25/10 heeft 25 uur = 100 kwartieren
    dag = kw[(kw["zone"] == "1.2") & (kw["grootheid"] == "ruimtetemp")]
    assert (dag["kwartier"].dt.date == date(2026, 10, 25)).sum() == 100


def test_kantooruren(run):
    t = run["t7"]
    kantoor = t[t["kantooruur"]]
    assert kantoor["kwartier"].dt.weekday.max() < 5
    assert kantoor["kwartier"].dt.hour.between(8, 16).all()
    # 36 kwartieren per werkdag per zone
    assert kantoor.groupby(["zone", "dag"]).size().eq(36).all()


def test_maximaal_1_kwartier_doortrekken(run):
    kw = run["kw"]
    reeks = kw[(kw["zone"] == "1.5") & (kw["grootheid"] == "ruimtetemp")].set_index("kwartier")
    gat = reeks.loc["2026-10-28 10:00":"2026-10-28 12:45"]
    assert gat["doorgetrokken"].sum() == 1          # 10:00 = vorige waarde doorgetrokken
    assert gat["waarde"].isna().sum() == len(gat) - 1  # de rest blijft leeg


def test_klachten_controle(run):
    i8 = run["infos"][-2]
    assert i8.weg["geen geldige datum"] == 1
    assert i8.weg["lege of onbekende zone"] == 1
    assert "Melder (initialen)" not in run["klachten"].columns
    assert "Omschrijving" not in run["klachten"].columns


@pytest.mark.parametrize("nr, verwacht", [
    (1, p.GEGROND),      # 26/10 08:30 1.2 te koud, warmteproductie leverde niet
    (2, p.ONGEGROND),    # binnen de band
    (3, p.NTB_METING),   # magazijn
    (4, p.NTB_DATA),     # datagat
    (5, p.NTB_THEMA),    # akoestiek
    (6, p.GEGROND),      # zonder tijdstip → hele werkdag, te warm
    (7, p.ONGEGROND),    # te koud geklaagd, maar te warm
    (8, p.NTB_METING),   # zone 0.1
])
def test_beoordeling(run, nr, verwacht):
    b = run["beoordeeld"].set_index("klacht_nr")
    assert b.loc[nr, "beoordeling"] == verwacht


def test_oorzaak_26_10(run):
    b = run["beoordeeld"].set_index("klacht_nr")
    assert "warmteproductie leverde niet" in b.loc[1, "mogelijke oorzaak"]


def test_ruwe_export_met_tekstwaarden():
    """Een ruwe export bevat ook binaire punten ('active'/'inactive') en een kolom 'naam'.
    Dan leest pandas 'waarde' als tekst in; stap 2 moet dat opvangen en tellen."""
    ruw = pd.DataFrame({
        "ts": ["2026-10-26T07:30:00+00:00"] * 4,
        "device": [8, 8, 8, 500],
        "type": ["analog-value", "analog-value", "binary-value", "analog-input"],
        "instance": [3, 1, 5, 12],
        "naam": ["KP 1.2 AV3", "KP 1.2 AV1", "pomp", "aanvoer"],
        "waarde": ["19.2", "", "active", "19.5"],
    })
    uit, info = p.stap2_nodige_punten(ruw)
    assert info.klopt
    assert info.weg["ander BACnet-punt (niet nodig)"] == 1          # binary-value
    assert info.weg["waarde is geen getal (leeg of tekst)"] == 1    # lege AV1
    assert uit["waarde"].dtype.kind == "f"
    p.stap3b_voelerfout(p.stap3_zone_koppelen(uit, p.lees_zones())[0])  # mag niet crashen


def test_zelf_gemeten_vergelijken():
    """Eigen meting > 2 °C buiten het GBS-bereik wordt gemarkeerd; de beoordeling verandert niet."""
    df = pd.DataFrame({"Gemeten temp (°C)": [16.0, 21.0, None, "?"],
                       "temp min": [21.4, 20.5, 21.0, 21.0], "temp max": [21.6, 21.5, 22.0, 22.0],
                       "beoordeling": [p.ONGEGROND] * 4})
    uit = p.zelf_gemeten_vergelijken(df)
    assert uit["verschil met GBS"].iloc[0] == pytest.approx(5.4)
    assert uit["verschil met GBS"].iloc[1] == 0               # binnen het GBS-bereik
    assert uit["afwijkende eigen meting"].tolist() == [True, False, False, False]
    assert (uit["beoordeling"] == p.ONGEGROND).all()


def test_klachten_zonder_datum(run):
    """De klacht zonder datum valt weg in stap 8, maar blijft zichtbaar als algemene klacht."""
    algemeen = p.klachten_zonder_datum(KLACHTEN, run["zones"])
    assert len(algemeen) == run["infos"][-2].weg["geen geldige datum"] == 1
    assert "Melder (initialen)" not in algemeen.columns and "Omschrijving" not in algemeen.columns


@pytest.mark.parametrize("datums, verwacht, woord", [
    (["10/26/2026", "11/9/2026"], ["2026-10-26", "2026-11-09"], "maand/dag"),   # Excel Online (VS)
    (["26/10/2026", "9/11/2026"], ["2026-10-26", "2026-11-09"], "dag/maand"),   # Belgisch
    (["2026-10-26", "2026-11-09"], ["2026-10-26", "2026-11-09"], ""),           # ISO: eenduidig
    (["9/11/2026"], ["2026-11-09"], "⚠️"),                                     # niet eenduidig → waarschuwing
])
def test_datumvolgorde(datums, verwacht, woord):
    """11/9/2026 mag nooit stil als 11 september gelezen worden als het bestand maand/dag gebruikt."""
    uit, uitleg = p.lees_datums(pd.Series(datums + [None]))
    assert uit.dt.strftime("%Y-%m-%d").tolist()[:-1] == verwacht
    assert pd.isna(uit.iloc[-1])
    assert woord in uitleg


def test_klachten_csv_zoals_excel_online(tmp_path):
    """CSV met komma's, Windows-tekenset (°), lege Excel-kolommen en VS-datums."""
    kop = ("Datum,Tijdstip,Duur,Zone,Discipline,Soort klacht,Ernst,Raam/deur open,Zelf aangepast,"
           "Gemeten temp (°C),Omschrijving,Melder (initialen),Beoordeling,Oorzaak,Opmerking technische dienst")
    rijen = [kop + ",,,",
             '10/26/2026,8:00,30 min - 2 uur,1.2 Calculatie (Kantoor 4),CV (verwarming),Te koud,2 - Storend,'
             'Nee,Niets,"18,5",verzonnen,XX,,,,,,',
             ",,,1.7 Refter,CV (verwarming),Te koud,2 - Storend,Nee,Andere,,verzonnen,XX,,,,,,",
             ",,,,,,,,,,,,,,,,,"]
    f = tmp_path / "klachten.csv"
    f.write_bytes("\r\n".join(rijen).encode("cp1252"))
    zones = p.lees_zones()
    k, info = p.stap8_klachten(f, zones)
    assert info.klopt and len(k) == 1
    assert k.loc[0, "datum"] == pd.Timestamp("2026-10-26")
    assert k.loc[0, "uur"] == pd.Timedelta(hours=8)
    assert "Melder (initialen)" not in k.columns and not any(c.startswith("Unnamed") for c in k.columns)
    assert len(p.klachten_zonder_datum(f, zones)) == 1
    gemeten = p.zelf_gemeten_vergelijken(k.assign(**{"temp min": 19.0, "temp max": 19.5}))
    assert gemeten.loc[0, "zelf gemeten"] == 18.5          # decimale komma gelezen


def test_klachten_csv_puntkomma_utf8(tmp_path):
    f = tmp_path / "klachten.csv"
    f.write_text("Datum;Tijdstip;Zone;Soort klacht\n2026-11-11;11:49;1.3 Elektro & regeling (Kantoor 5);Te koud\n",
                 encoding="utf-8-sig")
    k, _ = p.stap8_klachten(f, p.lees_zones())
    assert len(k) == 1 and k.loc[0, "zone"] == "1.3"


def test_venster_5_kwartieren():
    van, tot = p.klachtvenster(pd.Timestamp("2026-10-26"), pd.Timedelta(hours=8, minutes=30))
    assert (van.strftime("%H:%M"), tot.strftime("%H:%M")) == ("08:00", "09:00")
    van, tot = p.klachtvenster(pd.Timestamp("2026-10-26"), pd.Timedelta(hours=8, minutes=37))
    assert (van.strftime("%H:%M"), tot.strftime("%H:%M")) == ("08:00", "09:00")


def test_buiten_kantooruren_vlag(run):
    b = run["beoordeeld"].set_index("klacht_nr")
    assert bool(b.loc[9, "buiten kantooruren"]) is True
    assert bool(b.loc[1, "buiten kantooruren"]) is False


def test_noemer_zonder_geen_data(run):
    a1 = p.per_zone(run["t7"][run["t7"]["kantooruur"]], run["zones"])
    rij = a1.loc["1.5 Directie 1"]
    # % te koud + % te warm = % buiten (zelfde noemer: kwartieren mét data)
    assert rij["% te koud"] + rij["% te warm"] == pytest.approx(rij["% buiten band"])
    assert a1.loc["0.1 Nazorg (Kantoor 1)", "% geen data"] == 100
