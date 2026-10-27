# Changelog

All notable changes to weewx-ecowitt_console_emulator are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
version numbers follow the rules in [VERSIONING.md](VERSIONING.md).

## [Released]

## [2.0.0-custom]

weewx-ecowitt-console-custom: 2.0.0 with a Solar page.

### Added
- A **Solar** toolbar page with weewx-divumwx's SolarAssistant power-flow diagram
  (PV, grid, inverter, battery, essential and non-essential loads, animated flows),
  today's energy totals and details, in the dashboard's themes, with a compact form
  for phones. It reads weewx-divumwx's `solar_data.json` and `archive.json` (from the
  dashboard's folder or DivumWX's `jsondata`), every 10 seconds while open; nothing
  is added to WeeWX. See "Solar page" in the README.
- The Solar page stays open until closed and reopens after a page reload;
  `…/console/#solar` opens it directly.

### Changed
- The version tag on the page's scripts and styles covers every file in `js/` and
  `css/`, so browsers fetch new copies of any of them after an update.

## [2.0.0]

### Added
- Live data can come from the gateway's own MQTT messages. Gateways and consoles with
  MQTT (GW1200, GW2000, GW3000 ...) publish their readings to a broker every 8 seconds
  or more; with `[EcowittConsoleEmulator] source = mqtt` and an `[[MQTT]]` section
  (broker, port, topic, user name, password, optional TLS), the skin's live service
  subscribes to the gateway's topic and writes `live.json` from each message. The
  readings are renamed to weewx-EcowittGateway's fields and converted to METRICWX; the
  pass key and device details are left out. Dew point and feels-like are worked out
  when the gateway doesn't send them. `source = both` keeps loop packets too (for
  signal strengths and the WN20 battery), with MQTT readings on top while
  they are fresh. The subscriber is built in, so nothing else needs installing.
- The installer offers **mqtt** as a live-data source (also without
  weewx-EcowittGateway) and asks for the broker and topic; for unattended installs,
  `--live=mqtt --mqtt-host=... --mqtt-port=... --mqtt-topic=... --mqtt-user=...
  --mqtt-password=...`.
- The green live-data icon pulses briefly each time new live data arrives (a soft
  glow instead where the device asks for reduced motion).
