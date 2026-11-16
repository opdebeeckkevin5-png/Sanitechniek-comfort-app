"""Comfortapp kantoor – Streamlit-scherm. Alle rekenwerk zit in pipeline.py."""

import inspect
import io
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import pipeline as p

st.set_page_config(page_title="Comfort kantoor", page_icon="🌡️", layout="wide")

VOORBEELD_GBS = Path(__file__).parent / "data" / "voorbeeld" / "gbs_voorbeeld.csv.gz"
VOORBEELD_KLACHTEN = Path(__file__).parent / "data" / "voorbeeld" / "voorbeeld_klachten.xlsx"

KLEUR = {p.BINNEN: "#2b8a3e", p.TE_KOUD: "#1971c2", p.TE_WARM: "#e8590c", p.GEEN_DATA: "#adb5bd"}
KLEUR_BEOORDELING = {p.GEGROND: "#ffc9c9", p.ONGEGROND: "#d3f9d8"}


# ---------------------------------------------------------------------------
# Pijplijn draaien (gecachet: enkel opnieuw als er een ander bestand komt)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="GBS-data verwerken …")
def gbs_stappen(inhoud: bytes) -> dict:
    zones, feestdagen = p.lees_zones(), p.lees_feestdagen()
    df, i1 = p.stap1_inlezen(io.BytesIO(inhoud))
    voorbeelden = {"1": df.head()}
    df, i2 = p.stap2_nodige_punten(df); voorbeelden["2"] = df.head()
    df, i3 = p.stap3_zone_koppelen(df, zones); voorbeelden["3"] = df.head()
    fouten = p.voelerfouten(df)
    df, i3b = p.stap3b_voelerfout(df); voorbeelden["3b"] = fouten
    df, i4 = p.stap4_tijdzone(df); voorbeelden["4"] = df.head()
    kwartier, i5 = p.stap5_per_kwartier(df, zones)
    voorbeelden["5"] = kwartier[kwartier["waarde"].notna()].head(8)
    breed = p.breed_per_zone(kwartier)
    df6, i6 = p.stap6_kantooruren(breed, zones, feestdagen)
    voorbeelden["6"] = df6[df6["kantooruur"]].head()
    return {"df6": df6, "centraal": p.centraal_breed(kwartier), "infos": [i1, i2, i3, i3b, i4, i5, i6],
            "voorbeelden": voorbeelden, "datagaten": p.datagaten(kwartier, feestdagen)}


@st.cache_data(show_spinner="Klachten inlezen …")
def klachten_inlezen(inhoud: bytes):
    zones = p.lees_zones()
    klachten, info = p.stap8_klachten(io.BytesIO(inhoud), zones)
    return klachten, info, p.klachten_zonder_datum(io.BytesIO(inhoud), zones)


# ---------------------------------------------------------------------------
# Zijbalk
# ---------------------------------------------------------------------------

zones = p.lees_zones()
feestdagen = p.lees_feestdagen()
naam = dict(zip(zones["zone"], zones["naam"]))

with st.sidebar:
    st.header("Data")
    up_gbs = st.file_uploader("📤 GBS-data (.csv.gz)", type=["gz"])
    up_klachten = st.file_uploader("📤 Klachten (.xlsx)", type=["xlsx"])
    voorbeeld = False
    if up_gbs is None:
        voorbeeld = st.toggle("Verzonnen voorbeelddata gebruiken", value=True,
                              help="Testdata uit data/voorbeeld (gemaakt met maak_testdata.py).")

if up_gbs is not None:
    gbs_bytes = up_gbs.getvalue()
elif voorbeeld and VOORBEELD_GBS.exists():
    gbs_bytes = VOORBEELD_GBS.read_bytes()
else:
    st.title("Binnenklimaat kantoor")
    st.info("Laad links een GBS-export (.csv.gz) op, of zet de voorbeelddata aan.")
    st.stop()

if up_klachten is not None:
    klacht_bytes = up_klachten.getvalue()
elif voorbeeld and VOORBEELD_KLACHTEN.exists():
    klacht_bytes = VOORBEELD_KLACHTEN.read_bytes()
else:
    klacht_bytes = None

try:
    gbs = gbs_stappen(gbs_bytes)
except Exception as fout:  # noqa: BLE001 – toon de fout leesbaar in de app
    st.error(f"De GBS-export kon niet verwerkt worden: {fout}")
    st.stop()

