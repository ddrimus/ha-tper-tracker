# TPER Tracker

**Lingue disponibili:** [Inglese](README.md) | [Italiano](README.it.md)

Un'integrazione per Home Assistant per monitorare gli arrivi degli autobus in tempo reale di [TPER](https://www.tper.it/), il gestore del trasporto pubblico che serve Bologna e le zone limitrofe.

<p>
  <a href="https://github.com/ddrimus/ha-tper-tracker/releases"><img src="https://img.shields.io/github/v/release/ddrimus/ha-tper-tracker?display_name=tag&label=Ultima%20Versione&color=47c72a&labelColor=404951" alt="Ultima Versione"></a>
  <a href="https://github.com/ddrimus/ha-tper-tracker/actions/workflows/python-test-suite.yml"><img src="https://img.shields.io/github/actions/workflow/status/ddrimus/ha-tper-tracker/python-test-suite.yml?branch=main&label=Suite%20di%20Test&labelColor=404951" alt="Suite di Test"></a>
  <a href="https://github.com/ddrimus/ha-tper-tracker/actions/workflows/home-assistant-validation.yml"><img src="https://img.shields.io/github/actions/workflow/status/ddrimus/ha-tper-tracker/home-assistant-validation.yml?branch=main&label=Validazione&labelColor=404951" alt="Validazione"></a>
  <a href="https://github.com/ddrimus/ha-tper-tracker/actions/workflows/tper-live-check.yml"><img src="https://img.shields.io/github/actions/workflow/status/ddrimus/ha-tper-tracker/tper-live-check.yml?label=Controllo%20TPER&labelColor=404951" alt="Controllo TPER"></a>
</p>

## Funzionalità

- 🚌 Orari di arrivo degli autobus in tempo reale.
- 🔍 Ricerca fermate per nome, indirizzo o numero fermata.
- 📍 Monitoraggio di più linee per fermata.
- 📡 Stato del tracciamento GPS per gli autobus.
- ♿ Informazioni sull'accessibilità per sedie a rotelle.
- 🕐 Polling adattivo intelligente basato sull'ETA.
- ⏰ Orario attivo opzionale per seguire i bus solo quando servono.
- 🔁 Cambio fermata senza perdere sensori e automazioni.
- 🛠️ Avvisi di riparazione quando una fermata o una linea non è più servita.
- 🌐 Supporto multilingua (Inglese e Italiano).

## Installazione

### HACS (Consigliato)

[![Apri la tua istanza di Home Assistant e apri questo repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ddrimus&repository=ha-tper-tracker&category=integration)

1. Apri HACS nella tua istanza di Home Assistant (**Impostazioni** → **Marketplace** da Home Assistant 2026.11).
2. Cerca "TPER Tracker" e installalo.
3. Riavvia Home Assistant.

### Installazione Manuale

1. Scarica l'ultima versione dalla [pagina delle release](https://github.com/ddrimus/ha-tper-tracker/releases).
2. Estrai la cartella `tper_tracker` nella tua directory `custom_components`.
3. Riavvia Home Assistant.

### Aggiornamento dalla 1.x

La versione 2.0 usa una nuova fonte dati TPER, quindi le voci della 1.x non possono essere aggiornate e mostrano **Errore di migrazione**. Elimina la voce e aggiungi di nuovo la tua fermata.

## Configurazione

1. Vai su **Impostazioni** → **Dispositivi e Servizi**.
2. Clicca **Aggiungi Integrazione** e cerca "TPER Tracker".
3. Inserisci un termine di ricerca per la tua fermata (nome, indirizzo o numero fermata).
4. Seleziona la tua fermata dai risultati della ricerca.
5. Scegli quali linee di autobus vuoi monitorare.
6. Clicca **Invia**.

L'integrazione creerà entità sensore per ogni linea selezionata che mostrano il prossimo orario di arrivo.

Clicca **Configura** sull'integrazione per cambiare le linee monitorate o per impostare l'orario attivo, usando qualsiasi entità acceso/spento come un aiutante **Programmazione** con gli orari del tuo tragitto. Per passare a un'altra fermata, scegli **Riconfigura**: le linee servite da entrambe le fermate mantengono sensori e automazioni.

## Sensori

Ogni linea di autobus monitorata crea un sensore con le seguenti informazioni:

- **Stato**: Il prossimo orario di arrivo dell'autobus (come timestamp).

- **Attributi**:

  - `line`: Il codice della linea di autobus.
  - `status`: Lo stato della linea (`ok`, `no_buses`, `not_served`, `inactive` oppure `error`).
  - `next_bus_1_time`: Orario di arrivo del primo autobus.
  - `next_bus_1_satellite`: Stato del tracciamento GPS per il primo autobus.
  - `next_bus_1_accessible`: Indica se il primo autobus è accessibile alle sedie a rotelle.
  - `next_bus_1_vehicle`: Numero di vettura del primo autobus.
  - `next_bus_2_time`: Orario di arrivo del secondo autobus (se disponibile).
  - `next_bus_2_satellite`: Stato del tracciamento GPS per il secondo autobus.
  - `next_bus_2_accessible`: Indica se il secondo autobus è accessibile alle sedie a rotelle.
  - `next_bus_2_vehicle`: Numero di vettura del secondo autobus.

## Contributi

Se hai miglioramenti, informazioni aggiuntive, o noti problemi con TPER Tracker, ci piacerebbe sentire da te! Sentiti libero di aprire una pull request con i tuoi suggerimenti o dettagli.

Se incontri problemi con l'integrazione o credi che qualcosa non funzioni come previsto, fornisci tutte le informazioni rilevanti in un issue, incluso il file di **Scarica diagnostica** dalla pagina dell'integrazione. I tuoi contributi, suggerimenti e feedback sono sempre benvenuti e apprezzati!

## Disclaimer

Questa integrazione **non è affiliata** con **TPER**. Utilizza dati pubblicamente disponibili da TPER attraverso il servizio **Hello Bus** e il portale [open data TPER](https://solweb.tper.it/web/tools/open-data/open-data.aspx) (CC BY 3.0 IT) per fornire informazioni sugli autobus in tempo reale. L'accuratezza e la disponibilità dei dati dipendono da TPER, e qualsiasi problema con il servizio è al di fuori del controllo di questa integrazione.