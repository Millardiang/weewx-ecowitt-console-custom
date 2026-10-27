# weewx-ecowitt-console-custom — an Ecowitt console emulator skin for WeeWX 5, with a Solar page
# Version 2.0.0-custom

This is [weewx-ecowitt_console_emulator](https://github.com/Millardiang/weewx-ecowitt_console_emulator)
2.0.0 with one addition: a **Solar** page on the toolbar showing
[weewx-divumwx](https://github.com/Millardiang/weewx-divumwx)'s SolarAssistant
power-flow diagram (PV, grid, inverter, battery, essential and non-essential loads),
live, in the dashboard's own themes. It reads the files weewx-divumwx already writes;
see [Solar page](#solar-page). Everything else is the same as 2.0.0, and it installs,
updates and is configured the same way (same extension name, skin, settings and
database).

A full-screen dashboard for a wall or desk tablet, an Amazon Echo Show, an Apple
HomeView or a Google Nest Hub, laid out like the Ecowitt WH2560 / HP2560 console, in a navy-blue palette: outdoor temperature
ring, wind dial, selectable temperature/humidity channel, soil moisture / leaf
wetness and lightning line, leak indicators, PM2.5 and CO₂, sun arc and moon
phase, rain (traditional or piezo), and barometer with 3-hour trend and a
pressure-tendency forecast (a moon replaces the sun between sunset and sunrise). The sky panel has a sun arc and, inside it, a moon track with moonrise/moonset times; the moon is worked out in the browser for the station's position, so WeeWX doesn't need the `ephem` package. The readings row includes VPD, always in kPa. Like the console, signal bars sit next to each
reading and a battery icon only appears when a battery is low.

It works with any WeeWX 5 station fed by an Ecowitt gateway or console, whatever
driver brings the data in. It needs no other extension: the skin has its own
database, its own live-data service and its own chart data.

If the **[weewx-EcowittGateway](https://github.com/Millardiang/weewx-ecowittGateway)**
driver/service happens to be installed, the skin also makes use of what it
provides: its `ecwLoop.json` live file, its `rain_source` setting, and the extra
fields it adds (10-minute wind direction, max daily gust, feels-like, the second
rain gauge in `p_rain`, sensor batteries and signal). Without it the skin uses
its own live file and works the extras out itself (see
[Fields](#fields-the-dashboard-uses)). Only the sensors you actually have are shown.

### Works on

Any device with a web browser that can reach your WeeWX web server. It fills the
whole screen of:

| Device | Browser | Layout |
|---|---|---|
| Tablets (Android, iPad) | Chrome, Safari, Fully Kiosk Browser … | Landscape or Portrait, as the tablet is held |
| Phones | any | Phone (one scrolling column), or Landscape when turned sideways |
| **Amazon Echo Show** 5, 8, 10, 15 and 21 | Silk ("Alexa, open Silk") | Landscape, made wider to fill the whole width of these wide screens below Silk's address bar |
| **Apple HomeView** (7-inch square, 1088 × 1088) | Safari | Square, made for its square screen, with the header clear of the rounded corners |
| **Google Nest Hub** (7-inch, 1024 × 600) and **Nest Hub Max** (10-inch, 1280 × 800) | none of its own: the page is cast to it (see [tips](#tablet-and-smart-display-tips)) | Landscape, filling the whole screen |
| Computers, TVs and other screens | any | whichever fits the window's shape |

The layout is chosen from the shape of the screen, so no setting is needed; see
[Layouts](#layouts) and [Tablet and smart-display tips](#tablet-and-smart-display-tips).

### Layouts

The page picks a layout from the shape of the screen and switches when the
device is rotated. Each layout takes the exact shape of the screen, so the
dashboard fills it with no empty bands at the sides or at the top and bottom: the
extra width or height goes into the gaps between the panels, and the gauges keep
their round shape.

| Layout | Used when | Design size | Arrangement |
|---|---|---|---|
| Landscape | wider than tall | 1280 × 800, stretched to the screen's shape: wider up to 2.5:1 (Echo Show, 16:9), or taller (4:3, 5:4) | the console layout |
| Portrait | tablet held upright (600 px wide or more) | 800 × 1518, stretched to the screen's shape (wider on most tablets), no scrolling | outdoor and wind gauges side by side, readings, sun/moon, channel rings, rain, barometer |
| Square | near-square screens (width:height 0.8–1.25), e.g. Apple HomeView | 1040 × 1070, stretched to the screen's shape (wider up to 5:4, or taller) | header; outdoor and wind gauges with lightning, soil and air quality beside them; readings; channel rings beside rain and barometer; sun/moon; toolbar |
| Phone | narrow screens (under 600 px) | 540 wide, fitted to the width, scrolls | one column; readings in 3 × 2; header on two rows; a narrower sun/moon drawing with larger text |

**Settings → Layout** can force one of them (Auto, Landscape, Portrait, Square, Phone);
the choice is kept in the browser. "Add to Home screen" apps can rotate freely.

## What's in the package

| Part | What it does |
|---|---|
| `skins/EcowittConsoleEmulator` | The skin: the dashboard page, chart data (day/week/month/year), CSS/JS, translations (`lang/`), manifest for "Add to home screen" |
| Its own database | `ecowitt_console_emulator.sdb` (binding `ecce_binding`), kept by the `EcowittConsoleEmulatorArchive` service: the same schema as the station's main database plus extra fields for Ecowitt sensors. See [The skin's database](#the-skins-database) |
| `bin/user/ecowitt_console_emulator.py` | **Search-list extension** that builds the dashboard data (today's highs/lows, rain totals for hour/day/week/month/year/event, 10-min average wind, 3 h pressure trend, feels-like, lightning summary) and the **live service** that writes `live.json` |
| `skins/EcowittConsoleEmulator/js/solar-flow.js`, `css/solar-flow.css` | The Solar page (SolarAssistant power flow from weewx-divumwx's files). See [Solar page](#solar-page) |
| `install.py` | Installer for `weectl extension install` |

### Two data feeds

* `ecowitt.json` – written by WeeWX every archive interval (and embedded in
  `index.html`). Highs/lows, rain totals, trends, almanac.
* **Live data, every few seconds** – the skin's `EcowittConsoleEmulatorLive` service
  writes **`live.json`**, from one of:
  * **WeeWX loop packets**, whatever the driver (the default);
  * **the gateway's own MQTT messages** – GW1200, GW2000, GW3000 and other
    gateways and consoles with MQTT can publish their readings to a broker
    themselves; the service subscribes to the gateway's topic (see
    [Live data from the gateway's MQTT](#live-data-from-the-gateways-mqtt));
  * **weewx-EcowittGateway's `ecwLoop.json`** (its `[[loop_json]]` option), if
    that driver is installed; the skin's service is then switched off.

  Either way the browser converts the units. Live data is the only source of
  **battery and signal** levels, since those aren't archived.

The page uses live values while they are fresh and falls back to the archive
otherwise. The Wi-Fi icon in the header shows which: green = live, yellow =
archive only, red = stale. While it is green it pulses briefly each time new live
data arrives (a soft glow only, if the device is set to reduce motion). The tag beside it shows where live data is coming
from: **Loop** (WeeWX loop packets, or weewx-EcowittGateway's `ecwLoop.json`),
**MQTT** (the gateway's own messages) or **Loop + MQTT** (`source = both`). With
`source = both` it shows what the latest `live.json` was actually made from, so if
MQTT stops it changes to **Loop**. While live data isn't arriving, the tag is
dimmed and shows the source that is set up. Settings shows the same.

## Requirements

* WeeWX 5.4 or later, with any driver for an Ecowitt gateway or console
* Nothing else. weewx-EcowittGateway is optional: if it is already installed,
  the installer reads its settings and can use its live file.
* For live updates the tablet must load the page from a web server that serves
  WeeWX's `public_html` directly (e.g. nginx/Apache on the WeeWX machine).
* A browser on the display: any current browser on a tablet, phone or computer;
  Silk on an Amazon Echo Show; Safari on an Apple HomeView. A Google Nest Hub has
  no browser of its own: the page is cast to it from another machine on the same
  network (e.g. the WeeWX machine) with the free CATT tool.

### Fields the dashboard uses

The standard WeeWX fields (`outTemp`, `outHumidity`, `dewpoint`, `windSpeed`,
`windDir`, `windGust`, `rain`, `rainRate`, `barometer`, `pressure`, `inTemp`,
`inHumidity`, `radiation`, `UV`, `extraTemp1–8`, `extraHumid1–8`, `soilMoist1–4`,
`leafWet1–2`, `pm2_5`, `co2`, `lightning_strike_count`, `hail`) are enough for the
dashboard. The names below are the ones weewx-EcowittGateway uses; another driver
may use other names, which `[[FieldMap]]` in `skin.conf` maps. When a field is
missing the dashboard works it out or leaves it out:

* feels like – worked out from temperature, humidity and wind
* 10-minute wind direction – the vector average of the last 10 minutes of the archive
* max daily gust – the highest gust in today's archive
* VPD – worked out from temperature and humidity
* period rain totals – summed from the archive
* piezo gauge – `hail` when `p_rain` isn't there
* battery and signal – shown only for sensors whose fields are found

| Dashboard | Fields (weewx-EcowittGateway names) |
|---|---|
| Outdoor / feels like / dew point | `outTemp`, `outHumidity`, `feelslike`, `dewpoint` |
| Wind, 10-min direction, max daily gust | `windSpeed`, `windDir`, `windGust`, `windDir10`, `maxdailygust` |
| Channel rings | `inTemp`/`inHumidity` (WH25), `extraTemp1–8`/`extraHumid1–8` (WN31) |
| Soil / leaf | `soilMoist1–16` (WH51), `leafWet1–8` (WN35) |
| Leak, PM2.5, CO₂ | `leak_1–4` (WH55), `pm25_1–4` (WH41/43), `pm2_5` and `co2` (WH45) |
| Lightning | `lightning_dist`, `lightning_disturber_count` (last strike time), `lightningcount` (today); archive `lightning_strike_count` |
| Tipping gauge | `rain`, `rainRate`, `eventRain`, `hourRain`, `dayRain`, `weekRain`, `monthRain`, `yearRain` |
| Piezo gauge | `p_rain` (or `hail`, which the standard database archives), `p_rainrate`, `erain_piezo`, `hrain_piezo`, `drain_piezo`, `wrain_piezo`, `mrain_piezo`, `yrain_piezo` |
| Batteries / signal | weewx-EcowittGateway's names (other drivers: list yours in `[[Sensors]]`), e.g. `ws90_batt`, `wh40_batt`, `batteryStatus1`, `soilMoistBatt1`, `leafWetBatt1`, `lightning_Batt`, `co2_Batt`, `leak_Batt1`, `pm25_Batt1`, with `<sensor>_sig` / `<sensor>_ch<n>_sig` |

When weewx-EcowittGateway is set to `rain_source = piezo`, `rain`/`rainRate`
hold the piezo gauge, and the dashboard treats them that way.

## Install

```bash
weectl extension install https://github.com/Millardiang/weewx-ecowitt_console_emulator/archive/refs/heads/main.zip
sudo systemctl restart weewx
```

The installer asks which rain sensor(s) the station has:

```
Which rain sensor does this station have?
  tipping - traditional tipping-bucket gauge (WH40, WS69, WN20 ...)
  piezo   - piezoelectric haptic gauge (WS90, WS85 ...)
  both    - both; the rain section shows a column for each
Rain sensor (tipping/piezo/both) [tipping]:
```

The first letter is enough. With **both**, the rain section becomes a table with
a **Tipping** and a **Piezo** column (Daily, Rate, Event, Hourly, Weekly, Monthly,
Yearly), and the rain chart shows a column for each.

Then it asks whether to show VPD (vapour pressure deficit):

```
Show VPD (vapour pressure deficit, in kPa) on the dashboard and in the charts?
Show VPD (yes/no) [yes]:
```

**yes** shows the VPD reading (after Humidity) and the VPD chart; **no** leaves
both out, and the readings row spreads the others across the space.

Then it asks where live data comes from:

```
Where should the tablet get live (every few seconds) data from?
  driver - the driver's ecwLoop.json (its loop_json option, already on)
  skin   - this skin's own live.json, from WeeWX loop packets
  mqtt   - this skin's own live.json, from the gateway's own MQTT messages
Live data source (driver/skin/mqtt) [driver]:
```

(**driver** is only offered when weewx-EcowittGateway is installed; without it
the default is **skin**.) With **mqtt** it then asks for the broker's address and
port, the gateway's topic and, if the broker needs them, a user name and password
– see [Live data from the gateway's MQTT](#live-data-from-the-gateways-mqtt).

**If weewx-EcowittGateway is installed** (an `[EcowittGateway]` section in
weewx.conf), the rain question defaults to the driver's `rain_source`.

With **driver**, the skin reads the driver's `ecwLoop.json` and its own live
service is switched off. If the driver's `loop_json` is off, the installer turns
it on in the web folder (METRICWX units). If it's written somewhere the web
server can't reach (the `data`, `tmp` or a custom folder), the installer uses
the skin's own `live.json` instead. If you answer `both` to the rain question
but the driver only records one gauge, the installer says so.

For unattended installs, answer on the command line (`--live=driver` only
works when weewx-EcowittGateway is installed):

```bash
weectl extension install weewx-ecowitt_console_emulator.zip --yes --rain=both --vpd=y
weectl extension install weewx-ecowitt_console_emulator.zip --yes --rain=both --vpd=n --live=driver
weectl extension install weewx-ecowitt_console_emulator.zip --yes --rain=piezo --vpd=y --live=mqtt \
    --mqtt-host=192.168.1.20 --mqtt-topic=ecowitt/1C6920E3A8F3 --mqtt-user=weewx --mqtt-password=secret
```

The answers are stored in `weewx.conf` under
`[StdReport][[EcowittConsoleEmulatorReport]][[[Extras]]]` (`rain_sensors`, `show_vpd`, `live_url`).
Reinstalling offers your current answers as the defaults.

This adds (shown without weewx-EcowittGateway; with its `ecwLoop.json`,
`live_url = ../ecwLoop.json` and `enable = false`):

```ini
[StdReport]
    [[EcowittConsoleEmulatorReport]]
        skin = EcowittConsoleEmulator
        HTML_ROOT = public_html/console
        enable = true
        [[[Extras]]]
            rain_sensors = both
            show_vpd = true
            live_url = live.json

[EcowittConsoleEmulator]                # the skin's own live service
    enable = true              # false when weewx-EcowittGateway's ecwLoop.json is used instead
    report = EcowittConsoleEmulatorReport
    interval = 5
    filename = live.json
    source = loop              # loop, mqtt or both
    [[MQTT]]                   # only with source = mqtt or both
        host = 192.168.1.20
        port = 1883
        topic = ecowitt/1C6920E3A8F3
        username = weewx
        password = secret

[Engine]
    [[Services]]
        report_services = ..., user.ecowitt_console_emulator.EcowittConsoleEmulatorLive
```

Then open `http://<your-weewx-host>/weewx/console/` (or wherever your
`public_html` is served) on the tablet.

### Naming sensors

The temperature/humidity channels and the soil, leaf, leak and PM sensors can show
your own names (Porch, Attic, Freezer, Veg patch ...) instead of "WN31 CH1". At the
end of the install, the installer lists the ones with readings in the database in
the last 30 days and offers to name them:

```
The dashboard can show your own names for your sensors (Porch, Attic, Freezer ...)
instead of "WN31 CH1". Found: Indoor, WN31 CH1, WN31 CH2, WN34 CH1, WH51 CH1
Name them now (yes/no) [no]: y
Press Enter to keep the name shown in [brackets].
  Indoor temperature/humidity (inTemp) [Indoor]:
  WN31 temperature/humidity CH1 (extraTemp1) [WN31 CH1]: Porch
  WN31 temperature/humidity CH2 (extraTemp2) [WN31 CH2]: Attic
  WN34 temperature probe CH1 (soilTemp1), shown with the CH button if named [not shown]: Freezer
  WH51 soil moisture CH1 (soilMoist1) [WH51 CH1]: Veg patch
```

A WN34 probe isn't among the channels the **CH** button steps through unless you
name it. Install again at any time to change the names: the current ones are offered
as the defaults. For unattended installs, give `--label=FIELD=NAME` once per sensor:

```bash
weectl extension install weewx-ecowitt_console_emulator.zip --yes \
    --label=extraTemp1=Porch --label=extraTemp2=Attic --label=soilTemp1=Freezer
```

The names are written to `weewx.conf` under
`[StdReport][[EcowittConsoleEmulatorReport]][[[Extras]]]`, in `[[[[Channels]]]]`,
`[[[[SoilChannels]]]]`, `[[[[LeafChannels]]]]`, `[[[[LeakChannels]]]]` and
`[[[[PMChannels]]]]`, where they can also be edited by hand
(`name = temperature field, humidity field, sensor id` for channels,
`name = field, sensor id` for the others). A new section lists every sensor of its
kind, so ones you add later still appear; a section you've already set up is edited
in place, keeping its order, any entries you added and any you left out. Restart
WeeWX after editing by hand.

### Live data from the gateway's MQTT

Ecowitt gateways and consoles with MQTT (GW1200, GW2000 and GW3000 so far, with
recent firmware) can publish their readings to an MQTT broker such as Mosquitto
themselves, as often as every 8 seconds. The skin can take its live data from those messages:

1. In the gateway's web page (or the WS View Plus app), under **MQTT**, enter the
   broker's address, port (usually 1883), a topic (e.g. `ecowitt/<MAC>`), the
   broker's user name and password if it has them, and how often to publish.
   The gateway can't use TLS, so this must be a plain (unencrypted) listener.
2. Answer **mqtt** to the installer's live-data question, or set by hand in
   `weewx.conf`:

   ```ini
   [EcowittConsoleEmulator]
       enable = true
       source = mqtt
       [[MQTT]]
           host = 192.168.1.20       # the broker
           port = 1883
           topic = ecowitt/1C6920E3A8F3   # the gateway's topic; ecowitt/# takes any
           username = weewx          # leave out if the broker has no passwords
           password = secret
           # tls = true, ca_certs = /path/ca.pem   for a TLS listener (WeeWX can use one
           #                                       even though the gateway can't)
           keepalive = 60
   [StdReport]
       [[EcowittConsoleEmulatorReport]]
           [[[Extras]]]
               live_url = live.json
   ```

3. Restart WeeWX. The log shows
   `ecowitt_console_emulator: MQTT subscribed to ecowitt/... on 192.168.1.20:1883`,
   and Settings on the dashboard shows *Live data: OK, … s old (live.json · MQTT)*.

WeeWX itself subscribes, so the broker's password stays on the WeeWX machine and
the tablet still just reads `live.json`; no WebSocket listener is needed. Nothing
extra needs installing: the subscriber is built into the skin.

The gateway sends the same `key=value` readings it sends to a "Customized" upload
server (`tempf`, `baromrelin`, `rrain_piezo` ...), in US units. The skin renames
them to the fields weewx-EcowittGateway uses and writes them in METRICWX like the
rest of `live.json`. Its pass key and other device details are not written.
Dew point and feels-like are worked out when the gateway doesn't send them. Each
message replaces the previous one, so a sensor that goes quiet drops out.

Two things only loop packets have: **signal strengths** (MQTT carries none), and
the **WN20** battery, which the gateway sends in volts where the dashboard expects
a level. (The WH68 and WH40 batteries are read in volts or as the driver gives
them.) To keep those, use `source = both`: loop packets as
before, with the MQTT readings on top while they are fresh (`mqtt_stale`, default
120 seconds), so the faster MQTT values win and the loop fills in the rest.

### Full screen

Every panel (Charts, Radar, Sensors, Settings) opens over the whole screen inside
the dashboard, so the page never leaves full screen. Browsers only allow full
screen after a tap, so the first touch anywhere switches it on, and again if the
browser leaves it (Settings → "Full screen on touch" turns this off). Escape or ×
closes a panel. On an iPhone, which has no full-screen mode for web pages, use
Share → "Add to Home Screen".

### Tablet and smart-display tips

* **Android:** Chrome → ⋮ → *Add to Home screen* opens it full screen. For a
  permanent wall display, a kiosk browser (e.g. Fully Kiosk Browser) works well.
* **iPad:** Safari → Share → *Add to Home Screen*.
* **Amazon Echo Show:** say "Alexa, open Silk", then enter the dashboard's address
  (e.g. `http://192.168.1.10/weewx/console/`) and bookmark it. The dashboard fills
  the width of every Echo Show (5, 8, 10, 15, 21), below Silk's address bar; the
  extra width goes between the panels, and the gauges keep their shape. The first
  tap switches to full screen where Silk allows it.
* **Apple HomeView:** open the dashboard's address in Safari. Its square screen gets
  the Square layout, which fills the whole screen; the header keeps clear of the
  rounded corners.
* **Google Nest Hub / Nest Hub Max:** these have no browser you can open, so the
  dashboard is *cast* to them, here with [CATT](https://github.com/skorokithakis/catt)
  ("Cast All The Things") on the WeeWX machine or any computer on the same network:
  ```bash
  pip install catt
  catt -d "Kitchen display" cast_site "http://192.168.1.10/weewx/console/?lang=en&units=uk&theme=auto"
  ```
  (`-d` takes the Hub's name as shown in the Google Home app, or its IP address.)
  A cast page stops after about 10 minutes, so send it again regularly, e.g. every
  9 minutes from cron:
  ```
  */9 * * * * catt -d "Kitchen display" cast_site "http://192.168.1.10/weewx/console/?theme=auto"
  ```
  Home Assistant users can use the DashCast add-on or
  [ha-catt-fix](https://github.com/swiergot/ha-catt-fix) to keep it showing. The
  Hub may not keep settings chosen on the page between casts, so put them in the
  address (see [Options in the address](#options-in-the-address)).
* If a screen isn't filled as expected, Settings (⚙) shows the layout and the
  screen size the page sees (e.g. "Layout: Landscape · 960 × 430 px"), and
  Settings → Layout can choose a layout by hand.
* Settings (⚙) → *Keep screen awake* stops the screen dimming (Wake Lock API;
  needs HTTPS or `localhost` on most browsers).

## Using the dashboard

| Toolbar button | Action |
|---|---|
| Charts | Full-screen charts with Day, Week, Month and Year tabs. The Year tab has a list: the last 12 months, or any calendar year in the skin's database (1 January to 31 December). Charts: temperature, indoor temperature, humidity, VPD (kPa, unless turned off), wind, wind direction (day), rain, barometer, solar radiation, UV. Rain is one chart with a separate column for the tipping gauge (blue) and the piezo sensor (violet) in each hour, day or month and the difference in the tooltip. The legend gives each gauge's total for today, this week, this month or this year (by tab): the same figures as the rain table. The bars cover the chart's whole span (27 hours, 7 days, 31 days, 12 months). Every chart has a tooltip: hover with a mouse, or tap/drag on a touch screen. Drawn in the current theme and display units |
| Forecast | A 7-day forecast, hour by hour, for the station's position, from [Open-Meteo](https://open-meteo.com): a card for each day (conditions, high and low, rain and its chance), then for the chosen day its sunrise and sunset, high and low, strongest gust, rain and highest UV index, a table of every hour (temperature, feels like, humidity, gust and direction, rain and its chance, UV index, with sunrise and sunset marked between the hours), and charts of the same, read like the Charts panel. Drawn with the dashboard's own icons, in the current theme and display units. See [Forecast](#forecast) |
| Records | The highest and lowest readings **today**, **this month**, **this year** and **since the skin's database began**, each with when it happened: temperature, feels like, dew point, humidity, gust, barometer, solar radiation, UV index, and for each rain gauge the highest rain rate and the wettest day. All four periods side by side; one at a time (with tabs) on a phone. Updated with every archive record |
| Solar | The SolarAssistant power-flow diagram from weewx-divumwx, with today's energy totals. See [Solar page](#solar-page) |
| Theme | Auto (the default: Light from sunrise to sunset, Black from sunset to sunrise, switching by itself at the station's sunrise and sunset) → Navy (console) → Black (OLED / night) → Light. A short message shows which one is chosen |
| CH | Switches the second pair of rings between the temperature/humidity channels that are reporting: Indoor, then each WN31 (CH1–CH8). Greyed out when only one channel reports |
| Battery | Battery and signal of every sensor that reports them |
| Refresh | Reload data now |
| Settings | Language, units, layout, theme, 12/24 h clock, seconds, keep awake, full screen on touch, data status |

Tapping works too: the channel gauges cycle channels, the soil/leaf line cycles
through every soil-moisture and leaf-wetness channel, the PM2.5 readout cycles PM
sensors, the barometer reading switches between REL and ABS, with `rain_sensors = auto`
and both gauges reporting, the tag under the rain icon switches between them,
and the red battery icon in the header opens the sensor list.

On the wind gauge, the blue arrow is the current direction and the small grey
arrow is the 10-minute average direction.

All times (clock, date, sunrise/sunset, moonrise/moonset, chart axes) are shown in
the **station's** time zone, whatever the time zone of the tablet or phone viewing
the page.

### Forecast

The forecast comes from [Open-Meteo](https://open-meteo.com), a free weather
service that needs no account or key, for the station's latitude and longitude
(`[Station]` in weewx.conf). The tablet asks Open-Meteo itself, so it needs
internet access; WeeWX isn't involved. The forecast is kept for 30 minutes, then
fetched again the next time the panel opens. Open-Meteo's free service is for
non-commercial use, and its data is licensed CC BY 4.0, so the panel names it as
the source. For commercial use, take an Open-Meteo plan and set
`forecast_url = https://customer-api.open-meteo.com/v1/forecast?apikey=...`.

Rain in each hour is the amount expected in the hour up to that time (as Open-Meteo
gives it), with the chance of rain under it. Times are in the station's time zone.
The Forecast button is hidden if weewx.conf has no station position, or with
`forecast = false`.

### Solar page

The **Solar** button opens weewx-divumwx's SolarAssistant power-flow diagram: PV,
grid (import/export, connected or not), inverter, battery (charge %, charging or
discharging) and the essential and non-essential loads, with animated flows between
them, and below it today's energy (generated, used, grid import and export, battery
charged and discharged) and details (PV strings, battery volts, amps and
temperature, grid volts and frequency, inverter temperature and load). It updates
every 10 seconds while open. On a phone the diagram is drawn in a compact form.

It needs nothing in WeeWX and has no settings: it reads two files that
[weewx-divumwx](https://github.com/Millardiang/weewx-divumwx) (with its SolarAssistant
MQTT service) already writes:

| File | Used for |
|---|---|
| `solar_data.json` | SolarAssistant's readings (`solar_assistant/<device>/<name>/state` topics) |
| `archive.json` | `meta.solar_array_watts` (PV's share of the array's rating) and `meta.timezone` |

They are looked for, in this order, at these web addresses (relative to the
dashboard page), and the first that answers is used:
`./` (the dashboard's own folder), `../divumwx/jsondata/`, `/divumwx/jsondata/`,
`../../divumwx/jsondata/`, `/weewx/divumwx/jsondata/`. If yours are elsewhere,
copy or symlink them into the dashboard's folder, or add the address to `DIRS` at
the top of `js/solar-flow.js`. These are web addresses, not folders on the server
(`/var/www/html/...` won't work).

The status line above the diagram says when the readings were written, and what is
wrong if they can't be used: the addresses tried and why each failed (HTTP 404 = not
there, 403 = refused, "not JSON", network error); "not arriving" when
`solar_data.json` is more than 3 minutes old; or that it holds no readings when
weewx-divumwx isn't receiving anything from SolarAssistant.

Signs: grid power + importing / - exporting; battery power + charging / -
discharging. `load_power` is the total load, `load_power_essential` and
`load_power_non-essential` the two circuits.

The page stays open until it is closed (✕, Esc, a tap outside it, or another toolbar
page), and opens again after the page is reloaded, so a kiosk or cast screen that
reloads the page keeps showing it. `…/console/#solar` opens it directly.

## Configuration (`skins/EcowittConsoleEmulator/skin.conf`, `[Extras]`)

* `title` – the name at the top of the dashboard; empty = the station name (`location` in `[Station]` of weewx.conf)
* `language` – the default language (see [Languages](#languages-same-as-weewx-divumwx))
* `theme` – `auto` (default), `navy`, `black` or `light`; `theme_day` and `theme_night` – the themes `auto` uses by day and by night (`light` and `black`)
* `clock_24h`
* `timezone` – the station's time zone is read from the WeeWX machine; set it here
  (e.g. `timezone = Europe/Paris`) only if that comes out wrong
* `windy_radar`, `windy_mode`, `windy_zoom` – the **Radar** button at the top left shows
  Windy's radar centred on the station's `[Station]` latitude/longitude, with a
  marker on the station. `windy_mode = panel` (default) opens the map in a panel
  over the dashboard, so a full-screen tablet never leaves the page; the map's
  wind and temperature units follow the dashboard's unit preset, and the panel
  has an "Open in Windy" link. `windy_mode = link` opens windy.com instead.
  `windy_embed_url` / `windy_url` can be changed (`{lat}`, `{lon}`, `{zoom}`,
  `{wind}`, `{temp}` are filled in). The tablet needs internet access for this.
* `forecast` – `true` (default) or `false`: the **Forecast** button (see [Forecast](#forecast));
  `forecast_url` – Open-Meteo's address, to change only for a paid Open-Meteo plan
* `records` – `true` (default) or `false`: the **Records** button
* `rain_sensors` – `tipping`, `piezo`, `both` or `auto` (set by the installer); `baro_mode` – `REL` or `ABS`
* `show_vpd` – `true` or `false`: the VPD reading and chart (set by the installer)
* `[[Links]]` – chips at the top left, e.g. `Windy = https://www.windy.com/station/…`
* `[[FieldMap]]` – only needed if your driver names a field differently (or you've remapped it)
* `[[Channels]]` – which T&H channels the CH button cycles through, their names and
  sensor ids, e.g. `Greenhouse = extraTemp1, extraHumid1, wn31_ch1`
* `[[SoilChannels]]`, `[[LeafChannels]]`, `[[LeakChannels]]`, `[[PMChannels]]` – custom labels/fields
* `[[Sensors]]` – battery/signal list; `kind` is `binary` (0 = OK), `level` (0–5, 6 = DC) or `volt:<low volts>`,
  or two of them joined by `|` for a sensor whose battery can arrive either way (the first that fits the
  value is used: `binary` for 0 or 1, `level` for a whole number 0–6, otherwise volts). The WS68/WH68 uses
  `binary|level|volt:1.2` and the WH40 `level|volt:1.2`, because weewx-EcowittGateway gives them as a flag
  or level over the gateway's HTTP API but in volts over its TCP API. The battery field can also list
  fields to try in turn, e.g. `ws68_batt|wh68_batt`

### Options in the address

Language, units, theme and layout can also be set in the page's address, for
screens where Settings can't be used or isn't kept (a page cast to a Google Nest
Hub, a kiosk):

```
http://<your-weewx-host>/weewx/console/?lang=fr&units=metric&theme=auto&layout=landscape
```

| Option | Values |
|---|---|
| `lang` | a language code (see [Languages](#languages-same-as-weewx-divumwx)) |
| `units` | `uk`, `us`, `metric`, `scandi`, `canada`, `icao` |
| `theme` | `auto`, `navy`, `black`, `light` |
| `layout` | `auto`, `landscape`, `portrait`, `square`, `phone` |

They are applied as if chosen in Settings each time the page is opened with them;
values that aren't recognised are ignored.

### Languages (same as weewx-divumwx)

Everything on the dashboard can be shown in any of the 30 languages weewx-divumwx
has: labels, tooltips, messages, panels, charts, compass points, Beaufort names,
moon phases, and day and month names.

| Code | Language | Code | Language | Code | Language |
|---|---|---|---|---|---|
| `ar` | العربية (Arabic) | `eu` | Euskara (Basque) | `nl` | Nederlands (Dutch) |
| `br` | Brezhoneg (Breton) | `fi` | Suomi (Finnish) | `no` | Norsk (Norwegian) |
| `ca` | Català (Catalan) | `fr` | Français (French) | `pl` | Polski (Polish) |
| `cn` | 中文 (Chinese, simplified) | `gr` | Ελληνικά (Greek) | `pt` | Português (Portuguese) |
| `cy` | Cymraeg (Welsh) | `hi` | हिन्दी (Hindi) | `sv` | Svenska (Swedish) |
| `cz` | Čeština (Czech) | `hu` | Magyar (Hungarian) | `ta` | தமிழ் (Tamil) |
| `da` | Dansk (Danish) | `is` | Íslenska (Icelandic) | `th` | ไทย (Thai) |
| `de` | Deutsch (German) | `it` | Italiano (Italian) | `tr` | Türkçe (Turkish) |
| `en` | English | `ja` | 日本語 (Japanese) | `uk` | Українська (Ukrainian) |
| `en_US` | English (US) | `es` | Español (Spanish) | `ur` | اردو (Urdu) |

Pick one on the tablet under **Settings → Language**. Like the unit choice, it is
stored in the browser under DivumWX's key, `dashboardLanguage`, so if this skin and
DivumWX are served from the same web server they share one language. `language` in
`skin.conf` `[Extras]` sets the default for browsers that haven't chosen yet.

The translations are in `skins/EcowittConsoleEmulator/lang/<code>.json`, keyed by
the English text; English is built into the page. Where DivumWX already translates
the same text, its wording is used, so the two skins read alike. Names you set
yourself in `skin.conf` (channels, sensors, links) are shown as you wrote them.
In Arabic and Urdu the console layout stays the same, and each label, row and
message reads right to left. Labels that are longer in some languages are made a
little smaller, or put on two lines, so they fit their place on the console.

### Units (same model as weewx-divumwx)

Like weewx-divumwx, the data feeds are always written in **METRICWX** (°C, m/s,
mm, hPa, km), whatever `unit_system` your station or `weewx.conf` uses. The
browser converts them to the same display presets DivumWX offers (Beaufort is
shown as its own reading on the dashboard instead of as a unit choice; a
DivumWX `beaufort` choice shows metric units here):

| Preset | Temp | Wind | Pressure | Rain | Distance |
|---|---|---|---|---|---|
| `uk` (default) | °C | mph | hPa | mm | km |
| `us` | °F | mph | inHg | in | mi |
| `metric` | °C | km/h | hPa | mm | km |
| `scandi` | °C | m/s | hPa | mm | km |
| `canada` | °C | km/h | kPa | mm | km |
| `icao` | °C | kt | hPa | mm | NM |

Pick one on the tablet under **Settings → Units**. The choice is stored in the
browser under DivumWX's key, `dashboardUnitSystem`, and announced with the same
`unitsystemchange` event. If this skin and DivumWX are served from the
same web server, they share one unit choice. `unit_system` in `skin.conf`
`[Extras]` sets the default for browsers that haven't chosen yet.

The charts are drawn in the browser too, so they follow the unit preset and the theme.

## The skin's database

The skin keeps its own database, so it never changes the station's main one.

**Created only if it doesn't exist.** The installer checks for the
`[[ecce_binding]]` binding, its `[Databases]` entry and the database itself,
and leaves anything it finds untouched (it reports what it found). At each
start, `EcowittConsoleEmulatorArchive` checks again: an existing database is used as it
is; only a missing one is created.

**Same schema.** A new database gets the same columns and daily summaries as
the station's main database (`wx_binding`), read from that database itself,
so columns you've added are included. Added to that are the extra fields the
dashboard can use that the standard schema doesn't have (they stay empty if your
driver doesn't supply them): `feelslike`, `windDir10`,
`maxdailygust`, `p_rain`, `p_rainrate`, `lightning_dist`, `lightningcount`,
`soilMoist5–16`, `leafWet3–8`, `pm25_1–4` and `leak_1–4`. Set
`driver_fields = false` for an exact copy of the main schema. The database type
(SQLite or MySQL) also follows the main database.

**History.** A new database is filled from the main one, the last 400 days by
default (`backfill_days`, or `all`), with a bulk SQL copy: a year takes about a
second, plus a one-time daily-summary rebuild. On every later start, any gap
since its last record is filled the same way. From then on each archive record
is written to it as it arrives, extra fields included.

The charts' Year tab lists the calendar years this database holds. To chart every
year your station has recorded, set `backfill_days = all` before the skin's first
start (or delete `ecowitt_console_emulator.sdb` with WeeWX stopped, so it is built
again with all history).

```ini
[EcowittConsoleEmulator]
    data_binding = ecce_binding    # the skin's database
    source_binding = wx_binding     # the station's main database
    backfill_days = 400             # history copied into a new database ('all' for everything)
    driver_fields = true            # add the extra fields to a new database
```

The dashboard and the charts both read this database
(`data_binding = ecce_binding` in the report section). Uninstalling the skin
removes these settings but keeps the database file; reinstalling picks it up
again.

## Troubleshooting

* **Something new after an update doesn't appear** (e.g. the year list on the
  charts' Year tab) – restart WeeWX (`sudo systemctl restart weewx`): until then it
  keeps running the previous version of the skin's code, and the page's data
  (`ecowitt.json`) is still the old kind. The page's script, styles and
  translations are linked with a fingerprint of their contents, so browsers load
  the new copies as soon as WeeWX has rewritten the page.
* **Reports stop with `No such table archive`** (after `Cannot get columns of table
  archive, and no schema specified`) – the skin's own database exists but is empty,
  because it couldn't be created at start-up; the reason is in the log just after
  WeeWX starts (`ecowitt_console_emulator: could not prepare database ...`). Fixed in
  1.1.2: update and restart WeeWX, and the database is created again.
* **Wi-Fi icon yellow** – live data isn't arriving. With the skin's own
  `live.json`, check that `[EcowittConsoleEmulator] enable = true` and look for
  `ecowitt_console_emulator: ... writing live data to ...` in the log. With
  `source = mqtt`, look for `MQTT subscribed to ...`; an `MQTT ...` error says why
  it can't connect (wrong address, `not authorised`, ...). To see what the
  gateway sends, run `mosquitto_sub -h <broker> -t 'ecowitt/#' -v`: nothing there
  means the gateway's MQTT settings need checking, not WeeWX. With
  weewx-EcowittGateway's `ecwLoop.json`, check that the file exists and that
  `live_url` in weewx.conf points to it (relative to the dashboard page, e.g.
  `../ecwLoop.json`).
* **No batteries in Sensors** – battery fields only come from live data, and only
  under the names listed in `[[Sensors]]`. Add your driver's names there. With
  weewx-EcowittGateway, its `show_all_batt` option may help.
* **A sensor is missing** – it is hidden until it has a value. Check what your
  driver calls the field and add it to `[[FieldMap]]` or the relevant channel
  section.
* Turn on `debug = 1` in `weewx.conf` to see how long the data build takes.

## Changes and versions

See [CHANGELOG.md](CHANGELOG.md) for what changed in each release, and
[VERSIONING.md](VERSIONING.md) for how version numbers are chosen.

## Licence

Copyright (c) Ian Millard 2026

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. It is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; see the [GNU General Public License](LICENSE) for details.

The translations reuse wording from
[weewx-divumwx](https://github.com/Millardiang/weewx-divumwx), also GPLv3.

Ecowitt is a trademark of its owner; this project is not affiliated with
Ecowitt. All icons are original SVG drawings.
