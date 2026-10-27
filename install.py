# Installer for the EcowittConsoleEmulator skin (WeeWX 5) - weewx-ecowitt_console_emulator
#
# Copyright (c) Ian Millard 2026
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
#   weectl extension install weewx-ecowitt_console_emulator.zip
#
# Works with any driver for an Ecowitt gateway or console. If the optional
# weewx-EcowittGateway driver/service is installed, its settings are used too.
#
# During the install you are asked which rain sensor(s) the station has (with
# weewx-EcowittGateway, the default is its rain_source answer):
#   tipping  - traditional tipping-bucket gauge (WH40, WS69/WH65 array, WS80...)
#   piezo    - piezoelectric haptic gauge (WS90, WS85, WH40H...)
#   both     - both kinds; the dashboard's rain section gets a column for each
#
# whether to show VPD (vapour pressure deficit): the reading and its chart (yes/no),
#
# and where live data comes from:
#   driver - the driver's ecwLoop.json (its [[loop_json]] option; turned on if needed;
#            only offered when weewx-EcowittGateway is installed)
#   skin   - the skin's own live.json, written from WeeWX loop packets by the
#            EcowittConsoleEmulatorLive service
#   mqtt   - the skin's own live.json, written from the gateway's own MQTT messages
#            (GW1200, GW2000, GW3000 ...); then the broker's address, the gateway's
#            topic and, if the broker needs them, a user name and password are asked
#
# The skin keeps its own database (binding ecce_binding). The installer
# checks whether that binding, database entry and database already exist and
# leaves any it finds untouched; WeeWX creates the database on first start only
# if it doesn't exist, with the same schema as the station's main database.
#
# For unattended installs give the answers on the command line:
# Last, it can name your sensors: the channels, soil, leaf, leak and PM sensors that have
# readings in the database are listed, and each can be given a name (Porch, Attic,
# Freezer ...) shown on the dashboard instead of "WN31 CH1".
#
#   weectl extension install weewx-ecowitt_console_emulator.zip --yes --rain=both --live=driver --vpd=y
#   weectl extension install weewx-ecowitt_console_emulator.zip --yes --label=extraTemp1=Porch \
#       --label=extraTemp2=Attic --label=soilTemp1=Freezer
#   weectl extension install weewx-ecowitt_console_emulator.zip --yes --rain=piezo --vpd=y --live=mqtt \
#       --mqtt-host=192.168.1.20 --mqtt-topic=ecowitt/1C6920E3A8F3 --mqtt-user=weewx --mqtt-password=secret
#
import getpass
import os
import posixpath
import sys

from weecfg.extension import ExtensionInstaller

VERSION = "2.0.0-custom"
REPORT = 'EcowittConsoleEmulatorReport'
RAIN_CHOICES = ('tipping', 'piezo', 'both')
LIVE_CHOICES = ('driver', 'skin', 'mqtt')
VPD_CHOICES = ('yes', 'no')
# Translations in skins/EcowittConsoleEmulator/lang (English is built into the page)
LANGUAGES = ('ar', 'br', 'ca', 'cn', 'cy', 'cz', 'da', 'de', 'en_US', 'es', 'eu', 'fi', 'fr', 'gr', 'hi',
             'hu', 'is', 'it', 'ja', 'nl', 'no', 'pl', 'pt', 'sv', 'ta', 'th', 'tr', 'uk', 'ur')
DRIVER_SECTIONS = ('EcowittGateway', 'EcowittHttp')
LOOP_NAME = 'ecwLoop.json'
BINDING = 'ecce_binding'
DB_SQLITE, DB_MYSQL = 'ecce_sqlite', 'ecce_mysql'
DB_FILE, DB_MYSQL_NAME = 'ecowitt_console_emulator.sdb', 'ecowitt_console_emulator'


def loader():
    return EcowittConsoleEmulatorInstaller()