df6 = gbs["df6"]
eerste, laatste = df6["kwartier"].min(), df6["kwartier"].max()

with st.sidebar:
    st.header("Filters")
    comfort_namen = [naam[z] for z in p.comfortzones(zones)["zone"]]
    gekozen = st.multiselect("Zone(s)", comfort_namen, default=comfort_namen)
    gekozen_zones = [z for z, n in naam.items() if n in gekozen]
    periode = st.date_input("Periode", value=(eerste.date(), laatste.date()),
                            min_value=eerste.date(), max_value=laatste.date(), format="DD/MM/YYYY")
    van_dag, tot_dag = (periode if isinstance(periode, tuple) and len(periode) == 2
                        else (eerste.date(), laatste.date()))
    ook_nacht = st.checkbox("Ook nacht/weekend meetellen", value=False,
                            help="Standaard tellen enkel de kantooruren: ma–vr 8–17 u, zonder feestdagen.")

    st.header("Comfortband")
    st.caption("Typebestek 105, tabel B1.2.-1 (NBN EN ISO 7730 cat. B)")
    c1, c2 = st.columns(2)
    w_min = c1.number_input("Winter min", value=p.STANDAARD_BAND["winter"][0], step=0.5, help="okt–apr")
    w_max = c2.number_input("Winter max", value=p.STANDAARD_BAND["winter"][1], step=0.5)
    z_min = c1.number_input("Zomer min", value=p.STANDAARD_BAND["zomer"][0], step=0.5, help="mei–sep")
    z_max = c2.number_input("Zomer max", value=p.STANDAARD_BAND["zomer"][1], step=0.5)
    band = {"winter": (w_min, w_max), "zomer": (z_min, z_max)}
    if w_min >= w_max or z_min >= z_max:
        st.error("De ondergrens moet lager zijn dan de bovengrens.")
        st.stop()

# Stap 7 en 9 hangen af van de band → telkens opnieuw (snel)
df7, i7 = p.stap7_toestand(df6, band)
if klacht_bytes is not None:
    klachten, i8, algemeen = klachten_inlezen(klacht_bytes)
    beoordeeld, i9 = p.stap9_beoordelen(klachten, df7, gbs["centraal"], zones, feestdagen)
else:
    klachten = beoordeeld = algemeen = None
    i8 = i9 = None

# Filters toepassen
in_periode = df7["dag"].between(van_dag, tot_dag)
sel = df7[in_periode & df7["zone"].isin(gekozen_zones)]
if not ook_nacht:
    sel = sel[sel["kantooruur"]]

if beoordeeld is not None:
    kl = beoordeeld[beoordeeld["datum"].dt.date.between(van_dag, tot_dag)]
    if len(gekozen_zones) < len(comfort_namen):
        kl = kl[kl["zone"].isin(gekozen_zones)]
else:
    kl = None

# ---------------------------------------------------------------------------
# Kop + KPI's
# ---------------------------------------------------------------------------

st.title("Binnenklimaat kantoor – zit het binnen de comfortgrenzen?")
bron = "verzonnen voorbeelddata" if up_gbs is None else "GBS (Priva via BACnet)"
st.caption(f"Periode: {van_dag:%d/%m/%Y} – {tot_dag:%d/%m/%Y} · bron: {bron} · "
           f"laatste meting: {laatste:%d/%m %H:%M} · "
           + ("kantooruren ma–vr 8–17 u, zonder feestdagen" if not ook_nacht else "alle uren"))

met_data = sel[sel["toestand"] != p.GEEN_DATA]
pct_binnen = (met_data["toestand"] == p.BINNEN).mean() * 100 if len(met_data) else float("nan")
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("% kwartieren binnen band", "–" if pd.isna(pct_binnen) else f"{pct_binnen:.0f} %",
          help=f"Van {len(met_data):,} kwartieren mét meting. Kwartieren zonder data tellen niet mee "
               f"({(sel['toestand'] == p.GEEN_DATA).sum():,} kwartieren).".replace(",", "."))
if kl is not None:
    k2.metric("Klachten", len(kl))
    k3.metric("Gegrond", int((kl["beoordeling"] == p.GEGROND).sum()))
    k4.metric("Ongegrond", int((kl["beoordeling"] == p.ONGEGROND).sum()))
    k5.metric("Niet te beoordelen", int(kl["beoordeling"].str.startswith("niet").sum()))
