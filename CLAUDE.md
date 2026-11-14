# Afspraken – comfortapp kantoor (Syntra Data Scientist, Project 1)

**Centrale vraag:** *Zit het binnenklimaat op kantoor binnen de comfortgrenzen, en zijn de klachten gegrond?*
Lees bij elke nieuwe sessie eerst `ontwerp.md` en `beslissingslogboek.md`. De spec staat in `spec_prompt.md`.

## Projectstructuur
| Bestand | Wat |
|---|---|
| `pipeline.py` | Al het rekenwerk: één pure functie per stap (1–10), **geen Streamlit-imports** |
| `app.py` | Enkel het scherm (Streamlit): zijbalk, KPI's, tabs Comfort / Klachten / Oorzaak / Stap voor stap |
| `tests/test_pipeline.py` | Tests op de regels uit de spec (draaien op de voorbeelddata) |
| `maak_testdata.py` | Maakt de **verzonnen** testdata in `data/voorbeeld/` |
| `data/zones_koppeling.csv`, `data/feestdagen.csv` | Vaste referentiedata |

## Werken
- Environment: `conda activate syntra-ds`. **Niets installeren** zonder het eerst te vragen.
- App starten: `streamlit run app.py` · tests: `python -m pytest`
- Elke stap in `pipeline.py` geeft `(resultaat, StapInfo)` terug: rijen in, rijen uit, en per reden hoeveel rijen
  wegvielen. Bij filterstappen moet gelden: **rijen in = rijen uit + weg**. Een nieuwe stap volgt hetzelfde patroon
  en krijgt een expander in de tab "Stap voor stap".
- Na elke wijziging in `pipeline.py`: tests draaien. Rood = eerst oplossen, niet de test aanpassen zonder te vragen.
- Vóór een grote wijziging: commit of een aparte branch.

## Analyse: korte lus, ik beslis
- Een keuze die een getal op het dashboard kan veranderen (band, venster, filter, noemer, drempel, lege waarden)
  maak je **niet stil**: stel eerst een vraag.
- Elke beslissing komt in `beslissingslogboek.md` (datum, vraag, voorstel, mijn keuze, waarom).
- Getallen altijd narekenen in de data, niet schatten. Zeg hoeveel rijen je gebruikte en uitsloot.

## Vastgelegde regels (details en reden: zie logboek)
- Band: winter (okt–apr) 20–24 °C, zomer (mei–sep) 23–26 °C. Kantooruren: ma–vr 8–17 u Belgische tijd, zonder feestdagen.
- Voelerfout: enkel **ruimtetemperaturen** < 10 of > 35 °C weglaten.
- Per kwartier: laatste meting, max. 1 kwartier doortrekken. Afronden altijd **in UTC** (winteruur 25/10).
- % binnen band = van de kwartieren **mét** data; "geen data" apart tonen.
- Klacht: kwartieren ±30 min (klacht 08:30 → 08:00 t.e.m. 09:00); zonder tijdstip → hele werkdag.
  Gegrond enkel als de afwijking in de richting van de klacht gaat.

## Wat nooit in de repo mag (de repo is publiek)
- Echte GBS-exports of ingevulde klachtenformulieren → enkel uploaden in de app.
- IP-adressen, netwerkgegevens, namen of initialen van collega's, plannen van het gebouw.
- Geheimen (`.env`). `environment.yml` van de cursus hoort hier niet: enkel `requirements.txt`.