class EcowittConsoleEmulatorInstaller(ExtensionInstaller):
    def __init__(self):
        skin = 'skins/EcowittConsoleEmulator'
        super().__init__(
            version=VERSION,
            name='ecowitt_console_emulator',
            description='Ecowitt console emulator: full-screen dashboard in the style of the Ecowitt HP2560 console, '
                        'for any Ecowitt gateway device.',
            author='Ian Millard',
            archive_services='user.ecowitt_console_emulator.EcowittConsoleEmulatorArchive',
            report_services='user.ecowitt_console_emulator.EcowittConsoleEmulatorLive',
            config={
                'StdReport': {
                    REPORT: {
                        'skin': 'EcowittConsoleEmulator',
                        'HTML_ROOT': 'console',
                        'enable': 'true',
                        # the dashboard and graphs read the skin's own database
                        'data_binding': BINDING,
                        'Extras': {},
                    }
                },
                'EcowittConsoleEmulator': {
                    'enable': 'false',
                    'report': REPORT,
                    'interval': '5',
                    'filename': 'live.json',
                    # the skin's own database, kept by EcowittConsoleEmulatorArchive
                    'data_binding': BINDING,
                    'source_binding': 'wx_binding',
                    'backfill_days': '400',
                    'driver_fields': 'true',
                },
                'DataBindings': {
                    BINDING: {
                        'database': DB_SQLITE,
                        'table_name': 'archive',
                        'manager': 'weewx.manager.DaySummaryManager',
                        'schema': 'user.ecowitt_console_emulator.schema',
                    },
                },
                'Databases': {
                    DB_SQLITE: {'database_name': DB_FILE, 'database_type': 'SQLite'},
                    DB_MYSQL: {'database_name': DB_MYSQL_NAME, 'database_type': 'MySQL'},
                },
            },
            files=[
                ('bin/user', ['bin/user/ecowitt_console_emulator.py']),
                (skin, [skin + '/skin.conf',
                        skin + '/index.html.tmpl',
                        skin + '/chart_day.json.tmpl',
                        skin + '/chart_week.json.tmpl',
                        skin + '/chart_month.json.tmpl',
                        skin + '/chart_year.json.tmpl',
                        skin + '/chart_%Y.json.tmpl',
                        skin + '/ecowitt.json.tmpl',
                        skin + '/ecce_payload.inc',
                        skin + '/manifest.json']),
                (skin + '/css', [skin + '/css/console.css', skin + '/css/solar-flow.css']),
                (skin + '/js', [skin + '/js/console.js', skin + '/js/solar-flow.js']),
                (skin + '/icons', [skin + '/icons/icon.svg']),
                (skin + '/lang', [skin + '/lang/%s.json' % c for c in LANGUAGES]),
            ],
        )
        self.rain_arg = None
        self.live_arg = None
        self.vpd_arg = None
        self.mqtt_args = {}
        self.label_args = {}

    def process_args(self, args):
        """Accept --rain=tipping|piezo|both, --live=driver|skin|mqtt and --vpd=y|n for unattended
        installs, and with --live=mqtt: --mqtt-host, --mqtt-port, --mqtt-topic, --mqtt-user,
        --mqtt-password."""
        for i, a in enumerate(args or []):
            # --label=FIELD=NAME (repeatable): a sensor's name on the dashboard
            val = a.split('=', 1)[1] if a.startswith('--label=') else (args[i + 1] if a == '--label' and i + 1 < len(args) else None)
            if val is not None:
                field, _, name = val.partition('=')
                if field.strip() not in SENSOR_FIELDS or not name.strip():
                    raise ValueError("--label must be FIELD=NAME, FIELD one of: %s" % ', '.join(SENSOR_FIELDS))
                self.label_args[field.strip()] = _clean_label(name)
            for opt, key in (('--mqtt-host', 'host'), ('--mqtt-port', 'port'), ('--mqtt-topic', 'topic'),
                             ('--mqtt-user', 'username'), ('--mqtt-password', 'password')):
                if a.startswith(opt + '='):
                    self.mqtt_args[key] = a.split('=', 1)[1].strip()
                elif a == opt and i + 1 < len(args):
                    self.mqtt_args[key] = args[i + 1].strip()
            for opt, choices, attr in (('--rain', RAIN_CHOICES, 'rain_arg'), ('--live', LIVE_CHOICES, 'live_arg'),
                                       ('--vpd', VPD_CHOICES, 'vpd_arg')):
                val = None
                if a.startswith(opt + '='):
                    val = a.split('=', 1)[1]
                elif a == opt and i + 1 < len(args):
                    val = args[i + 1]
                if val is not None:
                    val = val.strip().lower()
                    val = next((c for c in choices if val and c.startswith(val)), val)   # y -> yes
                    if val not in choices:
                        raise ValueError("%s must be one of: %s" % (opt, ', '.join(choices)))
                    setattr(self, attr, val)

    def configure(self, engine):
        cfg = engine.config_dict
        driver = next((cfg[n] for n in DRIVER_SECTIONS if n in cfg), None)
        report = cfg.get('StdReport', {}).get(REPORT)
        extras = report.get('Extras', {}) if report is not None else {}
        interactive = sys.stdin is not None and sys.stdin.isatty()
        out = engine.printer.out
        changed = False

        if driver is None:
            out("EcowittConsoleEmulator: weewx-EcowittGateway not found; live data will come from the "
                "skin's own live.json (from loop packets or the gateway's MQTT messages)")

        # --- rain sensor(s): default to the driver's own answer -------------
        current = extras.get('rain_sensors')
        drv_rain = str(driver.get('rain_source', '')).lower() if driver is not None else ''
        default = current if current in RAIN_CHOICES else drv_rain if drv_rain in RAIN_CHOICES else 'tipping'
        rain = self.rain_arg
        if rain is None:
            if interactive:
                print("\nWhich rain sensor does this station have?")
                print("  tipping - traditional tipping-bucket gauge (WH40, WS69, WN20 ...)")
                print("  piezo   - piezoelectric haptic gauge (WS90, WS85 ...)")
                print("  both    - both; the rain section shows a column for each")
                if drv_rain in RAIN_CHOICES:
                    print("  (the EcowittGateway driver is set to rain_source = %s)" % drv_rain)
                rain = _ask("Rain sensor (tipping/piezo/both)", default, RAIN_CHOICES)
            else:
                rain = default
        if rain == 'both' and drv_rain in ('tipping', 'piezo'):
            out("EcowittConsoleEmulator: note - the driver records only one gauge (rain_source = %s). Set its "
                "rain_source = both to archive the second gauge too." % drv_rain)
        out("EcowittConsoleEmulator: rain sensor(s) set to '%s'" % rain)

        # --- VPD (vapour pressure deficit) reading and chart -------------------
        cur_vpd = str(extras.get('show_vpd', 'true')).lower()
        default_vpd = 'no' if cur_vpd in ('false', 'no', '0', 'off') else 'yes'
        vpd = self.vpd_arg
        if vpd is None:
            if interactive:
                print("\nShow VPD (vapour pressure deficit, in kPa) on the dashboard and in the charts?")
                vpd = _ask("Show VPD (yes/no)", default_vpd, VPD_CHOICES)
            else:
                vpd = default_vpd
        out("EcowittConsoleEmulator: VPD %s" % ('shown' if vpd == 'yes' else 'not shown'))

        # --- live data: the driver's ecwLoop.json, or the skin's live.json from
        # loop packets or from the gateway's MQTT messages ---------------------
        loop = driver.get('loop_json', {}) if driver is not None else {}
        own = cfg.get('EcowittConsoleEmulator', {})
        live_url, loop_settings = None, None
        if driver is not None:
            loop_path = _loop_json_path(cfg, loop if str(loop.get('enable', 'False')).lower() == 'true' else {})
            live_url = _url_from_page(cfg, loop_path)
        if str(own.get('source', '')).lower() in ('mqtt', 'both') and str(own.get('enable', '')).lower() == 'true':
            default_live = 'mqtt'
        else:
            default_live = (extras.get('live_url') and ('skin' if extras.get('live_url') == 'live.json' else 'driver')) \
                or ('driver' if live_url else 'skin')
        choices = LIVE_CHOICES if driver is not None else ('skin', 'mqtt')
        if default_live not in choices:
            default_live = 'skin'
        live = self.live_arg
        if live is None:
            if interactive:
                print("\nWhere should the tablet get live (every few seconds) data from?")
                if driver is not None:
                    print("  driver - the driver's %s (its loop_json option%s)" %
                          (LOOP_NAME, ', already on' if str(loop.get('enable', 'False')).lower() == 'true'
                           else ', will be turned on'))
                print("  skin   - this skin's own live.json, from WeeWX loop packets")
                print("  mqtt   - this skin's own live.json, from the gateway's own MQTT messages")
                live = _ask("Live data source (%s)" % '/'.join(choices), default_live, choices)
            else:
                live = default_live
        loop_on = str(loop.get('enable', 'False')).lower() == 'true'
        if live == 'driver' and driver is None:
            out("EcowittConsoleEmulator: weewx-EcowittGateway not found, so using the skin's live.json")
            live = 'skin'
        elif live == 'driver' and not loop_on:
            # Turn the driver's loop file on, in the web folder; the skin reads any units
            loop_settings = {'enable': 'True', 'path': LOOP_NAME, 'units': 'metricwx'}
            live_url = _url_from_page(cfg, _loop_json_path(cfg, loop_settings))
        elif live == 'driver' and not live_url:
            out("EcowittConsoleEmulator: the driver's %s is written outside the web folder (%s), so the tablet "
                "can't read it. Using the skin's live.json instead." % (LOOP_NAME, loop.get('path')))
            live = 'skin'
        mqtt = None
        if live == 'mqtt':
            mqtt = self._mqtt_settings(own.get('MQTT', {}), interactive)
        out("EcowittConsoleEmulator: live data from %s" %
            ("the driver's %s (%s)" % (LOOP_NAME, live_url) if live == 'driver' else
             "the skin's live.json, from MQTT topic %s on %s:%s" % (mqtt['topic'], mqtt['host'], mqtt['port'])
             if live == 'mqtt' else "the skin's live.json"))

        # --- the skin's own database: check what already exists ------------
        changed |= self._configure_database(engine, cfg, out)

        # --- names for the sensors (Porch, Attic, Freezer ...) ---------------
        name_sections = self._sensor_names(cfg, extras, interactive, out)

        # --- per-year chart files (chart_2025.json ...) are written once and then kept;
        # remove them so WeeWX writes them again, with this version's charts
        if not engine.dry_run:
            n = _remove_year_charts(cfg)
            if n:
                out("EcowittConsoleEmulator: removed %d calendar-year chart file(s); WeeWX writes them "
                    "again at its next report" % n)

        # --- write the answers ----------------------------------------------
        answers = {'rain_sensors': rain, 'live_url': live_url if live == 'driver' else 'live.json',
                   'show_vpd': 'true' if vpd == 'yes' else 'false'}
        service_enable = 'false' if live == 'driver' else 'true'
        # 'both' (loop packets and MQTT) is only set by hand; keep it
        source = 'mqtt' if live == 'mqtt' else 'loop'
        if live == 'mqtt' and str(own.get('source', '')).lower() == 'both':
            source = 'both'
        self['config']['StdReport'][REPORT]['Extras'].update(answers)
        self['config']['StdReport'][REPORT]['Extras'].update(name_sections)
        self['config']['EcowittConsoleEmulator']['enable'] = service_enable
        self['config']['EcowittConsoleEmulator']['source'] = source
        if mqtt:
            self['config']['EcowittConsoleEmulator']['MQTT'] = dict(mqtt)
        if engine.dry_run:
            return False
        if report is not None:
            report.setdefault('Extras', {})
            for k, v in answers.items():
                if report['Extras'].get(k) != v:
                    report['Extras'][k] = v
                    changed = True
            for k, v in name_sections.items():
                if dict(report['Extras'].get(k) or {}) != v:
                    report['Extras'][k] = v
                    changed = True
        if 'EcowittConsoleEmulator' in cfg:
            section = cfg['EcowittConsoleEmulator']
            for k, v in (('enable', service_enable), ('source', source)):
                if section.get(k) != v:
                    section[k] = v
                    changed = True
            if mqtt:
                section.setdefault('MQTT', {})
                for k, v in mqtt.items():
                    if section['MQTT'].get(k) != v:
                        section['MQTT'][k] = v
                        changed = True
        if loop_settings:
            driver.setdefault('loop_json', {}).update(loop_settings)
            out("EcowittConsoleEmulator: turned on the driver's %s in the web folder" % LOOP_NAME)
            changed = True
        return changed


    def _mqtt_settings(self, current, interactive):
        """The broker and topic for live data from the gateway's MQTT messages: from the
        command line, else asked, with the current settings (or the usual ones) as defaults."""
        a = self.mqtt_args
        s = {'host': a.get('host') or current.get('host') or 'localhost',
             'port': a.get('port') or current.get('port') or '1883',
             'topic': a.get('topic') or current.get('topic') or 'ecowitt/#',
             'username': a.get('username', current.get('username', '')),
             'password': a.get('password', current.get('password', ''))}
        if interactive and not a:
            print("\nThe gateway publishes to an MQTT broker (set in its web page or the WS View Plus app,")
            print("under MQTT). The skin subscribes to the same broker and topic.")
            s['host'] = _ask_text("Broker address", s['host'])
            s['port'] = _ask_text("Broker port", s['port'])
            s['topic'] = _ask_text("Gateway's topic (e.g. ecowitt/<MAC>; ecowitt/# takes any)", s['topic'])
            s['username'] = _ask_text("Broker user name (blank if none)", s['username'])
            if s['username']:
                try:
                    pw = getpass.getpass("Broker password%s: " % (' [keep current]' if s['password'] else ''))
                except (EOFError, KeyboardInterrupt):
                    pw = ''
                s['password'] = pw or s['password']
            else:
                s['password'] = ''
        if not str(s['port']).isdigit():
            raise ValueError("--mqtt-port must be a number")
        return s

    def _sensor_names(self, cfg, extras, interactive, out):
        """Ask for (or take from --label) a name for each sensor that has readings, and return
        the [[Channels]], [[SoilChannels]] ... sections to write: only those with a changed
        name, each listing every sensor of its kind, so sensors added later still appear."""
        current = _current_labels(extras)
        names = dict(current)
        names.update(self.label_args)
        if interactive and not self.label_args:
            found = _sensors_with_data(cfg)
            if found is None:
                out("EcowittConsoleEmulator: couldn't read the database to list your sensors; they can be "
                    "named later in weewx.conf (see 'Naming sensors' in the README)")
            elif not found:
                out("EcowittConsoleEmulator: no sensor readings in the database yet; sensors can be named "
                    "later by installing again, or in weewx.conf")
            else:
                print("\nThe dashboard can show your own names for your sensors (Porch, Attic, Freezer ...)")
                print("instead of \"WN31 CH1\". Found: " + ', '.join(current.get(f) or SENSOR_DEFAULTS[f] for f in found))
                if _ask("Name them now (yes/no)", 'no', ('yes', 'no')) == 'yes':
                    print("Press Enter to keep the name shown in [brackets].")
                    used = set()
                    for f in found:
                        default = names.get(f) or SENSOR_DEFAULTS[f]
                        probe = f.startswith('soilTemp')
                        prompt = '  %s (%s)%s' % (SENSOR_DESC[f], f, ', shown with the CH button if named' if probe else '')
                        while True:
                            ans = _ask_text(prompt, default if (not probe or f in names) else 'not shown')
                            ans = '' if ans == 'not shown' else _clean_label(ans)
                            if ans and ans in used:
                                print("    '%s' is already used; please choose another name." % ans)
                                continue
                            break
                        if ans and ans == SENSOR_DEFAULTS[f] and f not in current:
                            continue                # left as it is: nothing to write
                        if ans:
                            used.add(ans)
                            names[f] = ans
                        else:
                            names.pop(f, None)
        sections = {}
        for section, rows in SENSOR_SECTIONS.items():
            changed = any(names.get(r[0]) != current.get(r[0]) for r in rows)
            if not changed:
                continue
            spec = {r[0]: ', '.join(r[1:]) for r in rows}
            existing = extras.get(section) or {}
            body = {}
            if existing:
                # edit the section that is there: rename its entries, keep its order, its
                # other entries and any left out; add newly named WN34 probes at the end
                seen = set()
                for label, entry in existing.items():
                    text = ', '.join(entry) if isinstance(entry, (list, tuple)) else str(entry)
                    field = text.split(',')[0].strip()
                    if field in spec:
                        seen.add(field)
                        if field.startswith('soilTemp') and field not in names:
                            continue              # a probe whose name was cleared: not shown
                        body[names.get(field) or SENSOR_DEFAULTS[field]] = text
                    else:
                        body[label] = text
                for field in spec:
                    if field not in seen and field in names and names[field] != current.get(field):
                        body[names[field]] = spec[field]      # named in this install
            else:
                # a new section lists every sensor of its kind, so ones added later still appear
                for field in spec:
                    if field.startswith('soilTemp') and field not in names:
                        continue                  # WN34 probes are only shown when named
                    body[names.get(field) or SENSOR_DEFAULTS[field]] = spec[field]
            sections[section] = body
            out("EcowittConsoleEmulator: sensor names in [[%s]]: %s" % (
                section, ', '.join(names[r[0]] for r in rows if names.get(r[0]))))
        return sections

    def _configure_database(self, engine, cfg, out):
        """Set up the skin's database binding, leaving anything that already exists alone."""
        bindings = cfg.get('DataBindings', {})
        databases = cfg.get('Databases', {})
        if BINDING in bindings:
            db_name = bindings[BINDING].get('database')
            out("EcowittConsoleEmulator: binding [%s] already exists (database %s); leaving it unchanged" % (BINDING, db_name))
            db_entry = databases.get(db_name)
        else:
            # Same database type as the station's main database
            main_db = bindings.get('wx_binding', {}).get('database')
            main_type = str(databases.get(main_db, {}).get('database_type', 'SQLite'))
            db_name = DB_MYSQL if main_type.lower() == 'mysql' else DB_SQLITE
            self['config']['DataBindings'][BINDING]['database'] = db_name
            db_entry = databases.get(db_name) or self['config']['Databases'][db_name]
            if db_name in databases:
                out("EcowittConsoleEmulator: database entry [%s] already exists; leaving it unchanged" % db_name)
            out("EcowittConsoleEmulator: adding binding [%s] -> database %s (%s, same type as the main database)"
                % (BINDING, db_name, db_entry.get('database_type')))
        state = _database_state(cfg, db_name, db_entry)
        if state is True:
            out("EcowittConsoleEmulator: database '%s' already exists; it will be used as it is, not recreated"
                % db_entry.get('database_name'))
        elif state is False:
            out("EcowittConsoleEmulator: database '%s' doesn't exist yet; WeeWX will create it at the next start "
                "with the main database's schema, and copy recent history into it" % db_entry.get('database_name'))
        else:
            out("EcowittConsoleEmulator: couldn't check database '%s' (%s); WeeWX will check at start-up "
                "and create it only if it is missing" % (db_entry.get('database_name'), state))
        return False


