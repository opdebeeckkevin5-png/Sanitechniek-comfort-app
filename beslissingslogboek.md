# Beslissingslogboek – comfortapp kantoor Sanitechniek (Project 1, Syntra)

Centrale vraag: *Zit het binnenklimaat op kantoor Sanitechniek binnen de afgesproken comfortgrenzen, en zijn de klachten gegrond?*

Vul de kolom "waarom" aan in je eigen woorden: in het no-AI gesprek moet je elke keuze zelf kunnen uitleggen.

| Datum | Vraag | Voorstel van Claude | Mijn keuze | Waarom |
|---|---|---|---|---|
| 11/11/2026 | In welke vorm verzamel ik klachten? | Excel met vaste kolommen en keuzelijsten | Aanvaard | Gelijke schrijfwijze → app kan het zonder opkuis inlezen |
| 11/11/2026 | Mogen collega's vrij typen in de keuzelijsten? | Keuzelijst als waarschuwing (vrij typen na "Ja"), datum/tijd/temperatuur streng | Aanvaard (mijn eigen idee met `'` werkte niet) | Minder vragen van collega's; datum + tijdstip zijn nodig om aan de GBS-data te koppelen |
| 11/11/2026 | Welke zonenamen op het formulier? | Zonenummer HVAC-plan + gebruikte naam, plannaam tussen haakjes | Aanvaard | Collega's kennen de namen, de app gebruikt het nummer |
| 11/11/2026 | Welke GBS-regelaar hoort bij welke zone? | Koppeling via de namen van de regelaars | Bevestigd met het inrichtingsplan van 2018 | De Priva-regelaars zijn geconfigureerd op de indeling van 2018; zie `data/zones_koppeling.csv` |
| 11/11/2026 | Regelaar KP 0.11? | Koppelen aan 0.7 | 0.7 Magazijniers = geklimatiseerd kantoor | Ruimte wordt nu door de magazijniers gebruikt |
| 11/11/2026 | Hoe behandel ik de magazijnen (0.8, 0.9, 0.10, 1.8, 1.9)? | Apart zonetype | Zonetype "magazijn gasverhitter", minder comfort | Geen zoneregelaar en geen meetdata → klachten "niet te beoordelen" |
| 11/11/2026 | KP 0.1 en KP 1.7 ontbreken in de data | Navragen bij de programmeur | Vraag aan de programmeur | Regelaars bestaan in de Priva maar zijn niet zichtbaar op BACnet |
| 11/11/2026 | Welke ruimtetemperatuur gebruik ik? | AV3 "ruimtetemperatuur (regeling)" | Aanvaard | Enkel 0.3 en 0.6 hebben een eigen voeler (AV8) |
| 11/11/2026 | Comfortgrens: GBS-setpoints of vaste band? | Beide voorgelegd | **Vaste band** | |
| 11/11/2026 | Welke band? | Typebestek 105, tabel B1.2.-1 (p. 54), uit NBN EN ISO 7730 cat. B | **Winter 20–24 °C, zomer 23–26 °C** | |
| 11/11/2026 | Wanneer is het winter of zomer? | Volgens de maand | **Winter = okt t.e.m. apr, zomer = mei t.e.m. sep** | |
| 11/11/2026 | Welke uren tellen mee? | Werkdagen 8–17 u | **Werkdagen 8–17 u** (Belgische tijd) | |
| 11/11/2026 | Wanneer is een klacht gegrond? | Buiten de band binnen ±30 min rond het tijdstip | **±30 min** | |
| 11/11/2026 | Waar staat de app? | Aparte map, los van de bedrijfsbestanden | `C:\CLAUDE\syntra\comfortapp-sanitechniek` | Repo wordt publiek: geen IP-adressen, plannen of namen van collega's |
| 11/11/2026 | Hoe zet ik metingen met verschillende tijdstippen naast elkaar? | Per kwartier de laatste meting; ontbreekt er één, vorige waarde max. 1 kwartier doortrekken; langere gaten leeg laten | Aanvaard | |
| 11/11/2026 | Vorm van het overzicht | Eerst één kolom "Zone" (lange lijst) | **Verworpen** → zones naast elkaar: tijd, buitentemp, dan per zone ruimtetemp + SP verwarmen + SP koelen | Overzichtelijker voor mij |
| 11/11/2026 | Data tot welke datum? | Nieuwe export draaien | Export 08/10 – 11/11 (eerste export stopte op 20/10) | Klachtenperiode moet erin zitten |
| 11/11/2026 | Zone 1.7 Refter heeft geen zoneregelaar op BACnet. Andere bron? | VAV-regeling in de Priva met eigen voeler (ruimtetemp, gewenste temp, CO2) mee exporteren | Aanvaard | |
| 11/11/2026 | Is de VAV-voeler even goed als de thermostaat in de refter? | Controleren: thermostaat aflezen + uur noteren en vergelijken met de data (max. ± 0,5 °C) | Nog te doen | |
| 11/11/2026 | Bij welke ruimte hoort "VAV verg. 0.7" in de Priva? | Temperatuurverloop vergelijken met alle zones | **= zone 0.6 Groene vergaderzaal** (zelfde voeler: gem. verschil 0,00 °C, correlatie 0,99 over 5 weken) | Nagekeken met de data zelf, niet aangenomen |
| 11/11/2026 | Zone 0.1 heeft geen data | Geen alternatieve bron gevonden → regelaar laten zichtbaar maken door de programmeur | Gevraagd aan de programmeur | Tot dan: "geen data", niet "in orde" |
| 12/11/2026 | Waarom stijgt de temperatuur in het weekend? Staat de regeling in comfort? | Setpoints en kraan nakijken | Stand-by (16/26), kraan in rust → stijging komt van zon en buitentemperatuur | |
| 12/11/2026 | Waarom verandert het setpoint, ook buiten de kantooruren? | Patronen zoeken in alle zones | 3 oorzaken: centrale verhoging +1 °C op 21/10 13:00 · optimale start (comfort vanaf ± 03:30–05:30) · verschuiving door gebruikers aan de thermostaat | |
| 12/11/2026 | Hoe bepaal ik de thermostaatverschuiving per zone? | Setpoint zone − centraal setpoint; centraal = eerst mediaan, daarna **modus** (meest voorkomende waarde) | Modus (mediaan schoof mee als veel zones tegelijk verdraaid waren) | |
| 12/11/2026 | Verandert de centrale verhoging van 21/10 mijn beoordeling? | Vaste band blijft 20–24 °C → beoordeling verandert niet; wel periode voor/na apart kunnen tonen | Nog te beslissen | |
| 12/11/2026 | Waarom is het op sommige maandagen om 8:00 te koud? | Eerst gedacht: debiet per lokaal. Data toont: warmteproductie levert niet (aanvoer volgt kringsetpoint niet) op 8 van 21 werkdagen | Oorzaak = warmteproductie; klachten op die ochtenden **gegrond** | Op dagen met tijdig warm water was het om 8:00 overal ≥ 20,4 °C |
| 12/11/2026 | Aanvoertemperatuur t.o.v. kringsetpoint tonen in de app? | Ja, als "grondige reden" naast de comfortband | Nog te beslissen | |
| 12/11/2026 | Ontwerp dashboard (stap 1) | Ontwerp in Excalidraw: zijbalk, 5 KPI's, tabs Comfort / Klachten / Oorzaak / Stap voor stap | Aanvaard (`ontwerp_dashboard.excalidraw`) | |
| 12/11/2026 | Zonetabel sorteren op? | % binnen band | **% buiten band** (aflopend) | We willen de problemen eerst zien |
| 12/11/2026 | Klacht "te koud" terwijl het te warm was | Aparte categorie of ongegrond | **Ongegrond** → "gegrond" enkel als de afwijking in de richting van de klacht gaat | |
| 12/11/2026 | Klacht zonder uur (enkel datum) | Weglaten of hele werkdag | **Hele werkdag (8–17 u) bekijken** | |
| 13/11/2026 | Feestdagen in de kantooruren? | Weglaten of laten staan | **Weglaten**: lijst `data/feestdagen.csv` (Belgische wettelijke feestdagen 2026–2027, zelf aan te vullen met sluitingsdagen) | In de huidige data valt enkel wo 11/11 (Wapenstilstand) op een werkdag |
| 13/11/2026 | Wat met onmogelijke temperaturen (voelerfout)? | Metingen < 10 °C of > 35 °C weglaten en tellen in de rijen-trechter | **Aanvaard** | Wo 21/10 11:39–11:41: 3 zones tegelijk 0,0 °C (3 van 50 458 metingen) → zou ten onrechte "te koud" geven |
| 12/11/2026 | Ook behaaglijkheid/ventilatie (CO2, RV, akoestiek) in de app? | CO2 enkel bij klachten in 0.6/1.7, of later een apart dashboard | **Later, apart dashboard** (kandidaat Project 3) | CO2 maar in 2 ruimtes, geen bruikbare RV-meting (Priva toont 0,9 %), geen akoestiekmeting; deadline 17/11 |
| 12/11/2026 | Maatstaf voor inregeling | Opwarmsnelheid per zone (°C/u, eerste uur, kraan volledig open, gedeeld door aanvoer − ruimte) | Nog te beslissen (buiten scope app?) | |
| 13/11/2026 | Zone 1.7 in `zones_koppeling.csv` | Device 500 (VAV-voeler AV191/171/170) invullen i.p.v. "niet uitgelezen" | Aanvaard | Koppeling moet kloppen met de export van 11/11 |
| 13/11/2026 | Versiebeheer | Git opzetten vóór er code komt (eerste commit = ontwerp + logboek + referentiedata) | Aanvaard | Vangnet: altijd terug naar een werkende versie |
| 13/11/2026 | Spec-prompt (stap 2) | `spec_prompt.md` volgens de 5 vragen (data, weglaten, stappen, output, controle) + verplichte slotzin; kolom **Duur** bewust niet ingevuld | Aanvaard; uitvoeren in een **nieuwe** sessie | De vragen van Claude komen hieronder, elk met mijn antwoord |

## Bekende beperkingen (eerlijk tonen in de app)
- De norm spreekt over **operatieve temperatuur** (lucht + straling); het GBS meet **luchttemperatuur**. Bij klimaatplafonds kan dat verschillen.
- Meetinterval zones ± 15 min. Export 08/10 – 11/11; datagaten (alle punten tegelijk, Belgische tijd):
  **ma 12/10 01:45 → di 13/10 01:15 (hele werkdag)** · do 22/10 01:00–01:45 · vr 30/10 17:00–20:45 ·
  **za 07/11 22:45 → di 10/11 10:00 (maandag + dinsdagochtend)** → klachten op die momenten = "niet te beoordelen".
- Zones worden pas uitgelezen vanaf 08/10 ± 21:30.
- Tijdstippen in de data zijn **UTC** → omzetten naar Belgische tijd (let op winteruur 25/10).
- Zone 0.1: geen data tot de regelaar op BACnet zichtbaar is.
- Zone 1.7 Refter: **andere voeler** dan de andere zones (VAV-voeler van de Priva i.p.v. de zoneregelaar); VAV heeft één setpoint.
- Het centrale setpoint ging op **21/10 13:00 +1 °C** (comfort 20 → 21, stand-by 16 → 17): periodes voor en na zijn niet gelijk ingesteld.
- Het setpoint in de data = centraal setpoint + verschuiving door gebruikers; de thermostaatknop zelf zit niet in de data.
