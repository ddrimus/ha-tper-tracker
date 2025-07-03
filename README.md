# TPER Tracker

**Available languages:** [English](README.md) | [Italian](README.it.md)

A Home Assistant integration to track real-time bus arrivals from [TPER](https://www.tper.it/), the public transport provider serving Bologna and surrounding areas.

## Features

- 🚌 Real-time bus arrival times.
- 🔍 Search bus stops by name, address, or stop number.
- 📍 Monitor multiple bus lines per stop.
- 📡 GPS tracking status for buses.
- ♿ Wheelchair accessibility information.
- 🕐 Smart adaptive polling based on ETA.
- 🌐 Multi-language support (English & Italian).

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance.
2. Search for "TPER Tracker" and install it.
3. Restart Home Assistant.

### Manual Installation

1. Download the latest release from the [releases page](https://github.com/ddrimus/ha-tper-tracker/releases).
2. Extract the `tper_tracker` folder to your `custom_components` directory.
3. Restart Home Assistant.

## Configuration

1. Go to **Settings** → **Devices & Services**.
2. Click **Add Integration** and search for "TPER Tracker".
3. Enter a search term for your bus stop (name, address, or stop number).
4. Select your bus stop from the search results.
5. Choose which bus lines you want to monitor.
6. Click **Submit**.

The integration will create sensor entities for each selected bus line showing the next arrival time.

## Sensors

Each monitored bus line creates a sensor with the following information:

- **State**: The next bus arrival time (as a timestamp).

- **Attributes**:

  - `last_update`: Timestamp of when the data was last updated.
  - `line_id`: Identifier for the bus line.
  - `next_bus_1_time`: Arrival time of the first bus.
  - `next_bus_1_satellite`: GPS tracking status for the first bus.
  - `next_bus_1_accessible`: Indicates whether the first bus is wheelchair accessible.
  - `next_bus_2_time`: Arrival time of the second bus (if available).
  - `next_bus_2_satellite`: GPS tracking status for the second bus.
  - `next_bus_2_accessible`: Indicates whether the second bus is wheelchair accessible.

## Contributing

If you have any improvements, additional information, or notice any issues with the TPER Tracker, we'd love to hear from you! Feel free to open a pull request with your suggestions or details.

If you encounter any problems with the integration or believe something isn’t working as expected, please provide all relevant information in an issue. Your contributions, suggestions, and feedback are always welcome and appreciated!

## Disclaimer

This integration is **not affiliated** with **TPER** or **WebBus**. It uses publicly available data from TPER through the third-party **WebBus** ([https://webus.bo.it/](https://webus.bo.it/)) to provide real-time bus information. The accuracy and availability of the data depend on the WebBus API, and any issues with the service are outside the control of this integration.