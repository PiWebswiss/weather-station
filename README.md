# Weather Station

This repository is the current project fork:

- Current repo: `https://github.com/PiWebswiss/weather-station`
- Original codebase: `https://github.com/fatihak/InkyPi`

The code in this project is based on the original InkyPi project and has been adapted here for this weather-station setup.

## Install

1. Clone the repository:

```bash
git clone https://github.com/PiWebswiss/weather-station.git
cd weather-station
```

2. Run the installer:

For Inky displays:

```bash
sudo bash install/install.sh
```

For Waveshare displays:

```bash
sudo bash install/install.sh -W <waveshare_model>
```

Example:

```bash
sudo bash install/install.sh -W epd7in3f
```

3. Reboot if the installer asks you to.

After install, the display will show a default welcome screen with:

- `http://<hostname>.local`
- `http://<ip-address>`

## Uninstall

```bash
sudo bash install/uninstall.sh
```

## Origin

The original upstream project is InkyPi by Fatih Ak:

- Upstream repository: `https://github.com/fatihak/InkyPi`
- License details: [LICENSE](./LICENSE)