else:
    k2.metric("Klachten", "–", help="Laad een klachtenformulier op.")

# Meldingen: bekende beperkingen
gaten = gbs["datagaten"]
gaten_kantoor = gaten[gaten["kantoorkwartieren"] > 0]
with st.expander("⚠️ Bekende beperkingen van deze data", expanded=False):
    if len(gaten_kantoor):
        st.markdown("**Datagaten in de kantooruren** (alle punten tegelijk weg):\n" + "\n".join(
            f"- {r.van:%a %d/%m %H:%M} → {r.tot:%a %d/%m %H:%M} "
            f"({r.kantoorkwartieren} kantoorkwartieren)" for r in gaten_kantoor.itertuples()))
    else:
        st.markdown("Geen datagaten in de kantooruren.")
    st.markdown(
        "- **Zone 0.1 Nazorg**: geen data (regelaar wordt nog niet uitgelezen via BACnet) → "
        "*geen data*, niet *in orde*.\n"
        "- **Zone 1.7 Refter**: andere voeler (VAV-voeler van de Priva) dan de andere zones.\n"
        "- Het GBS meet **luchttemperatuur**; de norm spreekt over **operatieve temperatuur** "
        "(lucht + straling). Tocht en straling zitten niet in deze data.\n"
        "- Klachten over ventilatie, akoestiek, geur, … kan deze app **niet** beoordelen.")

tab_comfort, tab_klachten, tab_oorzaak, tab_stappen = st.tabs(
    ["Comfort", "Klachten", "Oorzaak", "Stap voor stap"])

# ---------------------------------------------------------------------------
# Tab Comfort
# ---------------------------------------------------------------------------

with tab_comfort:
    st.subheader("A1 · Per zone, gesorteerd op % buiten band (slechtste bovenaan)")
    tabel = p.per_zone(sel, zones)
    st.dataframe(
        tabel, width="stretch",
        column_config={k: st.column_config.NumberColumn(format="%.1f %%")
                       for k in ["% buiten band", "% te koud", "% te warm", "% geen data"]})
    st.caption("% buiten / te koud / te warm = van de kwartieren mét meting. "
               "% geen data = van alle kwartieren in de selectie.")

    st.subheader("A2 · Wanneer buiten de band? (zone × dag)")
    hm = p.per_zone_dag(sel)
    if hm.size:
        hm.index = [naam.get(z, z) for z in hm.index]
        fig = go.Figure(go.Heatmap(
            z=hm.to_numpy(), x=[f"{d:%a %d/%m}" for d in hm.columns], y=hm.index,
            colorscale=[[0, "#d3f9d8"], [0.15, "#ffe8cc"], [0.5, "#ff8787"], [1, "#c92a2a"]],
            zmin=0, zmax=100, colorbar={"title": "% buiten"}, xgap=2, ygap=2,
            hovertemplate="%{y}<br>%{x}<br>%{z:.0f} % buiten band<extra></extra>"))
        fig.update_layout(height=60 + 28 * len(hm), plot_bgcolor="#e9ecef",
                          margin={"l": 10, "r": 10, "t": 10, "b": 10})
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, width="stretch")
        st.caption("Groen = altijd binnen · oranje = deels buiten · rood = vaak buiten · grijs = geen data.")

    st.subheader("A3 · Te koud of te warm?")
    a3 = tabel[["% te koud", "% te warm"]].dropna()
    a3 = a3.assign(**{"% binnen band": 100 - a3.sum(axis=1)}).reset_index().melt(
        id_vars="Zone", var_name="Toestand", value_name="%")
    a3["Toestand"] = a3["Toestand"].str.removeprefix("% ")
    fig = px.bar(a3, x="Zone", y="%", color="Toestand", color_discrete_map=KLEUR,
                 category_orders={"Toestand": [p.TE_KOUD, p.BINNEN, p.TE_WARM]})
    fig.update_layout(height=400, margin={"l": 10, "r": 10, "t": 10, "b": 10}, yaxis_range=[0, 100])
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------------------
# Tab Klachten
# ---------------------------------------------------------------------------