def _database_state(cfg, db_name, db_entry):
    """True if the database exists, False if not, or a message if it can't be checked."""
    try:
        import weedb
        import weewx.manager
        probe = {'WEEWX_ROOT': cfg.get('WEEWX_ROOT', ''), 'DatabaseTypes': cfg.get('DatabaseTypes', {}),
                 'Databases': {db_name: dict(db_entry)}}
        db_dict = weewx.manager.get_database_dict_from_config(probe, db_name)
        try:
            weedb.connect(db_dict).close()
            return True
        except weedb.NoDatabaseError:
            return False
    except Exception as e:
        return str(e) or e.__class__.__name__


def _remove_year_charts(cfg):
    """Delete chart_<year>.json in the skin's web folder; returns how many."""
    import glob
    import re
    report = cfg.get('StdReport', {}).get(REPORT, {})
    folder = os.path.join(_web_root(cfg), 'console')
    if report.get('HTML_ROOT'):
        folder = os.path.normpath(os.path.join(cfg.get('WEEWX_ROOT', ''), report['HTML_ROOT']))
    n = 0
    for f in glob.glob(os.path.join(folder, 'chart_*.json')):
        if re.match(r'chart_\d{4}\.json$', os.path.basename(f)):
            try:
                os.remove(f)
                n += 1
            except OSError:
                pass
    return n


