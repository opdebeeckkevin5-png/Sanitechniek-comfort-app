# Spec-prompt – comfortapp kantoor (Project 1, stap 2)

> Gebruik: open een **nieuwe** Claude Code-sessie in deze map (na `conda activate syntra-ds`),
> sleep `ontwerp_dashboard.svg` in het venster en plak alles onder de lijn.
> Beantwoord elke vraag van Claude en noteer het antwoord in `beslissingslogboek.md`.
> Vraagt Claude iets wat hieronder al had moeten staan? Vul dan ook deze spec aan.

---

Bouw een Streamlit-app die deze vraag beantwoordt: **"Zit het binnenklimaat op kantoor binnen de
comfortgrenzen, en zijn de klachten van collega's gegrond?"** Het publiek is collega's en directie
(antwoord in één oogopslag) en ikzelf (de oorzaak zoeken). De app moet bij elke afwijking een
**grondige reden** kunnen tonen. Het ontwerp zit in de bijlage (`ontwerp_dashboard.svg`) en in
`ontwerp.md`. Alle keuzes en hun reden staan in `beslissingslogboek.md`. Lees die drie eerst.

## 1. Data
De app werkt met **twee uploads**. De echte data komt nooit in de repo, want die wordt publiek.
- **GBS-export** (`.csv.gz`, `;`-gescheiden), kolommen `ts;device;type;instance;waarde`.
  `ts` staat in **UTC** (ISO met `+00:00`). Elke rij is één meting van één BACnet-punt.
  - Zones: `device` = zoneregelaar (zie `data/zones_koppeling.csv`), `analog-value` 3 = ruimtetemp,
    1 = setpoint verwarmen, 2 = setpoint koelen.
  - Zone 1.7 Refter: `device` 500, `analog-value` 191 = ruimtetemp, 171 = SP verwarmen,
    170 = SP koelen (VAV-voeler van de centrale regeling, andere voeler dan de andere zones).
  - Centraal (`device` 500): `analog-input` 1 = buitentemp, `analog-input` 12 = aanvoertemp gemeten,
    `analog-value` 66 = kringsetpoint (gewenste aanvoertemp).
  - Alle andere punten zijn niet nodig.
- **Klachtenformulier** (`.xlsx`, blad `Klachten`), kolommen: Datum, Tijdstip, Duur, Zone, Discipline,
  Soort klacht, Ernst, Raam/deur open, Zelf aangepast, Gemeten temp (°C), Omschrijving,
  Melder (initialen), Beoordeling, Oorzaak, Opmerking technische dienst.
  - Zone = de tekst uit `data/zones_koppeling.csv` (kolom `formulier_zone`).
  - Discipline: CV (verwarming), Koeling, Ventilatie, Akoestiek, Andere / weet niet.
  - Soort klacht: Te warm, Te koud, Tocht, Bedompte / muffe lucht, Geur, Te droog, Te vochtig,
    Lawaai van installatie, Geluid uit andere ruimte, Trillingen, Andere.
- **Vaste bestanden in de repo:** `data/zones_koppeling.csv` (zone ↔ device, zonetype) en
  `data/feestdagen.csv` (`datum;naam;soort`).

## 2. Wat laat ik weg (en tel ik in de rijen-trechter)
- BACnet-punten die hierboven niet staan.
- Devices zonder zone.
- Temperaturen **< 10 °C of > 35 °C** (voelerfout).
- Voor de comfortberekening: alles buiten de **kantooruren** = ma–vr 8–17 u Belgische tijd,
  zonder feestdagen uit `feestdagen.csv`.
- Klachten zonder geldige datum of met een onbekende zone.
- Kolommen **Melder** en **Omschrijving** worden niet gebruikt en niet getoond (privacy).

## 3. Stappen
Bouw als **pijplijn van inspecteerbare stappen**:
- `pipeline.py` met **pure functies**, één per stap, **zonder Streamlit-imports**. Elke stap geeft
  het resultaat terug **én** hoeveel rijen er wegvielen en waarom.
- `app.py` toont elke stap in een eigen `st.expander`: rijen in, rijen uit, reden, voorbeeld van de data.