def grafiek_temp(zone: str, van: pd.Timestamp, tot: pd.Timestamp, venster=None, moment=None) -> go.Figure:
    z = df7[(df7["zone"] == zone) & df7["kwartier"].between(van, tot)]
    fig = go.Figure()
    fig.add_scatter(x=z["kwartier"], y=z["bovengrens"], line={"color": "#8ce99a", "dash": "dash"},
                    name="band max")
    fig.add_scatter(x=z["kwartier"], y=z["ondergrens"], line={"color": "#8ce99a", "dash": "dash"},
                    fill="tonexty", fillcolor="rgba(140,233,154,0.15)", name="band min")
    fig.add_scatter(x=z["kwartier"], y=z["sp_verwarmen"], line={"color": "#e03131", "dash": "dot", "shape": "hv"},
                    name="SP verwarmen")
    fig.add_scatter(x=z["kwartier"], y=z["sp_koelen"], line={"color": "#1c7ed6", "dash": "dot", "shape": "hv"},
                    name="SP koelen")
    fig.add_scatter(x=z["kwartier"], y=z["ruimtetemp"], line={"color": "#1971c2", "width": 3},
                    mode="lines+markers", name="ruimtetemp")
    if venster is not None:
        fig.add_vrect(x0=venster[0], x1=venster[1] + p.KWARTIER, fillcolor="#e03131", opacity=0.08,
                      line_width=0, annotation_text="venster", annotation_position="top left")
    if moment is not None:
        fig.add_vline(x=moment, line={"color": "#e03131", "dash": "dash"})
    fig.update_layout(height=380, margin={"l": 10, "r": 10, "t": 30, "b": 10},
                      yaxis_title="°C", legend={"orientation": "h", "y": -0.15})
    return fig


with tab_klachten:
    if kl is None:
        st.info("Laad een klachtenformulier (.xlsx) op in de zijbalk.")
    elif kl.empty:
        st.info("Geen klachten in deze periode / zone(s).")
    else:
        st.subheader("B1 · Elke klacht naast de meting (±30 min)")
        toon = pd.DataFrame({
            "Nr": kl["klacht_nr"],
            "Datum": kl["datum"].dt.strftime("%a %d/%m"),
            "Uur": kl["uur"].map(lambda u: "hele dag" if pd.isna(u)
                                 else f"{int(u.total_seconds() // 3600):02d}:{int(u.total_seconds() % 3600 // 60):02d}"),
            "Zone": kl["Zone"], "Soort": kl["Soort klacht"], "Ernst": kl.get("Ernst"),
            "Temp GBS min–max": [("–" if pd.isna(a) else f"{a:.1f}–{b:.1f}".replace(".", ","))
                                 for a, b in zip(kl["temp min"], kl["temp max"])],
            "Zelf gemeten": [("–" if pd.isna(g) else f"{g:.1f}".replace(".", ",")
                              + (" ⚠️" if afw else "")) for g, afw in
                             zip(kl["zelf gemeten"], kl["afwijkende eigen meting"])],
            "Beoordeling": kl["beoordeling"], "Waarom": kl["reden"],
            "Mogelijke oorzaak": kl["mogelijke oorzaak"],
            "Buiten kantooruren": kl["buiten kantooruren"],
            "Beoordeling TD": kl.get("Beoordeling"),
        })
        stijl = toon.style.apply(
            lambda kol: [f"background-color: {KLEUR_BEOORDELING.get(v, '#f1f3f5')}" for v in kol],
            subset=["Beoordeling"])
        keuze = st.dataframe(stijl, width="stretch", hide_index=True,
                             on_select="rerun", selection_mode="single-row", key="klachtkeuze")
        st.caption("Klik een rij aan voor het detail (B3). 'Beoordeling TD' = wat de technische dienst "
                   "zelf invulde op het formulier, ter vergelijking. 'Zelf gemeten' = temperatuur die de "
                   "collega op het formulier invulde; de beoordeling gebruikt enkel het GBS.")
        afwijkend = kl[kl["afwijkende eigen meting"]]
        for _, r in afwijkend.iterrows():
            st.warning(
                f"Klacht {r['klacht_nr']} ({r['Zone']}, {r['datum']:%d/%m}): zelf gemeten "
                f"{r['zelf gemeten']:.1f} °C, het GBS gaf {r['temp min']:.1f}–"
                f"{r['temp max']:.1f} °C (verschil {r['verschil met GBS']:.1f} °C > "
                f"{p.GEMETEN_DREMPEL:g} °C). Mogelijke oorzaken: ander meettoestel, meting op een andere "
                "plek (raam, buitenmuur), of de voeler van de regelaar hangt op een ongunstige plek. "
                "Even samen nameten.")

        rijen = keuze.selection.rows if keuze and keuze.selection else []
        gekozen_klacht = kl.iloc[rijen[0]] if rijen else kl.iloc[0]
        st.session_state["klacht"] = gekozen_klacht

        st.subheader(f"B3 · Temperatuurverloop rond klacht {gekozen_klacht['klacht_nr']} – "
                     f"{gekozen_klacht['Zone']}, {gekozen_klacht['datum']:%a %d/%m}")
        if gekozen_klacht["zone"] in set(df7["zone"]):
            van, tot = gekozen_klacht["van"], gekozen_klacht["tot"]
            heeft_uur = not pd.isna(gekozen_klacht["uur"])
            moment = van + p.VENSTER if heeft_uur else None
            st.plotly_chart(grafiek_temp(gekozen_klacht["zone"], van - pd.Timedelta(hours=2),
                                         tot + pd.Timedelta(hours=2), (van, tot), moment),
                            width="stretch")
            st.markdown(f"**{gekozen_klacht['beoordeling']}** – {gekozen_klacht['reden']}"
                        + (f"  \n**Mogelijke oorzaak:** {gekozen_klacht['mogelijke oorzaak']}"
                           if gekozen_klacht["mogelijke oorzaak"] else ""))
        else:
            st.info(f"{gekozen_klacht['beoordeling']}: {gekozen_klacht['reden']}.")

    if algemeen is not None and len(algemeen):
        st.subheader(f"Algemene klachten zonder datum ({len(algemeen)})")
        st.dataframe(algemeen, width="stretch", hide_index=True)
        st.caption("Deze klachten hebben geen datum, dus de app kan ze niet aan een meting koppelen en "
                   "beoordeelt ze niet (ze staan in de rijen-trechter bij stap 8 als 'geen geldige datum'). "
                   "Ze tellen niet mee in de KPI's. Gebruik ze als signaal: vraag een datum en uur bij een volgende klacht.")

