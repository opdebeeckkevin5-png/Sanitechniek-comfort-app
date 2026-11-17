# Overdracht 17/11/2026 – comfortapp kantoor (Syntra Project 1)

*Startnota voor een volgende sessie. Lees daarna `CLAUDE.md`, `ontwerp.md` en `beslissingslogboek.md`.*
*Deze map is een **publieke** repo: geen IP-adressen, netwerkgegevens of namen van collega's in deze nota.*

## Stand
- **Oplevering M1: di 17/11/2026** (repo + publieke URL + ontwerp + no-AI gesprek).
- **Live app:** https://sanitechniek-comfort.streamlit.app/ (start met verzonnen voorbeelddata; echte data enkel via upload).
- **Repo:** https://github.com/opdebeeckkevin5-png/Sanitechniek-comfort-app – branch `main`, laatste merge `5458266`
  (schets op papier). Branches gemerged met `--no-ff`: `fix-ruwe-export`, `klachten-mail`, `klachten-csv`, `ontwerp-foto`
  (+ `claude-md` als fast-forward).
- **Tests:** 28, alle groen (`python -m pytest`). Environment `syntra-ds`.
- Commits gebruiken het GitHub-noreply-adres (lokaal ingesteld in deze repo, geschiedenis herschreven vóór de eerste push).

## Wat de app doet (kort)
Pijplijn in `pipeline.py` (stap 1–10, pure functies, rijen-trechter), scherm in `app.py`:
zijbalk (uploads, filters, band) · 5 KPI's · tabs Comfort / Klachten / Oorzaak / Stap voor stap.
Sinds 14–16/11 erbij:
- **Ruwe GBS-dump** (alle punten, ook `active`/`inactive`) wordt aanvaard → stap 2 zet `waarde` om naar getal.
- **Klachten als `.xlsx` of `.csv`** (download uit OneDrive/Excel Online). Datumvolgorde per bestand bepaald:
  Excel Online schrijft **maand/dag/jaar** (10/26/2026) – anders werd 11/9 stil 11 september.
- Kolom **"Zelf gemeten"** + ⚠️ bij > 2 °C verschil met het GBS; **klachten zonder datum** apart getoond (niet beoordeeld).

## Waar staat de data (niet in git)
| Wat | Waar |
|---|---|
| GBS-export voor de demo (08/10 – 16/11 12:29, 284 740 rijen) | `C:\CLAUDE\bacnet\werf-SKW-sanitechniek\data\kringdata_2026-11-16.csv.gz` |
| Hoe die export gemaakt wordt (commando, controle) | `C:\CLAUDE\bacnet\OVERDRACHT_2026-11-16_export_kringdata.md` |
| Klachten-overzicht uit OneDrive (CSV) | `data\klachtenformulier_sanitechniek(Klachten).csv` |
| Klachten uit de 2 mails (xlsx + csv) | `data\echt\klachten_mail1.xlsx`, `klachten_mail2.xlsx`, `klachten_mail2.csv` |
| De mails zelf | `data\*.eml` |

`.gitignore` blokkeert: `data/echt/`, `*.csv.gz` (behalve `data/voorbeeld/`), `*klacht*.csv`, `*klacht*.xlsx`
(behalve `data/voorbeeld/`), `*.eml`, `*.msg`. Controle 17/11: 0 echte bestanden in git.

⚠️ **Niet committen:** `PROJECT COMFORT KANTOOR SANITECHNIE.txt` (eigen notities, bevat het IP-adres van de Pi) en
`.claude/` (lokale instellingen met gebruikersnaam).

## Resultaten met echte data (kantooruren 08/10 – 16/11)
- **88 %** van de gemeten kwartieren binnen 20–24 °C. Slechtst: 0.5 Inkomhal (20,8 % buiten, vooral te koud;
  setpoint 21 °C, haalt het slecht), 0.7 Magazijniers, 1.7 Refter.
- **Klachten:** 26/10 08:00 zone 0.7 **gegrond** (aanvoer ± 20 °C i.p.v. 35 °C → warmteproductie) · 09/11 08:00 zone 0.7
  **n.t.b. – datagat** · 11/11 11:49 zone 1.3 **ongegrond** (GBS 21,5 °C, zelf gemeten 16,0 °C ⚠️) · 4 klachten zonder datum.
- Vondst: op **11/11 (Wapenstilstand, gesloten)** stond de verwarming in comfort → feestdagen niet in het klokprogramma.

## Open punten
**Te beslissen / na te vragen (logboek)**
- Klacht 11/11 zone 1.3: datum klopt waarschijnlijk niet (bedrijf gesloten) → navragen; **nameten** (16 vs 21,5 °C).
- De klacht van 11/11 staat **niet** in het OneDrive-overzicht → toevoegen.
- OneDrive: kolom Datum opmaken als **jjjj-mm-dd**.
- Periode vóór/na de centrale verhoging (21/10, +1 °C) apart tonen? · Maatstaf opwarmsnelheid (inregeling) – buiten scope.
- Ruwe dump: periode in de zijbalk vanaf 09/10 (zones pas uitgelezen vanaf 08/10).
- Band voor de inkomhal (circulatieruimte?) – bewust zo gelaten (20–24 °C).
- Voorstellen van 16/11 in het logboek nog bevestigen: enkel mail 2, klachten zonder datum apart, drempel 2 °C, datumregel.

**Bij de programmeur / GBS (uit eigen notities)**
- Zone 0.1: regelaar nog niet zichtbaar op BACnet.
- Refter 1.7: verkeerde voeler gebruikt → aanpassing gevraagd. VAV-voeler vergelijken met de thermostaat (± 0,5 °C).
- Datagaten: één door opgebruikte RMS-credits, één onbekend → Revolution Pi gepland voor lokale monitoring.

**No-AI gesprek – herbekijken (oefengesprek 16/11)**
1. Klachtregel: **gemeten ruimtetemp**, venster **±30 min** (5 kwartieren), niet het setpoint, niet de hele dag.
2. KPI: enkel ruimtetemp, enkel kantooruren, noemer zonder "geen data".
3. Winteruur 25/10: geen datagat maar een **crash** (dubbel uur 02:00–03:00) → afronden in UTC.
4. Laatste meting i.p.v. gemiddelde: punten worden op verschillende momenten gemeten → per kwartier gelijkzetten.
Patroon voor elk antwoord: **wat → waarom → waar in de app**.

## Volgende stap (na de oplevering) – voorstel, nog niet beslist
Collega's de app met **echte data** laten volgen zonder upload:
- **Optie A (aanbevolen):** tweede, **afgeschermde** Streamlit-app (viewers per e-mail) die GBS-export en
  klachten-Excel uit een **gedeelde OneDrive-map** leest; links in Streamlit *secrets*, niet in de repo.
  De Syntra-app blijft publiek met voorbeelddata.
- Na te kijken: aantal afgeschermde apps op Community Cloud · directe downloadlink zakelijke OneDrive ·
  akkoord Sanitechniek voor bedrijfsdata op een externe dienst.
- Automatisch doorsturen van de export Pi → OneDrive hoort bij het BACnet-project (zie de nota daar).
- Opties B (bestand op de server, valt weg bij herstart) en C (lokaal op een kantoor-pc) besproken, niet gekozen.