| # | Stap |
|---|---|
| 1 | GBS-data inlezen |
| 2 | Enkel de nodige punten houden |
| 3 | Zone koppelen via `zones_koppeling.csv` |
| 3b | Onmogelijke temperaturen weglaten (< 10 of > 35 °C) |
| 4 | UTC → Europe/Brussels (let op het winteruur op 25/10) |
| 5 | Per kwartier gelijkzetten: laatste meting van het kwartier; ontbreekt er één, de vorige waarde **max. 1 kwartier** doortrekken; langere gaten blijven leeg |
| 6 | Kantooruren aanduiden (ma–vr 8–17 u, zonder feestdagen) |
| 7 | Toestand per kwartier: binnen band / te koud / te warm / geen data |
| 8 | Klachten inlezen + controleren |
| 9 | Elke klacht beoordelen (regels hieronder) |
| 10 | Oorzaak tonen: aanvoertemp tegenover kringsetpoint, plus de setpoints van de zone |

**Comfortband** (aanpasbaar in de zijbalk): winter (okt–apr) **20–24 °C**, zomer (mei–sep) **23–26 °C**.

**Beoordeling van een klacht** (kijk naar de kwartieren **±30 min** rond het tijdstip):
- *Gegrond*: minstens één kwartier buiten de band **in de richting van de klacht**
  ("Te koud" en de temperatuur was te koud).
- *Ongegrond*: alles binnen de band, of enkel buiten de band in de andere richting.
- *Niet te beoordelen – geen data*: een datagat rond het tijdstip.
- *Niet te beoordelen – geen meting*: zone zonder regelaar (magazijnen, 0.1) of "Andere / weet niet".
- *Niet te beoordelen – ander thema*: elke soort klacht behalve Te warm / Te koud.
- Klacht **zonder tijdstip** → de hele werkdag (8–17 u) van die datum bekijken.

## 4. Output (zie de schets)
- **Zijbalk:** de twee uploads, filter zone, filter periode, de grenzen van de band (min/max).
- **Bovenaan 5 KPI's:** % kantoorkwartieren binnen de band · aantal klachten · gegrond · ongegrond ·
  niet te beoordelen.
- **Tab Comfort:** A1 een tabel per zone, gesorteerd op **% buiten de band (aflopend)** · A2 een heatmap
  zone × dag · A3 te koud of te warm per zone.
- **Tab Klachten:** B1 een tabel met de beoordeling per klacht · B3 bij een gekozen klacht de
  temperatuur ±2 u rond het moment, met de band erop.
- **Tab Oorzaak:** aanvoertemp tegenover het kringsetpoint, en de setpoints van de zone.
- **Tab Stap voor stap:** de rijen-trechter (aantal + % per stap, met de reden) en de expanders.
- **Meldingen** van de bekende beperkingen: datagaten in de kantooruren, zone 0.1 zonder data, de
  refter met een andere voeler, luchttemperatuur ≠ operatieve temperatuur.

## 5. Controle
- Steekproef: **ma 26/10 08:30, zone 1.2** → *gegrond (te koud)*. De oorzaak moet zichtbaar zijn:
  de aanvoer bleef ± 19,5 °C terwijl het kringsetpoint veel hoger lag.
- Steekproef: **15/10 10:00, zone 1.2** = ± 21,5 °C → binnen de band.
- Wo 21/10 ± 11:40: 3 metingen van 0,0 °C moeten in de trechter staan als "voelerfout".
- De trechter moet kloppen: rijen in = rijen uit + weggevallen rijen, bij elke stap.

## Technische afspraken
- Python-environment `syntra-ds`. Installeer niets zonder het eerst te vragen.
- `requirements.txt` met enkel wat de app nodig heeft. Geen `environment.yml` in de repo.
- Geen echte data, IP-adressen of namen van collega's in de repo (`.gitignore` staat al klaar).
- Maak een testbestand met **verzonnen** data om de app zonder de echte export te kunnen proberen.

Stel ons eerst een vraag op elke plek waar je zelf een aanname zou maken. Begin pas met bouwen als alle vragen beantwoord zijn.