# ---------------------------------------------------------------------------
# Tab Oorzaak
# ---------------------------------------------------------------------------

with tab_oorzaak:
    st.subheader("C · Waarom buiten de band? Warmteproductie en regeling")
    k = st.session_state.get("klacht")
    meetzones = [z for z in p.comfortzones(zones).dropna(subset=["gbs_device"])["zone"]]
    standaard_zone = k["zone"] if k is not None and k["zone"] in meetzones else meetzones[0]
    standaard_dag = k["datum"].date() if k is not None else van_dag
    c1, c2 = st.columns(2)
    o_zone = c1.selectbox("Zone", meetzones, index=meetzones.index(standaard_zone),
                          format_func=lambda z: naam.get(z, z))
    o_dag = c2.date_input("Dag", value=min(max(standaard_dag, eerste.date()), laatste.date()),
                          min_value=eerste.date(), max_value=laatste.date(), format="DD/MM/YYYY")
    van = pd.Timestamp(o_dag).tz_localize(p.TZ)
    tot = van + pd.Timedelta(hours=20)
    oorzaak, meldingen = p.stap10_oorzaak(gbs["centraal"], df7, o_zone, van, tot)

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        subplot_titles=("Warmteproductie: aanvoer tegenover kringsetpoint",
                                        f"Zone {naam.get(o_zone, o_zone)}: ruimtetemp en setpoints"))
    fig.add_scatter(x=oorzaak.index, y=oorzaak["kringsetpoint"], name="kringsetpoint (gevraagd)",
                    line={"color": "#e8590c", "dash": "dash"}, row=1, col=1)
    fig.add_scatter(x=oorzaak.index, y=oorzaak["aanvoer"], name="aanvoer gemeten",
                    line={"color": "#c92a2a", "width": 3}, row=1, col=1)
    fig.add_scatter(x=oorzaak.index, y=oorzaak["buitentemp"], name="buitentemp",
                    line={"color": "#868e96"}, row=1, col=1)
    fig.add_scatter(x=oorzaak.index, y=oorzaak["bovengrens"], name="band",
                    line={"color": "#8ce99a", "dash": "dash"}, row=2, col=1, showlegend=False)
    fig.add_scatter(x=oorzaak.index, y=oorzaak["ondergrens"], name="band",
                    line={"color": "#8ce99a", "dash": "dash"}, fill="tonexty",
                    fillcolor="rgba(140,233,154,0.15)", row=2, col=1)
    fig.add_scatter(x=oorzaak.index, y=oorzaak["sp_verwarmen"], name="SP verwarmen",
                    line={"color": "#e03131", "dash": "dot", "shape": "hv"}, row=2, col=1)
    fig.add_scatter(x=oorzaak.index, y=oorzaak["sp_koelen"], name="SP koelen",
                    line={"color": "#1c7ed6", "dash": "dot", "shape": "hv"}, row=2, col=1)
    fig.add_scatter(x=oorzaak.index, y=oorzaak["ruimtetemp"], name="ruimtetemp",
                    line={"color": "#1971c2", "width": 3}, row=2, col=1)
    fig.update_layout(height=650, margin={"l": 10, "r": 10, "t": 40, "b": 10},
                      legend={"orientation": "h", "y": -0.08})
    fig.update_yaxes(title_text="°C")
    st.plotly_chart(fig, width="stretch")

    if meldingen:
        for m in meldingen:
            st.error(m)
    else:
        st.success(f"Geen kwartieren waarin de aanvoer meer dan {p.OORZAAK_DREMPEL:g} °C "
                   "onder het kringsetpoint bleef.")
    st.caption("Setpoint in de data = centraal setpoint (comfort/stand-by) + verschuiving door de "
               "gebruiker aan de thermostaat. Het centrale setpoint ging op 21/10 13:00 met +1 °C omhoog.")

