# TPER Tracker

**Lingue disponibili:** [Inglese](README.md) | [Italiano](README.it.md)

Un'integrazione per Home Assistant per monitorare gli arrivi degli autobus in tempo reale di [TPER](https://www.tper.it/), il gestore del trasporto pubblico che serve Bologna e le zone limitrofe.

## Funzionalità

- 🚌 Orari di arrivo degli autobus in tempo reale.
- 🔍 Ricerca fermate per nome, indirizzo o numero fermata.
- 📍 Monitoraggio di più linee per fermata.
- 📡 Stato del tracciamento GPS per gli autobus.
- ♿ Informazioni sull'accessibilità per sedie a rotelle.
- 🕐 Polling adattivo intelligente basato sull'ETA.
- 🌐 Supporto multilingua (Inglese e Italiano).

## Installazione

### HACS (Consigliato)

1. Apri HACS nella tua istanza di Home Assistant.
2. Clicca il menu a tre punti e seleziona "Archivi digitali personalizzati".
3. Aggiungi `https://github.com/ddrimus/ha-tper-tracker` come URL del repository e scegli come tipo "Integrazione".
5. Clicca "Aggiungi" per salvare il repository.
6. Cerca "TPER Tracker" e installalo.
7. Riavvia Home Assistant.

### Installazione Manuale

1. Scarica l'ultima versione dalla [pagina delle release](https://github.com/ddrimus/ha-tper-tracker/releases).
2. Estrai la cartella `tper_tracker` nella tua directory `custom_components`.
3. Riavvia Home Assistant.

## Configurazione

1. Vai su **Impostazioni** → **Dispositivi e Servizi**.
2. Clicca **Aggiungi Integrazione** e cerca "TPER Tracker".
3. Inserisci un termine di ricerca per la tua fermata (nome, indirizzo o numero fermata).
4. Seleziona la tua fermata dai risultati della ricerca.
5. Scegli quali linee di autobus vuoi monitorare.
6. Clicca **Invia**.

L'integrazione creerà entità sensore per ogni linea selezionata che mostrano il prossimo orario di arrivo.

## Sensori

Ogni linea di autobus monitorata crea un sensore con le seguenti informazioni:

- **Stato**: Il prossimo orario di arrivo dell'autobus (come timestamp).

- **Attributi**:

  - `last_update`: Timestamp di quando i dati sono stati aggiornati l'ultima volta.
  - `line_id`: Identificatore per la linea di autobus.
  - `next_bus_1_time`: Orario di arrivo del primo autobus.
  - `next_bus_1_satellite`: Stato del tracciamento GPS per il primo autobus.
  - `next_bus_1_accessible`: Indica se il primo autobus è accessibile alle sedie a rotelle.
  - `next_bus_2_time`: Orario di arrivo del secondo autobus (se disponibile).
  - `next_bus_2_satellite`: Stato del tracciamento GPS per il secondo autobus.
  - `next_bus_2_accessible`: Indica se il secondo autobus è accessibile alle sedie a rotelle.

## Contributi

Se hai miglioramenti, informazioni aggiuntive, o noti problemi con TPER Tracker, ci piacerebbe sentire da te! Sentiti libero di aprire una pull request con i tuoi suggerimenti o dettagli.

Se incontri problemi con l'integrazione o credi che qualcosa non funzioni come previsto, fornisci tutte le informazioni rilevanti in un issue. I tuoi contributi, suggerimenti e feedback sono sempre benvenuti e apprezzati!

## Disclaimer

Questa integrazione **non è affiliata** con **TPER** o **WebBus**. Utilizza dati pubblicamente disponibili da TPER attraverso il servizio di terze parti **WebBus** ([https://webus.bo.it/](https://webus.bo.it/)) per fornire informazioni sugli autobus in tempo reale. L'accuratezza e la disponibilità dei dati dipendono dall'API di WebBus, e qualsiasi problema con il servizio è al di fuori del controllo di questa integrazione.