- The header shows where live data comes from, beside the live-data icon: **Loop**,
  **MQTT** or **Loop + MQTT** (dimmed while live data isn't arriving); Settings shows
  the same after the live file's name. `live.json` records which sources each write
  was made from (`sources`), so with `source = both` the tag drops to **Loop** if
  MQTT stops.
- **Forecast** button and panel: a 7-day, hour-by-hour forecast for the station's
  position from Open-Meteo (free, no key; fetched by the browser and kept for 30
  minutes). A card for each day; for the chosen day its conditions, sunrise and
  sunset, high and low, strongest gust, rain and highest UV index; a table of every
  hour (temperature, feels like, humidity, gust and direction, rain and its chance,
  UV index) with sunrise and sunset marked; and charts of the same, read like the
  Charts panel. Uses the dashboard's own icons (with a new snow icon), theme and
  display units. `forecast` and `forecast_url` in `skin.conf`.
- **Records** button and panel: highest and lowest temperature, feels like, dew point,
  humidity, barometer, and highest gust, solar radiation, UV index, rain rate and
  wettest day (for each rain gauge), today, this month, this year and all time, each
  with when it happened. Worked out from the daily summaries, so it takes milliseconds
  even with years of data, and added to `ecowitt.json`. `records` in `skin.conf`.
- The new text is in all 29 translations.
- The installer can name your sensors: it lists the temperature/humidity channels and
  the soil, leaf, leak and PM sensors with readings in the database, and asks for a name
  for each (Porch, Attic, Freezer ...), shown on the dashboard instead of "WN31 CH1".
  Naming a WN34 probe adds it to the channels the CH button steps through. Reinstalling
  offers the current names; for unattended installs, `--label=FIELD=NAME`. The names go
  in weewx.conf (`[[[[Channels]]]]`, `[[[[SoilChannels]]]]` ...).

### Changed
- The station title is now the largest text in the header in every layout, centred
  between the status chips and the clock; the clock is a little smaller and the date
  dimmer. Long names are made smaller to fit before they are cut short.

### Fixed
- The WS68/WH68 anemometer showed a low battery whenever its battery came as a voltage
  (weewx-EcowittGateway over the gateway's TCP API, or MQTT): it was read as a flag, so
  any reading other than 0, such as a healthy 1.88 V, counted as low. It is now read
  either way: 0/1 as a flag, anything else as volts, low below 1.2 V (one AA cell). The
  WS68's own voltage (`ws68_batt`) is shown when the driver gives it. The WH40 rain gauge
  had the same problem with its 0–5 level and is read the same way (low below 1.2 V).
  Battery kinds can now be joined by `|` (`binary|volt:1.2`, `level|volt:1.2`) and a
  battery field can list fields to try in turn (`ws68_batt|wh68_batt`).
- MQTT: the WH68 and WH40 batteries are now passed on (they were left out).
- The WS68/WH68 anemometer showed its battery as 5.00 V when its voltage (`ws68_batt`)
  wasn't in the live data, for example with weewx-EcowittGateway 1.1.1, or with a WS68
  and a WS80 both paired. The panel then fell back to `wh68_batt`, which over the gateway's
  HTTP API is a level 0–5 (5 = full), not a flag, and read the 5 as volts. Its battery
  kind is now `binary|level|volt:1.2`, so that level shows as 5/5. A real voltage, from
  `ws68_batt` (weewx-EcowittGateway 1.2.0 or later) or the TCP API, still shows in volts.

## [1.1.2] – 2026-10-20

### Fixed
- Every report could stop with `No such table archive` (and `Cannot get columns of
  table archive, and no schema specified`) when the skin's own database couldn't be
  created at start-up: WeeWX was left with an empty database file. This happened when
  the main database has a column whose name differs from one the skin adds only in
  capital letters (for example `FeelsLike` and `feelslike`), which SQLite and MySQL
  treat as the same name. Such columns are now recognised, and if the database still
  can't be made with the main database's columns, it is made with the standard
  schema (wview_extended plus the driver fields) instead, with an error in the log
  saying why. An installation already showing the error repairs itself at the next
  start of WeeWX; nothing needs to be done by hand.

## [1.1.1] – 2026-10-15

### Added
- Square layout for near-square screens such as Apple HomeView (1088 × 1088), chosen
  automatically when the screen's width:height is between 0.8 and 1.25, and under
  Settings → Layout. It fills the whole screen, widening up to 5:4 like landscape.
  "Square" is in all 30 languages.
- Language, units, theme and layout can be set in the page address
  (`?lang=fr&units=metric&theme=auto&layout=landscape`), for screens where Settings
  can't be used or isn't kept, such as a page cast to a Google Nest Hub. The README
  explains casting the dashboard to a Nest Hub or Nest Hub Max with CATT.

### Changed
- New Auto theme, now the default: Light from sunrise to sunset and Black from sunset
  to sunrise, switching by itself at the station's sunrise and sunset. The themes it
  uses are set by `theme_day` and `theme_night` in `skin.conf`. A device that already
  chose a theme keeps it; Settings → Theme → Auto (or the theme button) switches to it.

### Fixed
- Every layout now fills the whole screen with no empty bands at the top and bottom
  or at the sides: landscape grows taller on 4:3 and 5:4 screens, portrait grows
  wider on tablets (iPad, Android) or taller on very tall screens, and square grows
  taller on screens a little taller than square. The extra space goes between the
  panels; the gauges keep their shape. (Phones scroll, as before.)
- On iPad (and iPhone) a blank strip could be left under the toolbar: Safari measures
  "100%" height with its toolbars shown, and a home-screen app leaves out the status
  bar. The dashboard's full-screen box is now pinned to the screen's edges instead,
  and any space it still doesn't reach under the toolbar is drawn in the toolbar's
  colour.
- On screens wider than 16:10 the landscape dashboard now fills the whole width (up to
  2.5:1) instead of leaving bands at the sides: Amazon Echo Show in the Silk browser
  (Show 5, 8, 10, 15, 21), 16:9 tablets, and browsers whose address bar shortens the
  screen. The extra width goes between the panels; the gauges keep their shape.
- The dashboard could sit at the left with empty space to the right in browsers on
  older engines (Silk on some Echo Shows): the full-screen box no longer relies on CSS
  `inset`, the screen size is measured from that box, and the page fits itself again
  after loading and whenever the visible area changes, also when the browser doesn't
  report it. Settings shows the layout and screen size the page sees.

## [1.1.0] – 2026-10-14

### Added
- Indoor temperature chart on every Charts tab (`inTemp`, mappable in `[[FieldMap]]`):
  the average on the Day, Week and Month tabs, the daily high and low on the Year tab.
- The installer asks whether to show VPD (vapour pressure deficit): yes shows the VPD
  reading and its chart as before, no leaves both out. `--vpd=y|n` answers it for
  unattended installs; the answer is stored as `show_vpd` and offered again on
  reinstall. Existing installations keep VPD.
- "Indoor temperature" in all 30 languages.

### Changed
- The readings row spreads its readings evenly whatever their number (six when VPD
  is not shown).
- Installing removes the calendar-year chart files (`chart_2025.json` ...), so WeeWX
  writes them again with the new charts; before, a year's file was never rewritten.
- The VPD chart is always in the chart files and left out by the page when VPD is
  not shown, so changing `show_vpd` takes effect at once on every tab and year.

### Fixed
- With one rain gauge, long words in some languages ran into the rain totals or out
  of the panel: the rate line and the total labels are now fitted to their space,
  and the Czech, Finnish, Hungarian, Norwegian and Tamil labels there are shorter.
- Labels in the readings row could be cut short instead of going onto two lines.

## [1.0.0] – 2026-10-07

First public release. A WeeWX 5 skin and extension that turns a tablet, phone or
browser into a full-screen emulation of the Ecowitt WH2560/HP2560 console.
Released under the GNU General Public License, version 3 or later (see LICENSE).

### Dashboard
- Console-style layout: outdoor temperature ring, wind dial, a temperature/humidity
  channel pair (Indoor and WN31 CH1–8), soil moisture and leaf wetness, lightning,
  leak indicators, PM2.5 and CO₂, barometer with 3-hour trend and pressure-tendency
  forecast, sun arc with a moon track, moon phase, and a readings row that includes
  feels-like, dew point, VPD (kPa), 10-minute average wind, max daily gust and Beaufort.
- Wind gauge with a blue arrow for the current direction and a grey arrow for the
  10-minute average direction.
- Rain section for a tipping gauge, a piezo gauge or both, with daily, rate, event,
  hourly, weekly, monthly and yearly totals.
- Signal bars next to each reading. A battery icon appears only when a battery is low.
- Three layouts chosen from the screen's shape: landscape 1280 × 800, portrait
  800 × 1518 and phone 540 wide. Settings → Layout can force one of them.
- Three themes: Navy (console), Black (OLED / night) and Light.
- All times are always shown in the station's time zone, whatever the time zone of
  the viewing device. The zone is read from the WeeWX machine and can be set in
  `skin.conf` (`timezone`) if that comes out wrong.

### Charts
- Full-screen Day, Week, Month and Year charts drawn in the browser, following the
  theme and display units, with tooltips by mouse or touch.
- Temperature, humidity, VPD, wind, wind direction (Day tab), rain, barometer,
  solar radiation and UV.
- One rain chart with a separate column per gauge in each interval (tipping blue,
  piezo violet). The tooltip shows both values and the difference, and the legend
  shows the same period totals as the rain table.
- The Year tab shows the last 12 calendar months, or any calendar year in the skin's
  database (1 January to 31 December), chosen from a list. Each year is a separate
  file (`chart_2025.json` ...); past years are written once, the current year at most
  once an hour.

### Panels
- Windy radar centred on the station, in a panel over the dashboard or as a link.
- Sensors panel with battery and signal for every sensor that reports them.
- Settings: language, units, layout, theme, 12/24-hour clock, seconds, keep screen awake,
  full screen on touch, and data status.
- Every panel opens inside the dashboard, so the page never leaves full screen.

### Languages
- Everything on the dashboard can be shown in 30 languages, the same as weewx-divumwx:
  Arabic, Basque, Breton, Catalan, Chinese (simplified), Czech, Danish, Dutch, English,
  English (US), Finnish, French, German, Greek, Hindi, Hungarian, Icelandic, Italian,
  Japanese, Norwegian, Polish, Portuguese, Spanish, Swedish, Tamil, Thai, Turkish,
  Ukrainian, Urdu and Welsh.
- Chosen under Settings → Language, with a default set by `language` in `skin.conf`.
  The choice is shared with weewx-divumwx through the `dashboardLanguage` browser
  setting when both are served from the same web server.
- Day and month names follow the language. Where weewx-divumwx already translates
  the same text, its wording is used.
- Labels that would not fit their place in a language are made smaller, or put on two
  lines, to fit. In Arabic and Urdu each label reads right to left.

### Units
- Data feeds are always written in METRICWX and converted in the browser to the
  DivumWX presets: uk, us, metric, scandi, canada and icao.
- The unit choice is shared with weewx-divumwx through the `dashboardUnitSystem`
  browser setting when both are served from the same web server.

### Data
- The skin keeps its own database (`ecowitt_console_emulator.sdb`, binding
  `ecce_binding`) and never changes the station's main database.
- The skin's database is created only if missing, with the main database's schema
  plus extra Ecowitt fields. It is filled with history from the main database
  (400 days by default), then gaps are filled at each start and every new archive
  record is written to it.
- Piezo rain history is read from `p_rain` and from `hail`, so records copied from
  the main database keep their piezo rain.
- Live data every few seconds from the skin's own `live.json`, or from
  weewx-EcowittGateway's `ecwLoop.json` when that driver is installed and chosen.
- Missing driver fields are worked out from the archive: feels-like, 10-minute wind
  direction, max daily gust, VPD and period rain totals.

### Installation
- `weectl extension install` installer that asks which rain sensor(s) the station
  has and, only when weewx-EcowittGateway is installed, where live data comes from.
- Unattended installs with `--yes --rain=tipping|piezo|both --live=driver|skin`.
- weewx-EcowittGateway is optional; the skin works with any driver for an Ecowitt
  gateway or console.

[Unreleased]: https://github.com/Millardiang/weewx-ecowitt_console_emulator/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/Millardiang/weewx-ecowitt_console_emulator/compare/v1.1.2...v2.0.0
[1.1.2]: https://github.com/Millardiang/weewx-ecowitt_console_emulator/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/Millardiang/weewx-ecowitt_console_emulator/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/Millardiang/weewx-ecowitt_console_emulator/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Millardiang/weewx-ecowitt_console_emulator/releases/tag/v1.0.0

---

Copyright (c) Ian Millard 2026. GNU General Public License v3 or later; see [LICENSE](LICENSE).