# ---------------------------------------------------------------------------
# Tab Stap voor stap
# ---------------------------------------------------------------------------

STAP_FUNCTIES = {"1": p.stap1_inlezen, "2": p.stap2_nodige_punten, "3": p.stap3_zone_koppelen,
                 "3b": p.stap3b_voelerfout, "4": p.stap4_tijdzone, "5": p.stap5_per_kwartier,
                 "6": p.stap6_kantooruren, "7": p.stap7_toestand, "8": p.stap8_klachten,
                 "9": p.stap9_beoordelen}

with tab_stappen:
    st.subheader("Rijen-trechter – GBS-data")
    infos = [*gbs["infos"], i7]
    st.dataframe(p.trechter(infos), width="stretch", hide_index=True,
                 column_config={"% weg": st.column_config.NumberColumn(format="%.2f %%")})
    if i8 is not None:
        st.subheader("Rijen-trechter – klachten")
        st.dataframe(p.trechter([i8, i9]), width="stretch", hide_index=True,
                     column_config={"% weg": st.column_config.NumberColumn(format="%.1f %%")})
    st.caption("Filterstappen: rijen in = rijen uit + weg (kolom 'Klopt'). Bij omvormstappen "
               "(samenvoegen per kwartier, kolommen toevoegen) verandert het aantal rijen zonder dat er data verloren gaat.")

    st.subheader("Elke stap in detail")
    voorbeelden = {**gbs["voorbeelden"], "7": df7[df7["kantooruur"]].head()}
    if klachten is not None:
        voorbeelden["8"] = klachten.head()
        voorbeelden["9"] = beoordeeld[["klacht_nr", "zone", "Soort klacht", "van", "tot",
                                       "temp min", "temp max", "beoordeling", "reden"]]
    for info in [*infos, *(x for x in (i8, i9) if x is not None)]:
        with st.expander(f"▸ Stap {info.nr} – {info.naam}"):
            c1, c2, c3 = st.columns(3)
            c1.metric("Rijen in", "–" if info.rijen_in is None else f"{info.rijen_in:,}".replace(",", "."))
            c2.metric("Rijen uit", f"{info.rijen_uit:,}".replace(",", "."))
            c3.metric("Weg", f"{info.totaal_weg:,}".replace(",", ".") if info.soort == "filter" else "–")
            if info.uitleg:
                st.markdown(info.uitleg)
            for reden, n in info.weg.items():
                if n:
                    st.markdown(f"- **{reden}**: {n:,} rijen".replace(",", "."))
            vb = voorbeelden.get(info.nr)
            if vb is not None:
                st.markdown("**Voorbeeld van de data na deze stap**" if info.nr != "3b"
                            else "**De weggelaten metingen (voelerfout)**")
                st.dataframe(vb, width="stretch")
            if info.nr in STAP_FUNCTIES:
                st.code(inspect.getsource(STAP_FUNCTIES[info.nr]), language="python")
