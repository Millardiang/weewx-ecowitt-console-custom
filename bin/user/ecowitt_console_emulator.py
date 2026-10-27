#
#    EcowittConsoleEmulator (weewx-ecowitt_console_emulator) - a WeeWX 5 skin that emulates
#    the Ecowitt WH2560/HP2560 console as a full-screen dashboard
#
#    Copyright (c) Ian Millard 2026
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Support code for the EcowittConsoleEmulator skin.

Built around the weewx-EcowittGateway driver/service
(https://github.com/Millardiang/weewx-ecowittGateway): its WeeWX field names,
its battery/signal fields, its two rain gauges and its ecwLoop.json loop file.

EcowittConsoleEmulatorData
    Cheetah search list extension. Reads the archive database and builds one
    dictionary ($ecce) with everything the dashboard needs: current values,
    today's highs and lows, rain totals for each period and gauge, the 3-hour
    barometer trend, a pressure-tendency forecast and a lightning summary.
    Values are written in METRICWX (as weewx-divumwx does); the browser
    converts them for display.

EcowittConsoleEmulatorArchive
    Archive service that keeps the skin's own database (binding ecce_binding).
    At start-up it checks whether that database exists and creates it only if
    it doesn't, with the same schema as the station's main database plus the
    driver fields the dashboard uses. A new database is filled from the main
    one (bulk SQL copy), any gap since the last record is filled on each start,
    and every new archive record is written to it, driver fields included.

EcowittConsoleEmulatorLive
    Optional service, used when the driver's own ecwLoop.json is not used.
    Writes live.json from WeeWX loop packets, or from the gateway's own MQTT
    messages (source = mqtt), or both, using a small built-in MQTT subscriber.
"""

import glob
import hashlib
import json
import logging
import math
import os
import threading
import time

import weedb
import weewx
import weewx.manager
import weewx.units
import weewx.wxformulas
import weewx.xtypes
from weewx.cheetahgenerator import SearchList
from weewx.engine import StdService
from weeutil.weeutil import (TimeSpan, archiveDaySpan, archiveWeekSpan, archiveMonthSpan,
                             archiveRainYearSpan, startOfDay, to_bool, to_int, to_float)

log = logging.getLogger(__name__)

VERSION = "2.0.0-custom"
DRIVER_SECTION = 'EcowittGateway'
DRIVER_LEGACY_SECTION = 'EcowittHttp'

# Like weewx-divumwx, the data feeds are always written in METRICWX
# (degree_C, m/s, mm, mm/h, mbar = hPa, km).
FEED_UNIT_SYSTEM = weewx.METRICWX
FEED_CONVERTER = weewx.units.StdUnitConverters[FEED_UNIT_SYSTEM]


def _rng(fmt, n, start=1):
    return [fmt.format(i) for i in range(start, n + 1)]


# ----------------------------------------------------------------------------
# Unit groups of the driver's fields. The driver registers these itself when it
# is loaded (inside weewxd); this covers 'weectl report run' and keeps the
# driver's own definitions when they exist.
# ----------------------------------------------------------------------------
_DRIVER_GROUPS = {
    'group_rain': ['p_rain', 'hail', 'eventRain', 'hourRain', 'rain24', 'dayRain', 'weekRain', 'monthRain',
                   'yearRain', 'totalRain', 'erain_piezo', 'hrain_piezo', 'drain_piezo', 'wrain_piezo',
                   'mrain_piezo', 'yrain_piezo', 'rain24_piezo', 'train_piezo', 't_rain', 't_rainyear',
                   'p_rainyear'],
    'group_rainrate': ['p_rainrate', 'rrain_piezo', 'hailRate', 't_rainRate'],
    'group_temperature': ['feelslike', 'appTemp', 'bgt', 'wbgt', 'co2_Temp'] + _rng('extraTemp{}', 8) +
                         _rng('soilTemp{}', 8),
    'group_percent': _rng('extraHumid{}', 8) + _rng('soilMoist{}', 16) + _rng('leafWet{}', 8) + ['co2_Hum'],
    'group_speed2': ['maxdailygust'],
    'group_direction': ['windDir10'],
    'group_distance': ['lightning_dist', 'lightning_distance'],
    'group_concentration': ['pm2_5', 'pm10_0', 'pm1_0', 'pm4_0'] + _rng('pm25_{}', 4) + _rng('pm25_avg_24h_ch{}', 4),
    'group_fraction': ['co2', 'co2_24h', 'co2in', 'co2in_24h'],
    'group_count': ['lightningcount', 'lightning_strike_count'] + _rng('leak_{}', 4),
}
for _grp, _fields in _DRIVER_GROUPS.items():
    for _f in _fields:
        weewx.units.obs_group_dict.setdefault(_f, _grp)


# Logical names used by the dashboard -> the driver's WeeWX field names.
# Override any of these in skin.conf [Extras][[FieldMap]].
DEFAULT_FIELD_MAP = {
    'outTemp': 'outTemp', 'outHumidity': 'outHumidity', 'dewpoint': 'dewpoint', 'feelslike': 'feelslike',
    'inTemp': 'inTemp',
    'windSpeed': 'windSpeed', 'windDir': 'windDir', 'windGust': 'windGust',
    'windDir10': 'windDir10', 'maxdailygust': 'maxdailygust',
    'barometer': 'barometer', 'pressure': 'pressure',
    'radiation': 'radiation', 'UV': 'UV', 'co2': 'co2',
    'lightning_dist': 'lightning_dist',
    'lightning_time': 'lightning_disturber_count',   # the driver stores the last strike time here
    'lightningcount': 'lightningcount',              # strikes today (live)
    'lightning_strike_count': 'lightning_strike_count',  # strikes per archive period (summed)
    # tipping-bucket gauge (live totals from the gateway)
    'rain': 'rain', 'rainRate': 'rainRate', 'eventRain': 'eventRain', 'hourRain': 'hourRain',
    'dayRain': 'dayRain', 'weekRain': 'weekRain', 'monthRain': 'monthRain', 'yearRain': 'yearRain',
    # piezo gauge; the driver also copies p_rain to 'hail', which the standard database archives
    'p_rain': 'p_rain', 'hail': 'hail', 'p_rainrate': 'p_rainrate', 'hailRate': 'hailRate',
    'erain_piezo': 'erain_piezo', 'hrain_piezo': 'hrain_piezo', 'drain_piezo': 'drain_piezo',
    'wrain_piezo': 'wrain_piezo', 'mrain_piezo': 'mrain_piezo', 'yrain_piezo': 'yrain_piezo',
}


def _default_channels():
    """(temp field, humidity field, label, sensor id)"""
    chans = [('inTemp', 'inHumidity', 'Indoor', 'wh25')]
    chans += [('extraTemp%d' % i, 'extraHumid%d' % i, 'WN31 CH%d' % i, 'wn31_ch%d' % i) for i in range(1, 9)]
    return chans


def _default_sensors():
    """Battery and signal fields of each sensor, as named by weewx-EcowittGateway.

    (id, label, battery field, signal field, battery kind)
    kind: 'binary' (0 = OK, 1 = low), 'level' (0-5, 6 = DC, low <= 1),
          'volt:<low>' (a voltage, low below <low> volts), or two joined by '|' for a
          sensor the driver reports either way (the page uses the first that fits)
    battery field: 'a|b' tries a, then b
    """
    s = [('ws90', 'WS90 array', 'ws90_batt', 'ws90_sig', 'volt:2.4'),
         ('ws85', 'WS85 array', 'ws85_batt', 'ws85_sig', 'volt:2.4'),
         ('ws80', 'WS80 array', 'ws80_batt', 'ws80_sig', 'volt:2.4'),
         ('wh69', 'WS69 array', 'wh69_batt', 'wh69_sig', 'binary'),
         ('wh65', 'WH65 array', 'outTempBatteryStatus', None, 'binary'),
         # WS68/WH68: one AA cell (with solar). wh68_batt is a level 0-5 over the HTTP API (some
         # gateways send a 0/1 flag) and volts over the TCP API (and from MQTT); ws68_batt is its
         # voltage, given by weewx-EcowittGateway 1.2.0 or later when it is the wind array
         ('wh68', 'WS68/WH68 anemometer', 'ws68_batt|wh68_batt', 'wh68_sig', 'binary|level|volt:1.2'),
         # WH40: one AA cell; a level 0-5 over the HTTP API, volts over the TCP API
         ('wh40', 'WH40 rain gauge', 'wh40_batt', 'wh40_sig', 'level|volt:1.2'),
         ('wn20', 'WN20 rain gauge', 'wn20_batt', 'wn20_sig', 'level'),
         ('wh25', 'WH25/WN32P indoor', 'wh25_batt', 'wh25_sig', 'binary'),
         ('wh26', 'WH26/WN32 outdoor', 'wh26_batt', 'wh26_sig', 'binary'),
         ('wh57', 'WH57 lightning', 'lightning_Batt', 'wh57_sig', 'level'),
         ('wh45', 'WH45 CO2 / AQ', 'co2_Batt', 'wh45_sig', 'level'),
         ('wn38', 'WN38 black globe', 'wn38_batt', 'wn38_sig', 'level')]
    s += [('wn31_ch%d' % i, 'WN31 CH%d' % i, 'batteryStatus%d' % i, 'wh31_ch%d_sig' % i, 'binary') for i in range(1, 9)]
    s += [('wn34_ch%d' % i, 'WN34 CH%d' % i, 'soilTempBatt%d' % i, 'wn34_ch%d_sig' % i, 'volt:1.2') for i in range(1, 9)]
    s += [('wn35_ch%d' % i, 'WN35 CH%d' % i, 'leafWetBatt%d' % i, 'wn35_ch%d_sig' % i, 'volt:1.2') for i in range(1, 9)]
    s += [('wh41_ch%d' % i, 'WH41 PM CH%d' % i, 'pm25_Batt%d' % i, 'wh41_ch%d_sig' % i, 'level') for i in range(1, 5)]
    s += [('wh55_ch%d' % i, 'WH55 leak CH%d' % i, 'leak_Batt%d' % i, 'wh55_ch%d_sig' % i, 'level') for i in range(1, 5)]
    s += [('wh54_ch%d' % i, 'WH54 depth CH%d' % i, 'ldsbatt%d' % i, 'wh54_ch%d_sig' % i, 'volt:1.2') for i in range(1, 5)]
    s += [('wh51_ch%d' % i, 'WH51 CH%d' % i, 'soilMoistBatt%d' % i, 'wh51_ch%d_sig' % i, 'volt:1.2') for i in range(1, 17)]
    return s


def _as_list(v):
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v]
    return [x.strip() for x in str(v).split(',')]


def _round(v, nd=2):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, nd)


def driver_section(config_dict):
    """The weewx-EcowittGateway section of weewx.conf, or {}."""
    if not config_dict:
        return {}
    return config_dict.get(DRIVER_SECTION) or config_dict.get(DRIVER_LEGACY_SECTION) or {}


def driver_rain_source(config_dict):
    """The driver's rain_source (tipping, piezo or both), or None."""
    v = str(driver_section(config_dict).get('rain_source', '')).strip().lower()
    return v if v in ('tipping', 'piezo', 'both') else None


def _rain_sensors(extras, config_dict):
    v = str(extras.get('rain_sensors', '')).strip().lower()
    if v in ('tipping', 'piezo', 'both', 'auto'):
        return v
    return driver_rain_source(config_dict) or 'auto'


VPD_FIELD = '__vpd__'


def _month_start(ts, back=0):
    """Local midnight on the 1st of the month 'back' months before the one holding ts,
    so the year chart's monthly rain columns are calendar months."""
    tm = time.localtime(ts)
    y, m = tm.tm_year, tm.tm_mon - back
    while m < 1:
        m += 12
        y -= 1
    return int(time.mktime((y, m, 1, 0, 0, 0, 0, 0, -1)))


def _asset_version(skin_dir):
    """Version tag for the page's script, styles and translations: the release plus a
    fingerprint of the files themselves, so browsers fetch new copies after any update
    (not only when the release number changes)."""
    h = hashlib.sha1()
    try:
        files = sorted(glob.glob(os.path.join(skin_dir, 'js', '*.js'))) + sorted(glob.glob(os.path.join(skin_dir, 'css', '*.css')))
        files += sorted(glob.glob(os.path.join(skin_dir, 'lang', '*.json')))
        for f in files:
            with open(f, 'rb') as fh:
                h.update(fh.read())
    except (OSError, TypeError):
        return VERSION
    return '%s-%s' % (VERSION, h.hexdigest()[:8])


def _years(db):
    """Calendar years (newest first) that the database has records for."""
    try:
        first, last = db.firstGoodStamp(), db.lastGoodStamp()
    except Exception:
        return []
    if not first or not last:
        return []
    return list(range(time.localtime(last).tm_year, time.localtime(first).tm_year - 1, -1))


def vpd_kpa(t_c, rh):
    """Vapour pressure deficit in kPa from °C and %RH."""
    if t_c is None or rh is None:
        return None
    try:
        return 0.6108 * math.exp(17.27 * t_c / (t_c + 237.3)) * (1 - rh / 100.0)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def station_timezone(extras=None):
    """(IANA zone name or None, current UTC offset in seconds) of the WeeWX machine,
    unless skin.conf [Extras] timezone names one."""
    import datetime
    name = str((extras or {}).get('timezone', '') or '').strip() or None
    if not name:
        name = os.environ.get('TZ') or None
        if name and name.startswith(':'):
            name = name[1:]
    if not name:
        try:
            with open('/etc/timezone') as f:
                name = f.read().strip() or None
        except OSError:
            pass
    if not name:
        try:
            real = os.path.realpath('/etc/localtime')
            if 'zoneinfo/' in real:
                name = real.split('zoneinfo/', 1)[1]
        except OSError:
            pass
    if name and name.startswith('posix/'):
        name = name[6:]
    offset = datetime.datetime.now().astimezone().utcoffset()
    return name, int(offset.total_seconds()) if offset is not None else 0


def _live_source_label(config_dict):
    conf = (config_dict or {}).get('EcowittConsoleEmulator', {})
    return live_source(conf) if to_bool(conf.get('enable', False)) else None


def build_dashboard_config(skin_dict, config_dict=None):
    """The dashboard configuration: field names, channels, sensors and options."""
    extras = skin_dict.get('Extras', {})
    fmap = dict(DEFAULT_FIELD_MAP)
    fmap.update({k: str(v) for k, v in extras.get('FieldMap', {}).items()})

    chans = []
    cconf = extras.get('Channels', {})
    if cconf:
        for label, spec in cconf.items():
            parts = _as_list(spec) + [None, None, None]
            t = parts[0] if parts[0] not in (None, '', 'None') else None
            h = parts[1] if parts[1] not in (None, '', 'None') else None
            sid = parts[2] if parts[2] not in (None, '', 'None') else None
            chans.append((t, h, label, sid))
    else:
        chans = _default_channels()

    def numbered(section, defaults):
        """[(field, label, sensor id)] from a skin.conf section (label = field[, sensor]) or defaults."""
        conf = extras.get(section, {})
        if not conf:
            return defaults
        out = []
        for label, spec in conf.items():
            parts = _as_list(spec) + [None]
            out.append((parts[0], label, parts[1] or None))
        return out

    soil = numbered('SoilChannels', [('soilMoist%d' % i, 'WH51 CH%d' % i, 'wh51_ch%d' % i) for i in range(1, 17)])
    leaf = numbered('LeafChannels', [('leafWet%d' % i, 'WN35 CH%d' % i, 'wn35_ch%d' % i) for i in range(1, 9)])
    leak = numbered('LeakChannels', [('leak_%d' % i, '%d' % i, 'wh55_ch%d' % i) for i in range(1, 5)])
    pm = numbered('PMChannels', [('pm25_%d' % i, 'CH%d' % i, 'wh41_ch%d' % i) for i in range(1, 5)] +
                  [('pm2_5', 'WH45', 'wh45')])

    sensors = []
    sconf = extras.get('Sensors', {})
    if sconf:
        for label, spec in sconf.items():
            parts = _as_list(spec) + [None, None, None, None]
            sensors.append((parts[3] or label, label, parts[0] or None, parts[1] or None, parts[2] or 'binary'))
    else:
        sensors = _default_sensors()

    # Live fields the browser reads, per gauge
    rain_fields = {
        'trad': {k: fmap[v] for k, v in (('rate', 'rainRate'), ('event', 'eventRain'), ('hour', 'hourRain'),
                                         ('day', 'dayRain'), ('week', 'weekRain'), ('month', 'monthRain'),
                                         ('year', 'yearRain'))},
        'piezo': {k: fmap[v] for k, v in (('rate', 'p_rainrate'), ('event', 'erain_piezo'), ('hour', 'hrain_piezo'),
                                          ('day', 'drain_piezo'), ('week', 'wrain_piezo'), ('month', 'mrain_piezo'),
                                          ('year', 'yrain_piezo'))},
    }

    cfg = {
        'fields': fmap,
        'rainFields': rain_fields,
        'channels': [{'temp': t, 'hum': h, 'label': lab, 'sensor': sid} for t, h, lab, sid in chans],
        'soil': [{'field': f, 'label': lab, 'sensor': sid} for f, lab, sid in soil],
        'leaf': [{'field': f, 'label': lab, 'sensor': sid} for f, lab, sid in leaf],
        'leak': [{'field': f, 'label': lab, 'sensor': sid} for f, lab, sid in leak],
        'pm': [{'field': f, 'label': lab, 'sensor': sid} for f, lab, sid in pm],
        'sensors': [{'id': i, 'label': lab, 'batt': b, 'sig': s, 'kind': k} for i, lab, b, s, k in sensors],
        # The driver's ecwLoop.json (set by the installer), or the skin's own live.json
        'live_url': str(extras.get('live_url', 'live.json')),
        # what the skin's own live.json is written from (loop, mqtt, both), shown in Settings
        'live_source': _live_source_label(config_dict),
        'live_poll': to_int(extras.get('live_poll', 5)),
        # Forecast panel: Open-Meteo's 7-day hourly forecast for [Station] latitude/longitude
        'forecast': to_bool(extras.get('forecast', True)),
        'forecast_url': str(extras.get('forecast_url', 'https://api.open-meteo.com/v1/forecast')).strip(),
        # Records panel: highs and lows today, this month, this year and all time
        'records': to_bool(extras.get('records', True)),
        'archive_poll': to_int(extras.get('archive_poll', 60)),
        'live_stale': to_int(extras.get('live_stale', 120)),
        'theme': str(extras.get('theme', 'auto')),
        # the themes 'auto' uses between sunrise and sunset, and at night
        'theme_day': str(extras.get('theme_day', 'light')),
        'theme_night': str(extras.get('theme_night', 'black')),
        'title': str(extras.get('title', '')),
        'links': {k: str(v) for k, v in extras.get('Links', {}).items()},
        'clock_24h': to_bool(extras.get('clock_24h', True)),
        # Default language, as in weewx-divumwx (en, fr, de ...); the page's lang/<code>.json
        'language': str(extras.get('language', 'en')),
        # Default display units, as in weewx-divumwx (uk, us, metric, scandi, canada, icao, beaufort)
        'unit_system': str(extras.get('unit_system', 'uk')).lower(),
        # tipping, piezo or both; defaults to the driver's rain_source
        'rain_sensors': _rain_sensors(extras, config_dict),
        # VPD reading and chart (the installer asks; true unless turned off)
        'show_vpd': to_bool(extras.get('show_vpd', True)),
        'baro_mode': str(extras.get('baro_mode', 'REL')).upper(),
        # Windy radar button: {lat}, {lon} and {zoom} are filled in by the page
        'windy_radar': to_bool(extras.get('windy_radar', True)),
        'windy_zoom': to_int(extras.get('windy_zoom', 8)),
        'windy_url': str(extras.get('windy_url', 'https://www.windy.com/?radar,{lat},{lon},{zoom},d:picker')),
        # panel = Windy's radar map shown over the dashboard; link = open windy.com
        'windy_mode': str(extras.get('windy_mode', 'panel')).lower(),
        'windy_embed_url': str(extras.get('windy_embed_url',
            'https://embed.windy.com/embed2.html?lat={lat}&lon={lon}&detailLat={lat}&detailLon={lon}&zoom={zoom}'
            '&level=surface&overlay=radar&product=radar&menu=&message=true&marker=true&calendar=now&pressure='
            '&type=map&location=coordinates&detail=&metricWind={wind}&metricTemp={temp}&radarRange=-1')),
    }
    # Unit group of every field the browser may read from the live file, so it can
    # convert ecwLoop.json from whatever units the driver writes it in.
    live_fields = set(fmap.values())
    for blk in rain_fields.values():
        live_fields.update(blk.values())
    for c in cfg['channels']:
        live_fields.update(f for f in (c['temp'], c['hum']) if f)
    for key in ('soil', 'leaf', 'leak', 'pm'):
        live_fields.update(e['field'] for e in cfg[key] if e['field'])
    cfg['groups'] = {f: weewx.units.obs_group_dict.get(f) for f in sorted(live_fields)
                     if weewx.units.obs_group_dict.get(f)}
    return cfg


# ============================================================================
#                         Search list extension
# ============================================================================

class EcowittConsoleEmulatorData(SearchList):

    def __init__(self, generator):
        SearchList.__init__(self, generator)
        self.config_dict = getattr(generator, 'config_dict', None)
        self.cfg = build_dashboard_config(generator.skin_dict, self.config_dict)

    def _conv(self, vt, nd=2):
        if vt is None or vt[0] is None:
            return None
        try:
            return _round(FEED_CONVERTER.convert(vt)[0], nd)
        except Exception:
            return _round(vt[0], nd)

    def get_extension_list(self, timespan, db_lookup):
        db = db_lookup()
        # The dashboard data is built only when a template uses it ($ecce_json), so the
        # chart templates (and one file per calendar year) don't pay for it.
        cache = {}

        def data_json():
            if 'json' not in cache:
                cache['json'] = json.dumps(self._dashboard_data(timespan, db), separators=(',', ':'))
            return cache['json']

        def chart(period):
            stop = timespan.stop
            if period != 'calyear' and not db.getRecord(stop):
                stop = db.lastGoodStamp() or stop
            return self._chart_json(db, period, stop, timespan)
        return [{'ecce_json': data_json, 'ecce_jv': _jv, 'ecce_version': self._asset_version(), 'ecce_chart': chart}]

    def _asset_version(self):
        sd = self.generator.skin_dict
        skin_dir = os.path.join(self.generator.config_dict.get('WEEWX_ROOT', ''), sd.get('SKIN_ROOT', 'skins'), sd.get('skin', ''))
        return _asset_version(skin_dir)

    def _dashboard_data(self, timespan, db):
        t0 = time.time()
        keys = set(getattr(db, 'sqlkeys', []) or [])
        fm = self.cfg['fields']
        stop = timespan.stop
        rec = db.getRecord(stop) or {}
        if not rec:
            last = db.lastGoodStamp()
            if last:
                rec = db.getRecord(last) or {}
                stop = last
        interval = (rec.get('interval') or 5) * 60
        stn = self.generator.stn_info

        def cur_raw(field):
            return rec.get(field) if field else None

        def cur(field, nd=2):
            if not field or rec.get(field) is None:
                return None
            return self._conv(weewx.units.as_value_tuple(rec, field), nd)

        def agg(field, span, aggregate, nd=2):
            if not field or (keys and field not in keys):
                return None
            try:
                vt = weewx.xtypes.get_aggregate(field, span, aggregate, db)
            except (weewx.UnknownType, weewx.UnknownAggregation):
                return None
            except Exception as e:
                log.debug("ecowitt_console_emulator: aggregate %s(%s) failed: %s", aggregate, field, e)
                return None
            if aggregate in ('vecdir', 'maxtime', 'mintime', 'lasttime', 'maxsumtime', 'minsumtime'):
                return _round(vt[0], 1)
            return self._conv(vt, nd)

        day = archiveDaySpan(stop)
        week = archiveWeekSpan(stop, startOfWeek=getattr(stn, 'week_start', 6))
        month = archiveMonthSpan(stop)
        year = archiveRainYearSpan(stop, getattr(stn, 'rain_year_start', 1))
        last_hour = TimeSpan(stop - 3600, stop)
        spans = {'hour': last_hour, 'day': day, 'week': week, 'month': month, 'year': year}

        # --- outdoor --------------------------------------------------------
        feels = cur(fm['feelslike'], 1)
        if feels is None:
            feels = self._feels(rec, fm)
        out = {
            'temp': cur(fm['outTemp'], 1), 'hi': agg(fm['outTemp'], day, 'max', 1), 'lo': agg(fm['outTemp'], day, 'min', 1),
            'hum': cur(fm['outHumidity'], 0), 'humHi': agg(fm['outHumidity'], day, 'max', 0),
            'humLo': agg(fm['outHumidity'], day, 'min', 0),
            'dew': cur(fm['dewpoint'], 1), 'feels': feels,
        }

        # --- wind -----------------------------------------------------------
        ten = TimeSpan(stop - 600, stop)
        wind = {
            'speed': cur(fm['windSpeed'], 1), 'gust': cur(fm['windGust'], 1),
            'dir': _round(cur_raw(fm['windDir']), 0),
            'avg10': agg(fm['windSpeed'], ten, 'avg', 1), 'avg10dir': _round(cur_raw(fm['windDir10']), 0),
            'maxGust': agg(fm['windGust'], day, 'max', 1),
        }
        if wind['avg10dir'] is None:
            try:
                wind['avg10dir'] = _round(weewx.xtypes.get_aggregate('wind', ten, 'vecdir', db)[0], 0)
            except Exception:
                wind['avg10dir'] = wind['dir']
        mdg = cur(fm['maxdailygust'], 1)
        if mdg is not None:
            wind['maxGust'] = max(mdg, wind['maxGust'] or 0)

        # --- temperature/humidity channels -----------------------------------
        channels = []
        for c in self.cfg['channels']:
            t, h = c['temp'], c['hum']
            channels.append({'label': c['label'], 'temp': t, 'hum': h, 'sensor': c['sensor'],
                             'value': cur(t, 1), 'hi': agg(t, day, 'max', 1), 'lo': agg(t, day, 'min', 1),
                             'humValue': cur(h, 0), 'humHi': agg(h, day, 'max', 0), 'humLo': agg(h, day, 'min', 0)})

        def numbered(lst, nd=0):
            return [{'label': e['label'], 'field': e['field'], 'sensor': e.get('sensor'), 'value': cur(e['field'], nd)}
                    for e in lst]

        # --- rain -----------------------------------------------------------
        # With the driver: 'rain'/'rainRate' are the tipping gauge, or the piezo
        # when rain_source = piezo; the piezo is always in 'p_rain' and 'hail'.
        drs = driver_rain_source(self.config_dict)
        if drs == 'piezo':
            trad_field = trad_rate = None
            piezo_field = self._piezo_field([fm['p_rain'], fm['hail'], fm['rain']], keys, year, agg)
            piezo_rate = next((f for f in (fm['p_rainrate'], fm['hailRate'], fm['rainRate']) if f in keys), None)
        else:
            trad_field, trad_rate = fm['rain'], fm['rainRate']
            piezo_field = self._piezo_field([fm['p_rain'], fm['hail']], keys, year, agg)
            piezo_rate = next((f for f in (fm['p_rainrate'], fm['hailRate']) if f in keys), None)
        rain = [self._rain_block('Tipping', trad_field, trad_rate, rec, db, keys, spans, cur, agg, stop),
                self._rain_block('Piezo', piezo_field, piezo_rate, rec, db, keys, spans, cur, agg, stop)]

        # --- barometer ------------------------------------------------------
        baro_field = fm['barometer']
        baro = {'rel': cur(baro_field, 3), 'abs': cur(fm['pressure'], 3),
                'hi': agg(baro_field, day, 'max', 3), 'lo': agg(baro_field, day, 'min', 3),
                'trend3h': None, 'forecast': None}
        try:
            old = db.getRecord(stop - 10800, max_delta=max(interval * 2, 900))
            if old and old.get(baro_field) is not None and rec.get(baro_field) is not None:
                now_vt = weewx.units.as_value_tuple(rec, baro_field)
                old_vt = weewx.units.as_value_tuple(old, baro_field)
                diff = (now_vt[0] - old_vt[0], now_vt[1], now_vt[2])
                baro['trend3h'] = self._conv(diff, 3)
                baro['forecast'] = self._forecast(weewx.units.convert(now_vt, 'hPa')[0],
                                                  weewx.units.convert(diff, 'hPa')[0])
        except Exception as e:
            log.debug("ecowitt_console_emulator: barometer trend failed: %s", e)

        # --- solar / UV -----------------------------------------------------
        solar = {'rad': cur(fm['radiation'], 1), 'radHi': agg(fm['radiation'], day, 'max', 0),
                 'uv': cur(fm['UV'], 1), 'uvHi': agg(fm['UV'], day, 'max', 1)}

        # --- lightning ------------------------------------------------------
        month_back = TimeSpan(stop - 30 * 86400, stop)
        last_det = cur_raw(fm['lightning_time']) or agg(fm['lightning_time'], month_back, 'max')
        if not last_det and fm['lightning_strike_count'] in keys:
            try:
                row = db.getSql("SELECT MAX(dateTime) FROM %s WHERE %s > 0 AND dateTime > ?"
                                % (db.table_name, fm['lightning_strike_count']), (stop - 30 * 86400,))
                last_det = row[0] if row else None
            except Exception:
                pass
        # the driver's 'lightning_dist' isn't in the standard schema; 'lightning_distance' is
        dist = cur(fm['lightning_dist'], 0)
        for f in (fm['lightning_dist'], 'lightning_distance'):
            if dist is None:
                dist = cur(f, 0) if rec.get(f) is not None else agg(f, month_back, 'last', 0)
        count = cur(fm['lightningcount'], 0)
        if count is None:
            count = agg(fm['lightning_strike_count'], day, 'sum', 0)
        lightning = {'last': last_det or None, 'dist': dist, 'countDay': count}

        # --- air quality ----------------------------------------------------
        aq = {'pm': numbered(self.cfg['pm'], 1), 'co2': cur(fm['co2'], 0)}

        # --- records: highs and lows today, this month, this year, all time ---
        records = self._records(db, keys, fm, stop, agg, [('Tipping', trad_field, trad_rate),
                                                          ('Piezo', piezo_field, piezo_rate)]) \
            if self.cfg.get('records', True) else None

        units = {'system': 'METRICWX', 'temp': 'C', 'wind': 'ms', 'rain': 'mm', 'rainRate': 'mm/h',
                 'press': 'hpa', 'dist': 'km', 'radiation': 'W/m²', 'pm': 'µg/m³', 'co2': 'ppm'}

        data = {
            'version': VERSION, 'weewx': weewx.__version__,
            'generated': int(time.time()), 'archiveTime': stop, 'interval': interval,
            'station': getattr(stn, 'location', ''), 'hardware': getattr(stn, 'hardware', ''),
            'driverRainSource': drs,
            'lat': _round(getattr(stn, 'latitude_f', None), 4), 'lon': _round(getattr(stn, 'longitude_f', None), 4),
            # the station's time zone: the page shows all times in it
            'tz': station_timezone(self.generator.skin_dict.get('Extras', {}))[0],
            'tzOffset': station_timezone(self.generator.skin_dict.get('Extras', {}))[1],
            'units': units,
            'out': out, 'wind': wind, 'channels': channels,
            'soil': numbered(self.cfg['soil']), 'leaf': numbered(self.cfg['leaf']),
            'leak': numbered(self.cfg['leak']),
            'rain': rain, 'baro': baro, 'solar': solar, 'lightning': lightning, 'aq': aq,
            'records': records,
            'config': self.cfg,
            # calendar years with data: chart_<year>.json, chosen on the charts' Year tab
            'chartYears': _years(db),
            # the page fetches its translations with this tag, so updated ones are used at once
            'assetVersion': self._asset_version(),
        }
        log.debug("ecowitt_console_emulator: built dashboard data in %.3fs", time.time() - t0)
        return data

    # -- charts --------------------------------------------------------------
    # Each chart: (id, title, kind, unit group, [(series key, label, field, aggregate)])
    # kind: line | bar | dots. Values are written in METRICWX like the rest of the feed;
    # the browser converts them to the display units and draws them in the theme.
    def _rain_chart_defs(self, keys):
        """One rain chart with a bar series per gauge (tipping bucket and piezo
        sensor side by side) so the two can be compared directly."""
        fm = self.cfg['fields']
        keys = keys or ()
        # The piezo gauge is in 'p_rain', and also in 'hail' when the driver runs as
        # the station driver. The main database (wview_extended) has 'hail' but not
        # 'p_rain', so history copied from it only has the piezo rain in 'hail':
        # both are read and the larger total of each interval is used.
        if driver_rain_source(self.config_dict) == 'piezo':
            trad = None
            cands = [f for f in (fm['p_rain'], fm['hail'], fm['rain']) if f in keys]
        else:
            trad = fm['rain']
            cands = [f for f in (fm['p_rain'], fm['hail']) if f in keys]
        piezo = tuple(dict.fromkeys(cands)) or None
        mode = self.cfg.get('rain_sensors', 'auto')
        ss = []
        if trad and mode != 'piezo':
            ss.append(('rain', 'Tipping gauge', trad, 'sum'))
        if piezo and mode != 'tipping':
            ss.append(('rain_p', 'Piezo sensor', piezo, 'sum'))
        return [('rain', 'Rain', 'bar', 'rain', ss)] if ss else []

    def _chart_defs(self, period, keys=None):
        fm = self.cfg['fields']
        daily = period in ('year', 'calyear')
        defs = [
            ('temp', 'Temperature', 'line', 'temp',
             [('tmax', 'High', fm['outTemp'], 'max'), ('tmin', 'Low', fm['outTemp'], 'min')] if daily else
             [('temp', 'Temperature', fm['outTemp'], 'avg'), ('dew', 'Dew point', fm['dewpoint'], 'avg')]),
            ('intemp', 'Indoor temperature', 'line', 'temp',
             [('itmax', 'High', fm['inTemp'], 'max'), ('itmin', 'Low', fm['inTemp'], 'min')] if daily else
             [('itemp', 'Indoor temperature', fm['inTemp'], 'avg')]),
            ('hum', 'Humidity', 'line', 'hum', [('hum', 'Humidity', fm['outHumidity'], 'avg')]),
            # always written; the page leaves it out when show_vpd is off, so the setting
            # takes effect at once, also for calendar-year files that are never rewritten
            ('vpd', 'Vapour pressure deficit', 'line', 'vpd', [('vpd', 'VPD', VPD_FIELD, 'avg')]),
        ] + [
            ('wind', 'Wind', 'line', 'speed',
             [('wspd', 'Wind', fm['windSpeed'], 'avg'), ('wgst', 'Gust', fm['windGust'], 'max')]),
        ] + self._rain_chart_defs(keys) + [
            ('baro', 'Barometer', 'line', 'press', [('baro', 'Barometer', fm['barometer'], 'avg')]),
            ('rad', 'Solar radiation', 'line', 'rad', [('rad', 'Radiation', fm['radiation'], 'max' if daily else 'avg')]),
            ('uv', 'UV index', 'line', 'uv', [('uv', 'UV', fm['UV'], 'max' if daily else 'avg')]),
        ]
        if period == 'day':
            at = next((i + 1 for i, d in enumerate(defs) if d[0] == 'wind'), len(defs))
            defs.insert(at, ('dir', 'Wind direction', 'dots', 'dir', [('wdir', 'Direction', fm['windDir'], None)]))
        return defs

    def _chart_json(self, db, period, stop, timespan=None):
        """JSON with the series for one chart period: day, week, month, year (the last
        12 months) or calyear (the calendar year of the template's time span, 1 January
        to 31 December, from the [[SummaryByYear]] template chart_%Y.json.tmpl)."""
        t0 = time.time()
        # (span start, aggregate interval for lines, interval for rain bars)
        spans = {
            'day': (stop - 27 * 3600, None, 3600),
            'week': (startOfDay(stop - 7 * 86400), 3600, 86400),
            'month': (startOfDay(stop - 31 * 86400), 3 * 3600, 86400),
            'year': (_month_start(stop, 11), 86400, 'month'),
        }
        if period == 'calyear':
            yr = time.localtime(timespan.start).tm_year
            start = int(time.mktime((yr, 1, 1, 0, 0, 0, 0, 0, -1)))
            stop = int(time.mktime((yr + 1, 1, 1, 0, 0, 0, 0, 0, -1)))
            spans['calyear'] = (start, 86400, 'month')
        start, line_iv, rain_iv = spans.get(period, spans['day'])
        span = TimeSpan(start, stop)
        series, charts = {}, []
        try:
            db_keys = db.sqlkeys
        except Exception:
            db_keys = ()
        for cid, title, kind, group, ss in self._chart_defs(period, db_keys):
            keys = []
            for key, label, field, agg in ss:
                iv = rain_iv if kind == 'bar' else line_iv
                if field == VPD_FIELD:
                    data = self._vpd_series(db, db_keys, span, agg if iv else None, iv)
                elif isinstance(field, tuple):
                    data = self._merged_series(db, field, span, agg if iv else None, iv)
                else:
                    data = self._series(db, field, span, agg if iv else None, iv)
                if data and any(v is not None for v in data['v']):
                    series[key] = data
                    keys.append({'key': key, 'label': label})
            if keys:
                chart = {'id': cid, 'title': title, 'kind': kind, 'group': group, 'series': keys}
                if group == 'rain':
                    chart['totals'] = self._rain_totals(db, period, stop, ss, keys, span)
                charts.append(chart)
        out = {'period': period, 'start': start, 'stop': stop, 'generated': int(time.time()),
               'year': time.localtime(start).tm_year if period == 'calyear' else None,
               'charts': charts, 'series': series}
        log.debug("ecowitt_console_emulator: %s chart data in %.2fs", period, time.time() - t0)
        return json.dumps(out, separators=(',', ':'))

    # Legend totals of the rain chart: the same calendar periods as the rain table
    # (today, this week, this month, this rain year), not the chart's whole span.
    TOTAL_LABELS = {'day': 'Today', 'week': 'This week', 'month': 'This month', 'year': 'This year'}

    def _rain_totals(self, db, period, stop, ss, keys, chart_span=None):
        stn = self.generator.stn_info
        if period == 'calyear':           # the whole calendar year shown
            return self._sum_totals(db, chart_span, str(time.localtime(chart_span.start).tm_year), ss, keys)
        span = {'day': lambda: archiveDaySpan(stop),
                'week': lambda: archiveWeekSpan(stop, startOfWeek=getattr(stn, 'week_start', 6)),
                'month': lambda: archiveMonthSpan(stop),
                'year': lambda: archiveRainYearSpan(stop, getattr(stn, 'rain_year_start', 1))}[period]()
        return self._sum_totals(db, span, self.TOTAL_LABELS[period], ss, keys)

    def _sum_totals(self, db, span, label, ss, keys):
        shown = {k['key'] for k in keys}
        out = {'label': label, 'start': span.start, 'v': {}}
        for key, _label, field, _agg in ss:
            if key not in shown:
                continue
            best = None
            for f in (field if isinstance(field, tuple) else (field,)):
                try:
                    vt = weewx.xtypes.get_aggregate(f, span, 'sum', db)
                    v = FEED_CONVERTER.convert(vt)[0] if vt[1] is not None else vt[0]
                except Exception:
                    v = None
                if v is not None and (best is None or v > best):
                    best = v
            out['v'][key] = _round(best, 3)
        return out

    def _merged_series(self, db, fields, span, agg, interval):
        """One series from several fields holding the same quantity (piezo rain in
        'p_rain' and 'hail'): the largest value of each interval."""
        out = None
        for f in fields:
            d = self._series(db, f, span, agg, interval)
            if not d or not any(v is not None for v in d['v']):
                continue
            if out is None:
                out = d
            elif len(d['v']) == len(out['v']):
                out['v'] = [b if a is None else a if b is None else max(a, b) for a, b in zip(out['v'], d['v'])]
        return out

    def _vpd_series(self, db, db_keys, span, agg, interval):
        """VPD in kPa, worked out from the temperature and humidity series with the
        same formula as the dashboard reading (always kPa, whatever the units)."""
        fm = self.cfg['fields']
        t = self._series(db, fm['outTemp'], span, agg, interval)
        h = self._series(db, fm['outHumidity'], span, agg, interval)
        if not t or not h or len(t['v']) != len(h['v']):
            return None
        return {'t0': t['t0'], 't': t['t'], 'v': [_round(vpd_kpa(tc, rh), 3) for tc, rh in zip(t['v'], h['v'])]}

    @staticmethod
    def _series(db, field, span, agg, interval):
        if not field:
            return None
        try:
            if agg and interval:
                start_vt, stop_vt, data_vt = weewx.xtypes.get_series(field, span, db, aggregate_type=agg,
                                                                      aggregate_interval=interval)
            else:
                start_vt, stop_vt, data_vt = weewx.xtypes.get_series(field, span, db)
        except (weewx.UnknownType, weewx.UnknownAggregation):
            return None
        except Exception as e:
            log.debug("ecowitt_console_emulator: series %s failed: %s", field, e)
            return None
        try:
            if data_vt[1] is not None:
                data_vt = FEED_CONVERTER.convert(data_vt)
        except Exception:
            pass
        # time stamps: interval starts for bars, ends otherwise (both sent)
        return {'t0': [int(t) for t in start_vt[0]], 't': [int(t) for t in stop_vt[0]],
                'v': [_round(v, 2) for v in data_vt[0]]}

    # -- pieces -------------------------------------------------------------
    # (id, label, field map key, unit group for the page, aggregates: hi and/or lo)
    RECORD_ROWS = (
        ('outTemp', 'Temperature', 'outTemp', 'temp', 'hilo'),
        ('feelslike', 'Feels Like', 'feelslike', 'temp', 'hilo'),
        ('dewpoint', 'Dew point', 'dewpoint', 'temp', 'hilo'),
        ('outHumidity', 'Humidity', 'outHumidity', 'hum', 'hilo'),
        ('windGust', 'Gust', 'windGust', 'speed', 'hi'),
        ('barometer', 'Barometer', 'barometer', 'press', 'hilo'),
        ('radiation', 'Solar radiation', 'radiation', 'rad', 'hi'),
        ('UV', 'UV index', 'UV', 'uv', 'hi'),
    )

    def _records(self, db, keys, fm, stop, agg, gauges):
        """Highest and lowest values, with their times, for today, this month, this
        calendar year and all time. Read from the daily summaries (each period starts
        at midnight), so even years of data take a few milliseconds."""
        try:
            first = db.firstGoodStamp()
        except Exception:
            first = None
        if not first:
            return None
        tm = time.localtime(stop)
        starts = [('day', startOfDay(stop)), ('month', archiveMonthSpan(stop).start),
                  ('year', int(time.mktime((tm.tm_year, 1, 1, 0, 0, 0, 0, 0, -1)))),
                  ('all', startOfDay(first))]
        spans = [(name, TimeSpan(min(start, stop), stop)) for name, start in starts]

        def pair(field, span, aggregate, nd):
            v = agg(field, span, aggregate, nd)
            return [v, agg(field, span, aggregate + 'time', 0) if v is not None else None]

        rows = []
        for rid, label, key, group, which in self.RECORD_ROWS:
            field = fm.get(key)
            if not field or field not in keys:
                continue
            nd = 1 if group in ('temp', 'speed', 'press', 'rad', 'uv') else 0
            row = {'id': rid, 'label': label, 'group': group}
            for name, span in spans:
                row[name] = {'hi': pair(field, span, 'max', nd + (2 if group == 'press' else 0))}
                if which == 'hilo':
                    row[name]['lo'] = pair(field, span, 'min', nd + (2 if group == 'press' else 0))
            rows.append(row)
        # rain: the highest rate and the wettest day, for each gauge that is archived
        both = sum(1 for _, f, _r in gauges if f and f in keys) > 1
        for gauge, rain_f, rate_f in gauges:
            if rate_f and rate_f in keys:
                row = {'id': 'rate_' + gauge, 'label': 'Rain rate', 'group': 'rainrate',
                       'gauge': gauge if both else None}
                for name, span in spans:
                    row[name] = {'hi': pair(rate_f, span, 'max', 3)}
                rows.append(row)
            if rain_f and rain_f in keys:
                row = {'id': 'day_' + gauge, 'label': 'Daily Rain', 'group': 'rain',
                       'gauge': gauge if both else None}
                for name, span in spans:
                    row[name] = {'hi': pair(rain_f, span, 'maxsum', 3)}
                rows.append(row)
        return {'since': first, 'rows': rows}

    @staticmethod
    def _piezo_field(cands, keys, year, agg):
        """The piezo gauge is in 'p_rain' and, with the gateway as station driver, also
        in 'hail'. History copied from the main database only has 'hail', so use
        whichever holds more rain this year (the first one present when equal)."""
        have = [f for f in dict.fromkeys(cands) if f and f in keys]
        if len(have) < 2:
            return have[0] if have else None
        sums = [(agg(f, year, 'sum', 3) or 0.0) for f in have[:2]]
        return have[1] if sums[1] > sums[0] else have[0]

    def _rain_block(self, label, rain_f, rate_f, rec, db, keys, spans, cur, agg, stop):
        blk = {'label': label, 'field': rain_f, 'archived': bool(rain_f and rain_f in keys),
               'rate': None, 'event': None, 'r24h': None}
        if rate_f:
            blk['rate'] = cur(rate_f, 3) if rec.get(rate_f) is not None else agg(rate_f, spans['hour'], 'last', 3)
        for name, span in spans.items():
            blk[name] = agg(rain_f, span, 'sum', 3) if blk['archived'] else None
        if blk['archived']:
            blk['r24h'] = agg(rain_f, TimeSpan(stop - 86400, stop), 'sum', 3)
            blk['event'] = self._event_rain(db, rain_f, stop)
        return blk

    def _event_rain(self, db, field, stop):
        """Rain since the start of the current event; an event ends after 24 h without rain."""
        try:
            sql = ("SELECT dateTime, %s, usUnits FROM %s WHERE dateTime > ? AND dateTime <= ? "
                   "AND %s > 0 ORDER BY dateTime DESC" % (field, db.table_name, field))
            total, last_ts, units = 0.0, None, None
            for ts, val, us in db.genSql(sql, (stop - 60 * 86400, stop)):
                if (last_ts is None and stop - ts > 86400) or (last_ts is not None and last_ts - ts > 86400):
                    break
                total += val
                last_ts, units = ts, us
            if units is None:
                return 0.0
            unit, group = weewx.units.getStandardUnitType(units, field)
            return self._conv((total, unit, group), 3)
        except Exception as e:
            log.debug("ecowitt_console_emulator: event rain failed: %s", e)
            return None

    def _feels(self, rec, fm):
        """Feels-like when the driver's 'feelslike' isn't archived."""
        t_f, h_f, w_f = fm['outTemp'], fm['outHumidity'], fm['windSpeed']
        if rec.get(t_f) is None:
            return None
        try:
            t_c = weewx.units.convert(weewx.units.as_value_tuple(rec, t_f), 'degree_C')[0]
        except Exception:
            return None
        rh = rec.get(h_f)
        v_kph = None
        if rec.get(w_f) is not None:
            try:
                v_kph = weewx.units.convert(weewx.units.as_value_tuple(rec, w_f), 'km_per_hour')[0]
            except Exception:
                pass
        import weewx.wxformulas as wxf
        feels_c = t_c
        if t_c >= 26.7 and rh is not None:
            feels_c = wxf.heatindexC(t_c, rh) or t_c
        elif t_c <= 10.0 and v_kph is not None and v_kph > 4.8:
            feels_c = wxf.windchillMetric(t_c, v_kph) or t_c
        return self._conv((feels_c, 'degree_C', 'group_temperature'), 1)

    @staticmethod
    def _forecast(p_hpa, d3h_hpa):
        """A simple pressure-tendency forecast: sunny, partly, cloudy, rain or storm."""
        if d3h_hpa <= -3.0:
            return 'storm'
        if d3h_hpa <= -1.6 or (p_hpa < 1000 and d3h_hpa < -0.5):
            return 'rain'
        if d3h_hpa < -0.5:
            return 'cloudy'
        if d3h_hpa >= 1.6 or p_hpa >= 1022:
            return 'sunny'
        return 'partly'


def _jv(value):
    """JSON-encode a value for safe embedding in a template."""
    try:
        return json.dumps(value)
    except Exception:
        return 'null'


# ============================================================================
#                         The skin's own database
# ============================================================================

# Driver fields the dashboard uses that the standard wview_extended schema
# doesn't have. Added to the skin's database unless driver_fields = false.
DRIVER_COLUMNS = (['feelslike', 'windDir10', 'maxdailygust', 'p_rain', 'p_rainrate',
                   'lightning_dist', 'lightning_disturber_count', 'lightningcount']
                  + _rng('soilMoist{}', 16, 5) + _rng('leafWet{}', 8, 3)
                  + _rng('pm25_{}', 4) + _rng('leak_{}', 4))


def _build_default_schema():
    """wview_extended plus the driver columns. Used only if the database is
    opened (for example by 'weectl report run') before the service has created
    it from the main database's own schema."""
    import weewx.schemas.wview_extended as wv
    table = list(wv.schema['table'])
    have = {c[0] for c in table}
    table += [(c, 'REAL') for c in DRIVER_COLUMNS if c not in have]
    days = list(wv.schema['day_summaries'])
    have_d = {d[0] for d in days}
    days += [(c, 'scalar') for c in DRIVER_COLUMNS if c not in have_d]
    return {'table': table, 'day_summaries': days}


schema = _build_default_schema()


def _schema_like(src, driver_fields=True):
    """A schema with the same columns and daily summaries as the manager src,
    optionally with the driver columns added."""
    table = []
    for _n, name, typ, _null, _default, _pk in src.connection.genSchemaOf(src.table_name):
        if name == 'dateTime':
            typ = 'INTEGER NOT NULL UNIQUE PRIMARY KEY'
        elif name in ('usUnits', 'interval'):
            typ = 'INTEGER NOT NULL'
        table.append((name, typ or 'REAL'))
    daykeys = sorted(getattr(src, 'daykeys', None) or
                     [c for c, _ in table if c not in ('dateTime', 'usUnits', 'interval')])
    days = [(k, 'vector' if k == 'wind' else 'scalar') for k in daykeys]
    if driver_fields:
        # SQLite and MySQL column names ignore case: a main database with 'FeelsLike'
        # already has 'feelslike', and adding it again would stop the table being made
        have = {c.lower() for c, _ in table}
        extra = [c for c in DRIVER_COLUMNS if c.lower() not in have]
        table += [(c, 'REAL') for c in extra]
        days += [(c, 'scalar') for c in extra]
    return {'table': table, 'day_summaries': days}


class EcowittConsoleEmulatorArchive(StdService):
    """Keeps the skin's own database. Configured in weewx.conf:

    [EcowittConsoleEmulator]
        data_binding = ecce_binding     # the skin's database
        source_binding = wx_binding      # the station's main database
        backfill_days = 400              # history copied into a new database ('all' for everything)
        driver_fields = true             # add the driver's extra fields to a new database
    """

    def __init__(self, engine, config_dict):
        super().__init__(engine, config_dict)
        conf = config_dict.get('EcowittConsoleEmulator', {})
        self.binding = conf.get('data_binding', 'ecce_binding')
        self.source = conf.get('source_binding', 'wx_binding')
        self.dbm = None
        bindings = config_dict.get('DataBindings', {})
        if self.binding not in bindings:
            log.error("ecowitt_console_emulator: no [DataBindings][[%s]] in weewx.conf; the skin's database is "
                      "not being kept", self.binding)
            return
        try:
            self._prepare(config_dict, conf, bindings)
        except Exception as e:
            log.error("ecowitt_console_emulator: could not prepare database '%s': %s", self.binding, e)
            return
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

    def _prepare(self, config_dict, conf, bindings):
        bind_dict = bindings[self.binding]
        db_name = bind_dict['database']
        table = bind_dict.get('table_name', 'archive')
        db_dict = weewx.manager.get_database_dict_from_config(config_dict, db_name)
        src = self.engine.db_binder.get_manager(self.source, initialize=True)

        # 1. Check whether the database already exists; create it only if it doesn't
        if self._exists(db_dict, table):
            log.info("ecowitt_console_emulator: using existing database '%s' (binding %s)", db_name, self.binding)
            created = False
        else:
            new_schema = _schema_like(src, to_bool(conf.get('driver_fields', True)))
            log.info("ecowitt_console_emulator: database '%s' not found; creating it with the schema of '%s' "
                     "(%d columns)", db_name, self.source, len(new_schema['table']))
            try:
                weewx.manager.DaySummaryManager.open_with_create(db_dict, table, new_schema).close()
            except Exception as e:
                # Never leave the database without its table: every report run would then
                # fail ('No such table archive'). Fall back to the standard schema.
                log.error("ecowitt_console_emulator: could not create '%s' with the schema of '%s' (%s); "
                          "creating it with the standard schema (wview_extended and the driver fields) instead",
                          db_name, self.source, e)
                weewx.manager.DaySummaryManager.open_with_create(db_dict, table, schema).close()
            created = True

        # 2. Copy history (new database) or fill the gap since the last record
        self._sync(config_dict, db_dict, table, src, created, conf.get('backfill_days', 400))

        # 3. Open it and bring the daily summaries up to date (as StdArchive does)
        self.dbm = self.engine.db_binder.get_manager(self.binding, initialize=True)
        nrecs, ndays = self.dbm.backfill_day_summary(progress_fn=lambda *a: None)
        if nrecs:
            log.info("ecowitt_console_emulator: daily summaries updated: %d records over %d days", nrecs, ndays)

    @staticmethod
    def _exists(db_dict, table):
        try:
            conn = weedb.connect(db_dict)
        except weedb.NoDatabaseError:
            return False
        try:
            return table in conn.tables()
        finally:
            conn.close()

    def _sync(self, config_dict, db_dict, table, src, created, backfill_days):
        """Copy archive records from the main database that are newer than ours."""
        own = weewx.manager.Manager.open(db_dict, table)
        try:
            last_src = src.lastGoodStamp()
            last_own = own.lastGoodStamp()
            if not last_src:
                return
            if last_own:
                start = last_own
            elif str(backfill_days).lower() == 'all':
                start = 0
            else:
                start = last_src - to_int(backfill_days) * 86400
            if start >= last_src:
                return
            cols = [c for c in own.sqlkeys if c in src.sqlkeys]
            col_sql = ', '.join('`%s`' % c if src.connection.dbtype == 'mysql' else '"%s"' % c for c in cols)
            src_db = weewx.manager.get_database_dict_from_config(
                config_dict, config_dict['DataBindings'][self.source]['database'])
            t0 = time.time()
            if own.connection.dbtype == 'sqlite' and src.connection.dbtype == 'sqlite':
                src_path = os.path.join(src_db.get('SQLITE_ROOT', ''), src_db['database_name'])
                own.connection.execute("ATTACH DATABASE ? AS ecce_src", (src_path,))
                try:
                    own.connection.execute("INSERT OR IGNORE INTO %s (%s) SELECT %s FROM ecce_src.%s "
                                           "WHERE dateTime > ?" % (table, col_sql, col_sql, src.table_name),
                                           (start,))
                finally:
                    own.connection.execute("DETACH DATABASE ecce_src")
            elif (own.connection.dbtype == 'mysql' and src.connection.dbtype == 'mysql'
                  and db_dict.get('host') == src_db.get('host')):
                own.connection.execute("INSERT IGNORE INTO %s (%s) SELECT %s FROM `%s`.%s WHERE dateTime > %%s"
                                       % (table, col_sql, col_sql, src_db['database_name'], src.table_name),
                                       (start,))
            else:
                # Different database servers: copy record by record, limited to 3 days
                start = max(start, last_src - 3 * 86400)
                log.info("ecowitt_console_emulator: databases on different servers; copying only the last 3 days")
                dsm = weewx.manager.DaySummaryManager.open(db_dict, table)
                try:
                    dsm.addRecord(src.genBatchRecords(start + 1, last_src))
                finally:
                    dsm.close()
            n = own.getSql("SELECT COUNT(*) FROM %s WHERE dateTime > ?" % table, (start,))[0]
            log.info("ecowitt_console_emulator: %s %d archive records from '%s' in %.1fs",
                     'copied' if created else 'filled gap with', n, self.source, time.time() - t0)
        finally:
            own.close()

    def new_archive_record(self, event):
        """Write each archive record, including the driver fields the main database drops."""
        if self.dbm is None:
            return
        try:
            self.dbm.addRecord(event.record)
        except weedb.IntegrityError:
            pass      # already there (e.g. copied from the main database)
        except Exception as e:
            log.error("ecowitt_console_emulator: could not save record %s: %s", event.record.get('dateTime'), e)


# ============================================================================
#              Gateway MQTT payloads -> the driver's WeeWX fields
# ============================================================================
# Ecowitt gateways and consoles with MQTT (GW1200, GW2000, GW3000 ...) publish
# the same key=value string they send to a "Customized" upload server:
#   PASSKEY=...&stationtype=GW2000A_V3.1.4&dateutc=2025-07-25+11:50:12&tempinf=72.5&...
# in US units. Some firmware can also send metric keys (tempc, baromrelhpa,
# rainratemm ...). Each key is mapped here to the WeeWX field(s) that
# weewx-EcowittGateway gives the same value, with the unit it arrives in, so
# the dashboard reads MQTT data exactly as it reads the driver's loop packets.
# Keys not listed (PASSKEY, stationtype, heap ...) are left out of live.json.
#
# Battery fields are passed on as they arrive: binary (0 = OK), level (0-5) or
# volts. The dashboard reads the WH68 and WH40 either way; the WN20's, which
# the gateway sends in volts where the driver gives a level, is left out.
# MQTT carries no signal strengths.

_T, _H, _P, _S, _R, _RR, _D = ('group_temperature', 'group_percent', 'group_pressure', 'group_speed',
                               'group_rain', 'group_rainrate', 'group_direction')


def _gw_map():
    """{protocol key: ((field, ...), unit, unit group)}; unit None = no conversion."""
    m = {}

    def add(key, fields, unit=None, group=None):
        m[key] = (tuple(fields) if isinstance(fields, (list, tuple)) else (fields,), unit, group)

    # temperatures: US key, metric key, field(s)
    temps = [('tempinf', 'tempinc', 'inTemp'), ('tempf', 'tempc', 'outTemp'),
             ('dewpointf', 'dewpointc', 'dewpoint'), ('tempfeelsf', 'tempfeelsc', 'feelslike'),
             ('windchillf', 'windchillc', 'windchill'), ('bgt', 'bgtc', 'bgt'), ('wbgt', 'wbgtc', 'wbgt'),
             ('tf_co2', 'tf_co2c', 'co2_Temp')]
    temps += [('temp%df' % i, 'temp%dc' % i, 'extraTemp%d' % i) for i in range(1, 9)]
    temps += [('tf_ch%d' % i, 'tf_ch%dc' % i, 'soilTemp%d' % i) for i in range(1, 9)]
    temps += [('soil_ec_temp%d' % i, 'soil_ec_temp%dc' % i, 'soilmTemp%d' % i) for i in range(1, 17)]
    for us, metric, field in temps:
        add(us, field, 'degree_F', _T)
        add(metric, field, 'degree_C', _T)
    # humidity and other percentages
    for key, field in ([('humidityin', 'inHumidity'), ('humidity', 'outHumidity'), ('humi_co2', 'co2_Hum')] +
                       [('humidity%d' % i, 'extraHumid%d' % i) for i in range(1, 9)] +
                       [('soilmoisture%d' % i, 'soilMoist%d' % i) for i in range(1, 17)] +
                       [('soil_ec_hum%d' % i, 'soilMoist%de' % i) for i in range(1, 17)] +
                       [('leafwetness_ch%d' % i, 'leafWet%d' % i) for i in range(1, 9)]):
        add(key, field, 'percent', _H)
    # pressure
    add('baromrelin', 'barometer', 'inHg', _P)
    add('baromabsin', 'pressure', 'inHg', _P)
    add('baromrelhpa', 'barometer', 'hPa', _P)
    add('baromabshpa', 'pressure', 'hPa', _P)
    # wind
    add('winddir', 'windDir', 'degree_compass', _D)
    add('winddir_avg10m', 'windDir10', 'degree_compass', _D)
    for us, metric, field in (('windspeedmph', 'windspeedkmh', 'windSpeed'), ('windgustmph', 'windgustkmh', 'windGust'),
                              ('maxdailygust', 'maxdailygustkmh', 'maxdailygust')):
        add(us, field, 'mile_per_hour', _S)
        add(metric, field, 'km_per_hour', _S)
    # sun
    add('solarradiation', 'radiation', 'watt_per_meter_squared', 'group_radiation')
    add('uv', 'UV', 'uv_index', 'group_uv')
    # tipping-bucket gauge
    add('rainratein', 'rainRate', 'inch_per_hour', _RR)
    add('rainratemm', 'rainRate', 'mm_per_hour', _RR)
    for stem, field in (('eventrain', 'eventRain'), ('hourlyrain', 'hourRain'), ('dailyrain', 'dayRain'),
                        ('weeklyrain', 'weekRain'), ('monthlyrain', 'monthRain'), ('yearlyrain', 'yearRain'),
                        ('totalrain', 'totalRain'), ('last24hrain', 'rain24')):
        add(stem + 'in', field, 'inch', _R)
        add(stem + 'mm', field, 'mm', _R)
    # piezo gauge (WS90, WS85 ...)
    add('rrain_piezo', ('p_rainrate', 'rrain_piezo', 'hailRate'), 'inch_per_hour', _RR)
    add('rrain_piezomm', ('p_rainrate', 'rrain_piezo', 'hailRate'), 'mm_per_hour', _RR)
    for stem, fields in (('erain_piezo', 'erain_piezo'), ('hrain_piezo', 'hrain_piezo'),
                         ('drain_piezo', 'drain_piezo'), ('wrain_piezo', 'wrain_piezo'),
                         ('mrain_piezo', 'mrain_piezo'), ('yrain_piezo', ('yrain_piezo', 'p_rainyear')),
                         ('train_piezo', 'train_piezo'), ('last24hrain_piezo', 'rain24_piezo')):
        add(stem, fields, 'inch', _R)
        add(stem + 'mm', fields, 'mm', _R)
    add('srain_piezo', 'srain_piezo')
    # lightning (the driver keeps the time of the last strike in lightning_disturber_count)
    add('lightning', 'lightning_dist', 'km', 'group_distance')
    add('lightning_mi', 'lightning_dist', 'mile', 'group_distance')
    add('lightning_num', ('lightningcount', 'lightning_num'))
    add('lightning_time', 'lightning_disturber_count')
    # air quality
    add('co2', 'co2')
    add('co2_24h', 'co2_24h')
    add('co2in', 'co2in')
    add('co2in_24h', 'co2in_24h')
    for p, field in (('25', 'pm2_5'), ('10', 'pm10_0'), ('1', 'pm1_0'), ('4', 'pm4_0')):
        add('pm%s_co2' % p, field)
        add('pm%s_24h_co2' % p, 'pm%s_24h_co2' % p)
    for i in range(1, 5):
        add('pm25_ch%d' % i, 'pm25_%d' % i)
        add('pm25_avg_24h_ch%d' % i, 'pm25_avg_24h_ch%d' % i)
        add('leak_ch%d' % i, 'leak_%d' % i)
    # batteries
    for key, fields in (('wh65batt', 'outTempBatteryStatus'), ('wh25batt', ('wh25_batt', 'inTempBatteryStatus')),
                        ('wh26batt', 'wh26_batt'), ('wh57batt', 'lightning_Batt'), ('co2_batt', 'co2_Batt'),
                        ('wh80batt', 'ws80_batt'), ('wh68batt', 'wh68_batt'), ('wh40batt', 'wh40_batt'),
                        ('wh85batt', 'ws85_batt'), ('wh90batt', 'ws90_batt'),
                        ('wh69batt', 'wh69_batt'), ('bgtbatt', 'bgtbatt'), ('console_batt', 'console_batt'),
                        ('ws85cap_volt', 'ws85cap_volt'), ('ws90cap_volt', 'ws90cap_volt')):
        add(key, fields)
    for i in range(1, 9):
        add('batt%d' % i, 'batteryStatus%d' % i)
        add('tf_batt%d' % i, 'soilTempBatt%d' % i)
        add('leaf_batt%d' % i, 'leafWetBatt%d' % i)
    for i in range(1, 17):
        add('soilbatt%d' % i, 'soilMoistBatt%d' % i)
    for i in range(1, 5):
        add('pm25batt%d' % i, 'pm25_Batt%d' % i)
        add('leakbatt%d' % i, 'leak_Batt%d' % i)
        add('ldsbatt%d' % i, 'ldsbatt%d' % i)
    return m


GATEWAY_MQTT_MAP = _gw_map()


def parse_gateway_payload(payload):
    """A gateway's MQTT payload -> {protocol key: text}.

    Accepts the key=value form (as uploaded to a Customized server), the same
    preceded by HTTP headers (some GW1200 firmware), or a JSON object."""
    if isinstance(payload, bytes):
        payload = payload.decode('utf-8', 'replace')
    text = payload.strip()
    if text.startswith('{'):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return {str(k): v for k, v in obj.items()}
        except ValueError:
            pass
    # HTTP headers before the body: keep what follows the blank line
    for sep in ('\r\n\r\n', '\n\n'):
        if sep in text:
            text = text.split(sep, 1)[1].strip()
            break
    from urllib.parse import parse_qsl
    return dict(parse_qsl(text, keep_blank_values=True))


def gateway_to_metricwx(raw):
    """{protocol key: value} -> {WeeWX field: value in METRICWX}. Unknown keys and
    empty values (a sensor with no reading yet) are left out."""
    out = {}
    for key, value in raw.items():
        spec = GATEWAY_MQTT_MAP.get(key)
        if spec is None:
            continue
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        if math.isnan(v) or math.isinf(v):
            continue
        fields, unit, group = spec
        if unit:
            v = FEED_CONVERTER.convert(weewx.units.ValueTuple(v, unit, group))[0]
        for f in fields:
            out[f] = _round(v, 3)
    # Values the gateway doesn't send but the dashboard shows: WeeWX would add
    # them to loop packets (StdWXCalculate); worked out the same way here.
    t, rh = out.get('outTemp'), out.get('outHumidity')
    if t is not None and rh is not None:
        if out.get('dewpoint') is None:
            out['dewpoint'] = _round(weewx.wxformulas.dewpointC(t, rh), 3)
        if out.get('feelslike') is None:
            ws = out.get('windSpeed')
            if t >= 26.7:                                   # 80 °F: heat index
                fl = weewx.wxformulas.heatindexC(t, rh)
            elif t <= 10.0 and ws is not None and ws > 1.34:  # 50 °F and over 3 mph: wind chill
                fl = weewx.wxformulas.windchillMetricWX(t, ws)
            else:
                fl = t
            out['feelslike'] = _round(fl, 3)
    return out


# ============================================================================
#                  A small MQTT 3.1.1 subscriber (no libraries)
# ============================================================================

class MqttSubscriber(threading.Thread):
    """Subscribes to one or more topics and passes each message to on_message.

    Standard library only, so nothing else needs installing in WeeWX's Python.
    QoS 0, clean session; reconnects after 2 s, 4 s ... up to 2 minutes."""

    def __init__(self, host, port, topics, on_message, username=None, password=None,
                 client_id=None, keepalive=60, tls=None):
        super().__init__(name='ecce-mqtt', daemon=True)
        self.host, self.port, self.topics = host, int(port), list(topics)
        self.on_message = on_message
        self.username, self.password = username or None, password or None
        self.client_id = client_id or 'weewx-ecce-%d' % os.getpid()
        self.keepalive = max(10, int(keepalive))
        self.tls = tls                     # None, or an ssl.SSLContext
        self.stopping = threading.Event()
        self.sock = None
        self.last_error = None
        self.connected = False

    # -- framing ---------------------------------------------------------------
    @staticmethod
    def _str(s):
        b = s.encode('utf-8')
        return len(b).to_bytes(2, 'big') + b

    @staticmethod
    def _packet(first, body):
        n, length = len(body), bytearray()
        while True:
            byte, n = n % 128, n // 128
            length.append(byte | 0x80 if n else byte)
            if not n:
                break
        return bytes([first]) + bytes(length) + body

    def _recv_exact(self, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError('the broker closed the connection')
            buf.extend(chunk)
        return bytes(buf)

    def _read_packet(self):
        """The next packet. A timeout before it starts is passed on (the line is
        idle); one part-way through means the stream is out of step: reconnect."""
        import socket
        first = self._recv_exact(1)[0]
        try:
            mult, length = 1, 0
            for _ in range(4):
                byte = self._recv_exact(1)[0]
                length += (byte & 0x7F) * mult
                if not byte & 0x80:
                    break
                mult *= 128
            return first, self._recv_exact(length) if length else b''
        except socket.timeout:
            raise ConnectionError('incomplete packet from the broker')

    # -- session ---------------------------------------------------------------
    def _connect(self):
        import socket
        sock = socket.create_connection((self.host, self.port), timeout=15)
        if self.tls is not None:
            sock = self.tls.wrap_socket(sock, server_hostname=self.host)
        self.sock = sock
        flags = 0x02                                             # clean session
        payload = self._str(self.client_id)
        if self.username:
            flags |= 0x80
            payload += self._str(self.username)
            if self.password:
                flags |= 0x40
                payload += self._str(self.password)
        body = self._str('MQTT') + bytes([4, flags]) + self.keepalive.to_bytes(2, 'big') + payload
        sock.sendall(self._packet(0x10, body))
        first, body = self._read_packet()
        if first >> 4 != 2 or len(body) < 2:
            raise ConnectionError('unexpected reply to CONNECT')
        if body[1]:
            raise PermissionError({1: 'protocol version not accepted', 2: 'client id refused',
                                   3: 'broker unavailable', 4: 'wrong user name or password',
                                   5: 'not authorised (check the user name and password)'}.get(body[1], 'refused (code %d)' % body[1]))
        sub = b''.join(self._str(t) + b'\x00' for t in self.topics)
        sock.sendall(self._packet(0x82, (1).to_bytes(2, 'big') + sub))

    def _session(self):
        """Run one connection until it fails or stop() is called."""
        import socket
        self._connect()
        self.sock.settimeout(self.keepalive / 2.0)
        last_in = last_out = time.time()
        while not self.stopping.is_set():
            try:
                first, body = self._read_packet()
            except socket.timeout:
                now = time.time()
                if now - last_in > self.keepalive * 1.5:
                    raise ConnectionError('no reply from the broker for %ds' % int(now - last_in))
                if now - last_out >= self.keepalive / 2.0:
                    self.sock.sendall(b'\xc0\x00')               # PINGREQ
                    last_out = now
                continue
            last_in = time.time()
            kind = first >> 4
            if kind == 9:                                        # SUBACK
                if any(b == 0x80 for b in body[2:]):
                    raise PermissionError('not allowed to subscribe to %s' % ', '.join(self.topics))
                if not self.connected:
                    self.connected = True
                    log.info("ecowitt_console_emulator: MQTT subscribed to %s on %s:%d",
                             ', '.join(self.topics), self.host, self.port)
                    self.last_error = None
            elif kind == 3:                                      # PUBLISH
                qos = (first >> 1) & 3
                tlen = int.from_bytes(body[:2], 'big')
                topic = body[2:2 + tlen].decode('utf-8', 'replace')
                pos = 2 + tlen
                if qos:                                          # brokers may still send QoS 1/2
                    pid = body[pos:pos + 2]
                    pos += 2
                    self.sock.sendall(bytes([0x40 if qos == 1 else 0x50, 2]) + pid)
                try:
                    self.on_message(topic, body[pos:])
                except Exception as e:
                    log.error("ecowitt_console_emulator: MQTT message on %s failed: %s", topic, e)
            elif kind == 6:                                      # PUBREL -> PUBCOMP
                self.sock.sendall(b'\x70\x02' + body[:2])

    def run(self):
        delay = 2
        while not self.stopping.is_set():
            try:
                self._session()
            except Exception as e:
                if self.stopping.is_set():
                    break
                msg = str(e) or e.__class__.__name__
                # say so once; the same failure again only at debug level
                if msg != self.last_error:
                    log.error("ecowitt_console_emulator: MQTT %s:%d: %s (retrying)", self.host, self.port, msg)
                    self.last_error = msg
                else:
                    log.debug("ecowitt_console_emulator: MQTT %s:%d: %s", self.host, self.port, msg)
                if self.connected:
                    delay = 2
                elif isinstance(e, PermissionError):
                    delay = max(delay, 60)                       # bad password: don't hammer the broker
            finally:
                self.connected = False
                self._close()
            self.stopping.wait(delay)
            delay = min(120, delay * 2)

    def _close(self):
        sock, self.sock = self.sock, None
        if sock is not None:
            try:
                sock.sendall(b'\xe0\x00')                        # DISCONNECT
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    def stop(self):
        self.stopping.set()
        self._close()


# ============================================================================
#                         Live (loop packet) service
# ============================================================================

class EcowittConsoleEmulatorLive(StdService):
    """Writes the latest live data to live.json, from WeeWX loop packets, from
    the gateway's own MQTT messages, or both.

    Only needed when the driver's ecwLoop.json can't be served next to the
    dashboard, or to take live data from MQTT; the installer turns it on or off.
    Configured in weewx.conf:

    [EcowittConsoleEmulator]
        enable = false
        report = EcowittConsoleEmulatorReport
        interval = 5
        filename = live.json
        # loop: WeeWX loop packets (any driver); mqtt: the gateway's MQTT
        # messages; both: loop packets, with MQTT values on top
        source = loop
        [[MQTT]]
            host = localhost
            port = 1883
            topic = ecowitt/#           # the gateway's topic; several: a, b
            username =
            password =
            # tls = true for a broker that needs it (the gateway itself can't use TLS)
            tls = false
            ca_certs =                  # optional CA file for tls
            keepalive = 60
    """

    def __init__(self, engine, config_dict):
        super().__init__(engine, config_dict)
        self.mqtt = None
        conf = config_dict.get('EcowittConsoleEmulator', {})
        if not to_bool(conf.get('enable', False)):
            log.info("ecowitt_console_emulator: own live.json disabled (the dashboard uses the driver's ecwLoop.json)")
            return
        self.interval = to_float(conf.get('interval', 5))
        report = conf.get('report', 'EcowittConsoleEmulatorReport')
        self.converter = FEED_CONVERTER
        path = conf.get('path')
        try:
            import weewx.reportengine
            skin_dict = weewx.reportengine.build_skin_dict(config_dict, report)
            if not path:
                path = os.path.join(config_dict.get('WEEWX_ROOT', ''), skin_dict['HTML_ROOT'])
        except Exception as e:
            log.error("ecowitt_console_emulator: could not load report '%s' (%s)", report, e)
            if not path:
                path = os.path.join(config_dict.get('WEEWX_ROOT', ''),
                                    config_dict.get('StdReport', {}).get('HTML_ROOT', 'public_html'), 'console')
        self.path = os.path.join(path, conf.get('filename', 'live.json'))
        self.cache = {}          # from loop packets, merged as they arrive
        self.mqtt_data = {}      # the gateway's latest MQTT message (each one is a full set)
        self.mqtt_time = 0
        self.loop_time = 0
        # with source = both, MQTT values older than this no longer hide the loop's
        self.mqtt_stale = to_int(conf.get('mqtt_stale', 120))
        self.last_write = 0
        self.lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.source = live_source(conf)
        if self.source in ('loop', 'both'):
            self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
        if self.source in ('mqtt', 'both'):
            self._start_mqtt(conf.get('MQTT', {}))
        log.info("ecowitt_console_emulator: version %s, writing live data to %s (from %s)",
                 VERSION, self.path, {'loop': 'loop packets, every %.0fs' % self.interval,
                                      'mqtt': 'MQTT', 'both': 'loop packets and MQTT'}[self.source])

    def _start_mqtt(self, mc):
        tls = None
        if to_bool(mc.get('tls', False)):
            import ssl
            tls = ssl.create_default_context(cafile=mc.get('ca_certs') or None)
            if to_bool(mc.get('tls_insecure', False)):
                tls.check_hostname = False
                tls.verify_mode = ssl.CERT_NONE
        topics = [t for t in _as_list(mc.get('topic', 'ecowitt/#')) if t]
        port = to_int(mc.get('port', 8883 if tls else 1883))
        self.mqtt = MqttSubscriber(str(mc.get('host', 'localhost')), port, topics, self.new_mqtt_message,
                                   username=mc.get('username'), password=mc.get('password'),
                                   client_id=mc.get('client_id'), keepalive=to_int(mc.get('keepalive', 60)),
                                   tls=tls)
        self.mqtt.start()

    def new_loop_packet(self, event):
        try:
            conv = self.converter.convertDict(event.packet)
            with self.lock:
                self.loop_time = time.time()
                for k, v in conv.items():
                    if v is not None or k == 'windDir':
                        self.cache[k] = _round(v, 3) if isinstance(v, float) else v
            now = time.time()
            if now - self.last_write >= self.interval:
                self.last_write = now
                self._write(now)
        except Exception as e:
            log.error("ecowitt_console_emulator: live packet failed: %s", e)

    def new_mqtt_message(self, topic, payload):
        data = gateway_to_metricwx(parse_gateway_payload(payload))
        if not data:
            log.debug("ecowitt_console_emulator: MQTT message on %s has no readings; ignored", topic)
            return
        with self.lock:
            self.mqtt_data = data
            self.mqtt_time = time.time()
        # the gateway sends every 8 s or more, so each message is written at once
        now = time.time()
        self.last_write = now
        self._write(now)

    def _write(self, now):
        with self.lock:
            data = dict(self.cache)
            mqtt_fresh = self.source == 'mqtt' or now - self.mqtt_time < self.mqtt_stale
            if mqtt_fresh:
                data.update(self.mqtt_data)
            # what this write was made from, shown on the dashboard: loop, mqtt or both
            sources = []
            if self.source in ('loop', 'both') and now - self.loop_time < self.mqtt_stale:
                sources.append('loop')
            if self.source in ('mqtt', 'both') and self.mqtt_data and mqtt_fresh:
                sources.append('mqtt')
            payload = {'written': int(now), 'units': 'METRICWX', 'sources': sources, 'data': data}
        with self.write_lock:
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                tmp = self.path + '.tmp'
                with open(tmp, 'w') as f:
                    json.dump(payload, f, separators=(',', ':'), default=str)
                os.replace(tmp, self.path)
            except OSError as e:
                log.error("ecowitt_console_emulator: cannot write %s: %s", self.path, e)

    def shutDown(self):
        if self.mqtt is not None:
            self.mqtt.stop()
            self.mqtt = None


def live_source(conf):
    """[EcowittConsoleEmulator] source: loop, mqtt or both (default loop)."""
    v = str((conf or {}).get('source', 'loop')).strip().lower()
    return v if v in ('loop', 'mqtt', 'both') else 'loop'
