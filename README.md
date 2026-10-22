# TPER Tracker

**Available languages:** [English](README.md) | [Italian](README.it.md)

A Home Assistant integration to track real-time bus arrivals from [TPER](https://www.tper.it/), the public transport provider serving Bologna and surrounding areas.

<p>
  <a href="https://github.com/ddrimus/ha-tper-tracker/releases"><img src="https://img.shields.io/github/v/release/ddrimus/ha-tper-tracker?display_name=tag&label=Latest%20Release&color=47c72a&labelColor=404951" alt="Latest Release"></a>
  <a href="https://github.com/ddrimus/ha-tper-tracker/actions/workflows/python-test-suite.yml"><img src="https://img.shields.io/github/actions/workflow/status/ddrimus/ha-tper-tracker/python-test-suite.yml?branch=main&label=Test%20Suite&labelColor=404951" alt="Test Suite"></a>
  <a href="https://github.com/ddrimus/ha-tper-tracker/actions/workflows/home-assistant-validation.yml"><img src="https://img.shields.io/github/actions/workflow/status/ddrimus/ha-tper-tracker/home-assistant-validation.yml?branch=main&label=Validation&labelColor=404951" alt="Validation"></a>
  <a href="https://github.com/ddrimus/ha-tper-tracker/actions/workflows/tper-live-check.yml"><img src="https://img.shields.io/github/actions/workflow/status/ddrimus/ha-tper-tracker/tper-live-check.yml?label=TPER%20Live%20Check&labelColor=404951" alt="TPER Live Check"></a>
</p>

## Features

- 🚌 Real-time bus arrival times.
- 🔍 Search bus stops by name, address, or stop number.
- 📍 Monitor multiple bus lines per stop.
- 📡 GPS tracking status for buses.
- ♿ Wheelchair accessibility information.
- 🕐 Smart adaptive polling based on ETA.
- ⏰ Optional active hours to track buses only when you need them.
- 🔁 Change stop without losing sensors and automations.
- 🛠️ Repair notices when a stop or line is no longer served.
- 🌐 Multi-language support (English & Italian).

## Installation

### HACS (Recommended)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ddrimus&repository=ha-tper-tracker&category=integration)

1. Open HACS in your Home Assistant instance (**Settings** → **Marketplace** from Home Assistant 2026.11).
2. Search for "TPER Tracker" and install it.
3. Restart Home Assistant.

### Manual Installation

1. Download the latest release from the [releases page](https://github.com/ddrimus/ha-tper-tracker/releases).
2. Extract the `tper_tracker` folder to your `custom_components` directory.
3. Restart Home Assistant.

### Upgrading from 1.x

Version 2.0 moved to a new TPER data source, so 1.x entries can't be upgraded and show **Migration error**. Delete the entry and add your stop again.

## Configuration

1. Go to **Settings** → **Devices & Services**.
2. Click **Add Integration** and search for "TPER Tracker".
3. Enter a search term for your bus stop (name, address, or stop number).
4. Select your bus stop from the search results.
5. Choose which bus lines you want to monitor.
6. Click **Submit**.

The integration will create sensor entities for each selected bus line showing the next arrival time.

Click **Configure** on the integration to change the monitored lines or to set active hours, using any on/off entity such as a **Schedule** helper with your commute times. To move to another stop, choose **Reconfigure**: lines served at both stops keep their sensors and automations.

## Sensors

Each monitored bus line creates a sensor with the following information:

- **State**: The next bus arrival time (as a timestamp).

- **Attributes**:

  - `line`: The bus line code.
  - `status`: The line status (`ok`, `no_buses`, `not_served`, `inactive` or `error`).
  - `next_bus_1_time`: Arrival time of the first bus.
  - `next_bus_1_satellite`: GPS tracking status for the first bus.
  - `next_bus_1_accessible`: Indicates whether the first bus is wheelchair accessible.
  - `next_bus_1_vehicle`: Vehicle number of the first bus.
  - `next_bus_2_time`: Arrival time of the second bus (if available).
  - `next_bus_2_satellite`: GPS tracking status for the second bus.
  - `next_bus_2_accessible`: Indicates whether the second bus is wheelchair accessible.
  - `next_bus_2_vehicle`: Vehicle number of the second bus.

## Contributing

If you have any improvements, additional information, or notice any issues with the TPER Tracker, we'd love to hear from you! Feel free to open a pull request with your suggestions or details.

If you encounter any problems with the integration or believe something isn’t working as expected, please provide all relevant information in an issue, including the file from **Download diagnostics** on the integration page. Your contributions, suggestions, and feedback are always welcome and appreciated!

## Disclaimer

This integration is **not affiliated** with **TPER**. It uses publicly available data from TPER through the **Hello Bus** service and the [TPER open data](https://solweb.tper.it/web/tools/open-data/open-data.aspx) portal (CC BY 3.0 IT) to provide real-time bus information. The accuracy and availability of the data depend on TPER, and any issues with the service are outside the control of this integration.