def _web_root(cfg):
    return os.path.normpath(os.path.join(cfg.get('WEEWX_ROOT', ''),
                                         cfg.get('StdReport', {}).get('HTML_ROOT', 'public_html')))


def _loop_json_path(cfg, loop):
    """Absolute path of the driver's ecwLoop.json, or None if it isn't enabled."""
    if str(loop.get('enable', 'False')).lower() != 'true':
        return None
    path = os.path.expanduser(str(loop.get('path', LOOP_NAME)))
    if not os.path.isabs(path):
        path = os.path.join(_web_root(cfg), path)
    if path.endswith(os.sep) or os.path.isdir(path) or not path.endswith('.json'):
        path = os.path.join(path, LOOP_NAME)
    return os.path.normpath(path)


def _url_from_page(cfg, loop_path):
    """URL of the loop file relative to the dashboard page, or None if it isn't in the web folder."""
    if not loop_path:
        return None
    web = _web_root(cfg)
    if os.path.commonpath([web, loop_path]) != web:
        return None
    report = cfg.get('StdReport', {}).get(REPORT, {})
    page = os.path.normpath(os.path.join(cfg.get('WEEWX_ROOT', ''), report.get('HTML_ROOT', os.path.join(web, 'console'))))
    return posixpath.join(*os.path.relpath(loop_path, page).split(os.sep))


# The sensors that can be named, as the skin lists them by default:
# section -> [(field, *rest of the entry)]; Channels: temp, humidity, sensor id; others: field, sensor id.
# WN34 probes (soilTemp1-8) aren't among the channels by default; naming one adds it.
SENSOR_SECTIONS = {
    'Channels': [('inTemp', 'inTemp', 'inHumidity', 'wh25')] +
                [('extraTemp%d' % i, 'extraTemp%d' % i, 'extraHumid%d' % i, 'wn31_ch%d' % i) for i in range(1, 9)] +
                [('soilTemp%d' % i, 'soilTemp%d' % i, 'None', 'wn34_ch%d' % i) for i in range(1, 9)],
    'SoilChannels': [('soilMoist%d' % i, 'soilMoist%d' % i, 'wh51_ch%d' % i) for i in range(1, 17)],
    'LeafChannels': [('leafWet%d' % i, 'leafWet%d' % i, 'wn35_ch%d' % i) for i in range(1, 9)],
    'LeakChannels': [('leak_%d' % i, 'leak_%d' % i, 'wh55_ch%d' % i) for i in range(1, 5)],
    'PMChannels': [('pm25_%d' % i, 'pm25_%d' % i, 'wh41_ch%d' % i) for i in range(1, 5)] + [('pm2_5', 'pm2_5', 'wh45')],
}
SENSOR_FIELDS = [r[0] for rows in SENSOR_SECTIONS.values() for r in rows]
SENSOR_DEFAULTS = dict([('inTemp', 'Indoor')] + [('extraTemp%d' % i, 'WN31 CH%d' % i) for i in range(1, 9)] +
                       [('soilTemp%d' % i, 'WN34 CH%d' % i) for i in range(1, 9)] +
                       [('soilMoist%d' % i, 'WH51 CH%d' % i) for i in range(1, 17)] +
                       [('leafWet%d' % i, 'WN35 CH%d' % i) for i in range(1, 9)] +
                       [('leak_%d' % i, '%d' % i) for i in range(1, 5)] +
                       [('pm25_%d' % i, 'CH%d' % i) for i in range(1, 5)] + [('pm2_5', 'WH45')])
SENSOR_DESC = dict([('inTemp', 'Indoor temperature/humidity')] +
                   [('extraTemp%d' % i, 'WN31 temperature/humidity CH%d' % i) for i in range(1, 9)] +
                   [('soilTemp%d' % i, 'WN34 temperature probe CH%d' % i) for i in range(1, 9)] +
                   [('soilMoist%d' % i, 'WH51 soil moisture CH%d' % i) for i in range(1, 17)] +
                   [('leafWet%d' % i, 'WN35 leaf wetness CH%d' % i) for i in range(1, 9)] +
                   [('leak_%d' % i, 'WH55 leak sensor %d' % i) for i in range(1, 5)] +
                   [('pm25_%d' % i, 'WH41/WH43 PM2.5 CH%d' % i) for i in range(1, 5)] + [('pm2_5', 'WH45 air quality')])


def _clean_label(name):
    """A name that weewx.conf can hold as a key: no brackets, '=', '#' or quotes."""
    return ' '.join(''.join(c for c in str(name) if c not in '[]=#"\'').split())


def _current_labels(extras):
    """{field: name} from the [[Channels]], [[SoilChannels]] ... sections already set."""
    out = {}
    for section in SENSOR_SECTIONS:
        for label, spec in (extras.get(section) or {}).items():
            field = (spec if isinstance(spec, (list, tuple)) else str(spec).split(','))[0].strip()
            if field in SENSOR_DEFAULTS:
                out[field] = label
    return out


def _sensors_with_data(cfg, days=30):
    """The sensor fields with readings in the last 30 days, in the main database or the skin's
    own; None if neither can be read."""
    try:
        import time
        import weewx.manager
    except ImportError:
        return None
    found, read_any = set(), False
    for binding in ('wx_binding', BINDING):
        if binding not in cfg.get('DataBindings', {}):
            continue
        try:
            mgr = weewx.manager.open_manager_with_config(cfg, binding)
        except Exception:
            continue
        try:
            read_any = True
            last = mgr.lastGoodStamp() or time.time()
            for f in SENSOR_FIELDS:
                if f in found or f not in mgr.sqlkeys:
                    continue
                row = mgr.getSql("SELECT 1 FROM %s WHERE %s IS NOT NULL AND dateTime > ? LIMIT 1"
                                 % (mgr.table_name, f), (last - days * 86400,))
                if row:
                    found.add(f)
        except Exception:
            pass
        finally:
            mgr.close()
    return [f for f in SENSOR_FIELDS if f in found] if read_any else None


def _ask_text(prompt, default):
    try:
        ans = input("%s [%s]: " % (prompt, default)).strip()
    except EOFError:
        return default
    return ans or default


def _ask(prompt, default, choices):
    while True:
        try:
            ans = input("%s [%s]: " % (prompt, default)).strip().lower()
        except EOFError:
            return default
        if not ans:
            return default
        for c in choices:
            if c.startswith(ans):          # accept the first letter(s)
                return c
        print("Please answer %s." % ' or '.join(choices))
