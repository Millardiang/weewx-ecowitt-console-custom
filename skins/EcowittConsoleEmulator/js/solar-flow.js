/*
 * solar-flow.js - the Solar page of weewx-ecowitt-console-custom: weewx-divumwx's
 * solar power-flow diagram, from the files weewx-divumwx already writes. Nothing is
 * added to WeeWX (no service, settings or database).
 *
 * To take it out, remove the two lines that load this file and css/solar-flow.css
 * from index.html.tmpl.
 *
 * Reads (the web addresses tried are DIRS below):
 *   solar_data.json  SolarAssistant's readings (weewx-divumwx's SolarAssistant MQTT
 *                    service), every 10 seconds while the page is open
 *   archive.json     meta.solar_array_watts (PV's share of the array's rating) and
 *                    meta.timezone (station time), when the page opens
 *
 * Signs: grid power + importing / - exporting; battery power + charging / -
 * discharging. Loads: load_power is the total, load_power_essential and
 * load_power_non-essential the two circuits (on this system the two add up to
 * load_power).
 *
 * The Solar button is always on the toolbar; if the files can't be read, the page
 * says which path it tried. (It is named 'solarflow', so no other code hides it.)
 */
(function () {
  'use strict';

  // Web addresses of the folder holding solar_data.json and archive.json: first the
  // dashboard's own folder, then DivumWX's jsondata (not server paths such as /var/www/html/...).
  // Each is tried in turn; the first that answers with JSON is kept.
  var DIRS = ['./', '../divumwx/jsondata/', '/divumwx/jsondata/', '../../divumwx/jsondata/', '/weewx/divumwx/jsondata/'];
  var dir = null, lastErr = '';
  var POLL_MS = 10000;      // as weewx-divumwx's own page
  var STALE_S = 180;        // readings older than this are "not arriving" (divumwx writes every 30 s)
  var MIN_W = 1;
  var C = { pv: '#F28C1B', grid: '#E53935', batt: '#2EA043', inv: '#2B8CEB', ess: '#43A047', non: '#F28C1B' };
  var NAMES = { pv: 'PV Solar', grid: 'Grid', inv: 'Inverter', batt: 'Battery', ess: 'Essential', non: 'Non-Essential' };

  // wide: the full page (weewx-divumwx's layout); compact: phones (its card layout)
  var L = {
    wide: {
      vb: '0 0 1000 600', s: 4, rx: 18,
      wire: { pv: 'M230 300 H390', grid: 'M500 160 V230', gridRev: 'M500 230 V160', batt: 'M500 440 V370',
        battRev: 'M500 370 V440', load: 'M610 300 H790', ess: 'M790 300 V175 H810', non: 'M790 300 V425 H810' },
      pill: { pv: [310, 262], grid: [600, 195], batt: [600, 405], load: [700, 262] },
      box: {
        pv: { r: [30, 210, 200, 180], icon: [130, 255], name: [130, 316], big: [130, 352], sub: [130, 376] },
        grid: { r: [390, 10, 220, 150], icon: [445, 85], name: [530, 48], big: [530, 86], val: [530, 116], sub: [530, 143] },
        inv: { r: [390, 230, 220, 140], icon: [447, 300], name: [535, 280], val: [535, 314], sub: [535, 345] },
        batt: { r: [390, 440, 220, 150], icon: [445, 515], name: [530, 478], big: [530, 516], val: [530, 546], sub: [530, 573] },
        ess: { r: [810, 100, 170, 150], icon: [895, 148], name: [895, 204], big: [895, 238] },
        non: { r: [810, 350, 170, 150], icon: [895, 398], name: [895, 454], big: [895, 488] }
      }
    },
    compact: {
      vb: '0 0 190 175', s: 1, rx: 5,
      wire: { pv: 'M48 87 H67', grid: 'M95 39 V63', gridRev: 'M95 63 V39', batt: 'M95 136 V111',
        battRev: 'M95 111 V136', load: 'M123 87 H134', ess: 'M134 87 V51 H141', non: 'M134 87 V123 H141' },
      pill: null,
      box: {
        pv: { r: [3, 63, 45, 48], icon: [25.5, 76], name: [25.5, 95], big: [25.5, 105] },
        grid: { r: [67, 2, 56, 37], icon: [76, 20.5], name: [101, 11], val: [101, 22], big: [101, 32] },
        inv: { r: [67, 63, 56, 48], icon: [77, 87], name: [102, 80], val: [102, 92], sub: [102, 102] },
        batt: { r: [63, 136, 64, 37], icon: [72, 154.5], name: [101, 144.5], big: [92, 155.5], val: [114, 155.5], sub: [101, 166] },
        ess: { r: [141, 30, 47, 42], icon: [164.5, 41], name: [164.5, 57], big: [164.5, 67] },
        non: { r: [141, 102, 47, 42], icon: [164.5, 113], name: [164.5, 129], big: [164.5, 139] }
      }
    }
  };
  // weewx-divumwx's icons (its compact card's), drawn at 's' times their size
  var G = {
    pv: '<circle r="4.2" fill="currentColor"/><g stroke="currentColor" stroke-width="1.3" stroke-linecap="round">' +
      '<line y1="-6.5" y2="-8.5"/><line y1="6.5" y2="8.5"/><line x1="-6.5" x2="-8.5"/><line x1="6.5" x2="8.5"/>' +
      '<line x1="-4.6" y1="-4.6" x2="-6" y2="-6"/><line x1="4.6" y1="4.6" x2="6" y2="6"/>' +
      '<line x1="-4.6" y1="4.6" x2="-6" y2="6"/><line x1="4.6" y1="-4.6" x2="6" y2="-6"/></g>',
    grid: '<path fill="currentColor" d="M-2.6 -8 h1.6 v3 h2 v-3 h1.6 v3 h1.5 a.8 .8 0 0 1 .8 .8 v3 a3.8 3.8 0 0 1 -3 3.7 v1.7 l1 1.5 h-5.4 l1 -1.5 v-1.7 a3.8 3.8 0 0 1 -3 -3.7 v-3 a.8 .8 0 0 1 .8 -.8 h1.1 z"/>',
    inv: '<g fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="M-6 -4 h3 a2.2 2.2 0 0 1 0 4.4 h-1.7 a2.2 2.2 0 0 0 0 4.4 h3.3"/>' +
      '<rect x=".6" y="1.8" width="3.8" height="5.4" rx="1.1" fill="currentColor" stroke="none"/>' +
      '<line x1="4.4" y1="3.2" x2="6.6" y2="3.2"/><line x1="4.4" y1="5.8" x2="6.6" y2="5.8"/></g>',
    batt: '<rect x="-1.6" y="-8.6" width="3.2" height="1.6" rx=".5" fill="currentColor"/>' +
      '<rect x="-4" y="-7.2" width="8" height="14.6" rx="1.3" fill="none" stroke="currentColor" stroke-width="1.1"/>' +
      '<rect class="sf-lvl" x="-2.8" y="6.2" width="5.6" height="0" rx=".5" fill="currentColor"/>',
    ess: '<path fill="currentColor" d="M0 -6.5 L5 -4.6 V-.5 C5 3.2 2.8 5.5 0 6.7 C-2.8 5.5 -5 3.2 -5 -.5 V-4.6 Z"/>',
    non: '<path fill="currentColor" d="M0 -6.5 L6.5 -.5 H4.6 V6 H1.4 V2 H-1.4 V6 H-4.6 V-.5 H-6.5 Z"/>'
  };
  var TOOL_ICON = '<svg viewBox="0 0 24 24"><circle cx="19.2" cy="3.6" r="2.6" fill="currentColor"/>' +
    '<path fill="currentColor" fill-rule="evenodd" d="M4.2 8.2 H17.2 L21.6 22 H-0.2 Z M6 10 L5.1 14 H10.6 L10.9 10 Z ' +
    'M12.6 10 L12.9 14 H18.5 L17.3 10 Z M4.7 15.7 L3.6 20.2 H10.2 L10.5 15.7 Z M12.9 15.7 L13.2 20.2 H19.9 L18.9 15.7 Z"/></svg>';

  var st = { layout: null, timer: null, data: null, watts: null, tz: null, archAt: 0 };
  var $ = function (id) { return document.getElementById(id); };
  var isNum = function (v) { return typeof v === 'number' && isFinite(v); };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
  function getJSON(url) {
    return fetch(url + (url.indexOf('?') < 0 ? '?' : '&') + '_=' + Date.now(), { cache: 'no-store' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.text().then(function (t) { try { return JSON.parse(t); } catch (e) { throw new Error('not JSON (' + t.slice(0, 40).replace(/\s+/g, ' ') + '...)'); } });
      }, function (e) { throw new Error('network error: ' + e.message); });
  }
  function abs(u) { try { return new URL(u, location.href).href; } catch (e) { return u; } }
  // solar_data.json: use the folder that worked last; if none has, try each in turn
  function getSolar() {
    if (dir) return getJSON(dir + 'solar_data.json').catch(function (e) { lastErr = abs(dir + 'solar_data.json') + ': ' + e.message; dir = null; throw e; });
    var errs = [], seen = {}, i = 0;
    function next() {
      if (i >= DIRS.length) { lastErr = errs.join(' | '); return Promise.reject(new Error(lastErr)); }
      var d = DIRS[i++];
      if (seen[abs(d)]) return next(); seen[abs(d)] = 1;
      return getJSON(d + 'solar_data.json').then(function (j) { dir = d; lastErr = ''; return j; },
        function (e) { errs.push(abs(d + 'solar_data.json') + ': ' + e.message); return next(); });
    }
    return next();
  }
  function open() { var ov = $('overlay'), body = $('ov-body'); return !!(ov && !ov.hidden && body && body.querySelector('.sol[data-solar-flow]')); }

  // ---- station time --------------------------------------------------------
  // weewx-divumwx writes solar_data.json's times in station time without a zone,
  // so compare them with the station's wall clock now.
  function wallNow() {
    try {
      var p = {}; new Intl.DateTimeFormat('en-GB', { timeZone: st.tz || undefined, year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).formatToParts(new Date()).forEach(function (x) { p[x.type] = x.value; });
      return Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second) / 1000;
    } catch (e) { var d = new Date(); return d.getTime() / 1000 - d.getTimezoneOffset() * 60; }
  }
  function wallTime(iso) {        // '2026-10-27T06:59:36.443176' -> seconds, as wall clock
    var m = /^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)/.exec(String(iso || ''));
    return m ? Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]) / 1000 : null;
  }
  function hms(iso) { var m = /T(\d\d:\d\d:\d\d)/.exec(String(iso || '')); return m ? m[1] : '--:--:--'; }

  // ---- readings ---------------------------------------------------------------
  // Find a SolarAssistant reading. Accepts 'solar_assistant/<dev>/<name>/state', the same
  // without '/state', any other topic prefix, a flat '<name>' key, and entries that are
  // either {value: ...} or the bare value. The named device is preferred; otherwise
  // the first device that has the reading.
  function index(d) {
    if (d === st.idxFor) return st.idx;
    var data = (d && (d.data || d.topics || d.values)) || d || {}, idx = {};
    Object.keys(data).forEach(function (k) {
      if (typeof data[k] === 'object' && data[k] !== null && !('value' in data[k])) return;
      var parts = k.split('/').filter(Boolean);
      if (parts[parts.length - 1] === 'state') parts.pop();
      var name = parts.pop(); if (!name) return;
      var dev = parts.length ? parts[parts.length - 1] : '';
      (idx[name] = idx[name] || []).push({ dev: dev, e: data[k] });
    });
    st.idxFor = d; st.idx = idx; return idx;
  }
  function topic(d, dev, name) {
    var list = index(d)[name]; if (!list) return null;
    var hit = list.filter(function (x) { return x.dev === dev; })[0];
    if (!hit && dev === 'total') return null;      // totals only from the 'total' device
    if (!hit) hit = list.filter(function (x) { return x.dev !== 'total'; })[0] || list[0];
    var e = hit.e, v = e !== null && typeof e === 'object' ? e.value : e;
    if (typeof v === 'string' && v.trim() !== '' && !isNaN(+v)) v = +v;
    return v;
  }
  function num(v) { return isNum(v) ? v : null; }
  function values(d) {
    var I = function (k) { return num(topic(d, 'inverter_1', k)); }, T = function (k) { var v = num(topic(d, 'total', k)); return v; };
    var ess = I('load_power_essential'), non = I('load_power_non-essential'), total = I('load_power');
    if (total === null && (ess !== null || non !== null)) total = (ess || 0) + (non || 0);
    var updated = wallTime(d && d.last_updated), age = updated === null ? null : wallNow() - updated;
    var fresh = !!d && (age === null ? d.connected === true : age < STALE_S);
    return {
      pv: I('pv_power') !== null ? I('pv_power') : T('pv_power'),
      grid: I('grid_power'), gridV: I('grid_voltage'), gridHz: I('grid_frequency'),
      batt: T('battery_power') !== null ? T('battery_power') : I('battery_power'),
      soc: T('battery_state_of_charge') !== null ? T('battery_state_of_charge') : I('battery_state_of_charge'),
      ess: ess, non: non, total: total, fresh: fresh, online: fresh && d.connected === true && Object.keys(index(d)).length > 0, age: age,
      mode: topic(d, 'inverter_1', 'device_mode'), work: topic(d, 'inverter_1', 'work_mode'),
      pv1: I('pv_power_1'), pv2: I('pv_power_2'), battV: I('battery_voltage'), battA: I('battery_current'),
      battT: T('battery_temperature'), invT: I('temperature'), loadPct: I('load_percentage'),
      e: { gen: T('pv_energy'), used: T('load_energy'), imp: T('grid_energy_in'), exp: T('grid_energy_out'),
           chg: T('battery_energy_in'), dis: T('battery_energy_out') }
    };
  }

  // ---- drawing ----------------------------------------------------------------
  function svg(Lx) {
    var g = '<svg class="sf sf-' + (Lx === L.wide ? 'wide' : 'compact') + '" viewBox="' + Lx.vb + '" role="img" aria-label="Solar power flow">';
    ['pv', 'grid', 'batt', 'load', 'ess', 'non'].forEach(function (k) { g += '<path class="sf-wire" d="' + Lx.wire[k] + '"/>'; });
    ['pv', 'grid', 'batt', 'load', 'ess', 'non'].forEach(function (k) { g += '<path class="sf-tr off" data-tr="' + k + '"/>'; });
    if (Lx.pill) Object.keys(Lx.pill).forEach(function (k) {
      g += '<g class="sf-pill" transform="translate(' + Lx.pill[k][0] + ' ' + Lx.pill[k][1] + ')"><rect x="-56" y="-22" width="112" height="44" rx="10"/>' +
        '<text y="7" data-v="pill-' + k + '">—</text></g>';
    });
    Object.keys(Lx.box).forEach(function (k) {
      var b = Lx.box[k], t = function (cls, p, key, fill) {
        return p ? '<text class="' + cls + '" x="' + p[0] + '" y="' + p[1] + '" data-v="' + k + '-' + key + '"' + (fill ? ' style="fill:var(--c)"' : '') + '></text>' : '';
      };
      g += '<g class="sf-box idle" data-box="' + k + '" style="--c:' + C[k] + '"><title>' + NAMES[k] + '</title>' +
        '<rect class="sf-base" x="' + b.r[0] + '" y="' + b.r[1] + '" width="' + b.r[2] + '" height="' + b.r[3] + '" rx="' + Lx.rx + '"/>' +
        '<rect class="sf-bg" x="' + b.r[0] + '" y="' + b.r[1] + '" width="' + b.r[2] + '" height="' + b.r[3] + '" rx="' + Lx.rx + '"/>' +
        '<g class="sf-icon" transform="translate(' + b.icon[0] + ' ' + b.icon[1] + ') scale(' + Lx.s + ')">' + G[k] + '</g>' +
        '<text class="sf-name" x="' + b.name[0] + '" y="' + b.name[1] + '">' + NAMES[k] + '</text>' +
        t('sf-big', b.big, 'big', true) + t('sf-val', b.val, 'val', k === 'inv') + t('sf-sub', b.sub, 'sub') + '</g>';
    });
    return g + '</svg>';
  }
  function layout() {
    var body = $('ov-body'); if (!open()) return;
    var Lx = body.clientWidth < 640 ? L.compact : L.wide;
    if (Lx === st.layout) return;
    st.layout = Lx;
    body.querySelector('.sf-wrap').innerHTML = svg(Lx);
    render();
  }
  function W(w) {
    if (!isNum(w)) return '—';
    var a = Math.abs(w);
    return a >= 10000 ? (a / 1000).toFixed(1) + ' kW' : Math.round(a) + ' W';
  }
  function dur(w) { return (2.4 - 1.8 * Math.sqrt(Math.min(Math.abs(w || 0), 5000) / 5000)).toFixed(2) + 's'; }
  function render() {
    if (!open() || !st.layout) return;
    var body = $('ov-body'), d = st.data, v = values(d), Lx = st.layout, Wr = Lx.wire;
    var q = function (sel) { return body.querySelector(sel); };
    var txt = function (key, s, fill) { var el = q('[data-v="' + key + '"]'); if (el) { el.textContent = s; if (fill !== undefined) el.style.fill = fill; } };
    var idle = function (k, on) { var el = q('[data-box="' + k + '"]'); if (el) el.classList.toggle('idle', !!on); };
    var tracer = function (k, on, path, color, w) {
      var el = q('[data-tr="' + k + '"]'); if (!el) return;
      if (!on) { el.classList.add('off'); return; }
      if (el.getAttribute('d') !== path) el.setAttribute('d', path);
      el.style.stroke = color; el.style.setProperty('--dur', dur(w)); el.classList.remove('off');
    };
    // status: when the readings were written, and what the inverter says it is doing
    var stEl = q('.sf-status');
    stEl.querySelector('i').style.background = v.online ? 'var(--good)' : v.fresh ? 'var(--warn)' : 'var(--bad)';
    stEl.querySelector('span').textContent = !d ? 'No SolarAssistant readings. Tried ' + lastErr + ' (set DIRS in js/solar-flow.js).'
      : !v.fresh ? 'SolarAssistant readings are not arriving (last ' + hms(d.last_updated) + ').'
      : !Object.keys(index(d)).length
        ? 'solar_data.json (' + hms(d.last_updated) + ') is being written but holds no SolarAssistant readings (' + (d.message_count || 0) + ' MQTT messages received). DivumWX is not getting anything from SolarAssistant.'
      : [v.pv, v.grid, v.batt, v.total].every(function (x) { return x === null; })
        ? 'solar_data.json (' + hms(d.last_updated) + ') has ' + Object.keys(index(d)).length + ' readings but no pv_power, grid_power, battery_power or load_power yet. Some: ' + Object.keys(index(d)).slice(0, 8).join(', ')
      : 'Updated ' + hms(d.last_updated) + [v.mode, v.work].filter(function (s) { return s && typeof s === 'string'; }).map(function (s) { return ' · ' + s; }).join('');
    if (!v.fresh) v.pv = v.grid = v.batt = v.ess = v.non = v.total = null;
    // PV, with its share of the array's rating
    var pvOn = v.pv !== null && v.pv > MIN_W;
    idle('pv', !pvOn); txt('pv-big', W(v.pv)); txt('pill-pv', W(v.pv));
    txt('pv-sub', isNum(v.pv) && st.watts ? Math.round(v.pv / st.watts * 100) + '% of ' + (st.watts / 1000).toFixed(2) + ' kW' : '');
    tracer('pv', pvOn, Wr.pv, C.pv, v.pv);
    // grid: + import (grid -> inverter), - export (inverter -> grid)
    var gIn = v.grid !== null && v.grid > MIN_W, gOut = v.grid !== null && v.grid < -MIN_W;
    idle('grid', !gIn && !gOut);
    txt('grid-big', v.grid === null ? '—' : gIn ? 'Import' : gOut ? 'Export' : 'Idle', gOut ? C.batt : '');
    txt('grid-val', W(v.grid)); txt('pill-grid', W(v.grid));
    txt('grid-sub', v.gridV === null || !v.fresh ? '' : v.gridV > 100 ? 'Connected' : 'Disconnected', 'var(--c)');
    tracer('grid', gIn || gOut, gIn ? Wr.grid : Wr.gridRev, gIn ? C.grid : C.inv, v.grid);
    // battery: - discharging (battery -> inverter), + charging (inverter -> battery)
    var bDis = v.batt !== null && v.batt < -MIN_W, bChg = v.batt !== null && v.batt > MIN_W;
    idle('batt', v.soc === null && !bDis && !bChg);
    txt('batt-big', v.soc === null ? '—' : Math.round(v.soc) + '%'); txt('batt-val', W(v.batt)); txt('pill-batt', W(v.batt));
    txt('batt-sub', v.batt === null ? '' : bDis ? 'Discharging' : bChg ? 'Charging' : 'Idle', bDis ? '#E58A00' : bChg ? C.inv : 'var(--fg-dim)');
    var lvl = q('[data-box="batt"] .sf-lvl'), f = Math.max(0, Math.min(100, v.soc === null ? 0 : v.soc)) / 100;
    if (lvl) { lvl.setAttribute('height', (12.4 * f).toFixed(2)); lvl.setAttribute('y', (6.2 - 12.4 * f).toFixed(2)); }
    tracer('batt', bDis || bChg, bDis ? Wr.batt : Wr.battRev, bDis ? C.batt : C.inv, v.batt);
    // inverter and the two circuits
    var loadOn = v.total !== null && v.total > MIN_W, essOn = v.ess !== null && v.ess > MIN_W, nonOn = v.non !== null && v.non > MIN_W;
    idle('inv', !v.online);
    txt('inv-val', W(v.total)); txt('pill-load', W(v.total));
    txt('inv-sub', v.online ? 'Online' : 'Offline', v.online ? C.batt : C.grid);
    tracer('load', loadOn, Wr.load, C.inv, v.total);
    idle('ess', !essOn); txt('ess-big', W(v.ess)); tracer('ess', essOn, Wr.ess, C.inv, v.ess);
    idle('non', !nonOn); txt('non-big', W(v.non)); tracer('non', nonOn, Wr.non, C.inv, v.non);
    details(v);
  }
  // today's energy (SolarAssistant's daily counters) and a few more readings
  function details(v) {
    var el = $('ov-body').querySelector('.sol-today'); if (!el) return;
    var ic = function (k, col) {
      var glyph = k === 'batt' ? G.batt.replace('class="sf-lvl" x="-2.8" y="6.2" width="5.6" height="0"', 'x="-2.8" y="-1" width="5.6" height="7.2"') : G[k];
      return '<svg viewBox="-9 -9 18 18" width="30" height="30" style="color:' + col + '">' + glyph + '</svg>';
    };
    var chip = function (icon, label, value, unit) {
      return '<span class="sol-chip">' + icon + '<span><small>' + esc(label) + '</small><b>' + value + (unit ? ' <small>' + unit + '</small>' : '') + '</b></span></span>';
    };
    var k = function (x) { return isNum(x) ? x.toFixed(1) : '—'; }, f1 = function (x, u) { return isNum(x) ? x.toFixed(1) + ' ' + u : null; };
    var e = v.e || {};
    var more = [isNum(v.pv1) || isNum(v.pv2) ? 'PV strings ' + W(v.pv1) + ' / ' + W(v.pv2) : null,
      [f1(v.battV, 'V'), f1(v.battA, 'A'), f1(v.battT, '°C')].filter(Boolean).length ? 'Battery ' + [f1(v.battV, 'V'), f1(v.battA, 'A'), f1(v.battT, '°C')].filter(Boolean).join(', ') : null,
      isNum(v.gridV) ? 'Grid ' + [f1(v.gridV, 'V'), isNum(v.gridHz) ? v.gridHz.toFixed(2) + ' Hz' : null].filter(Boolean).join(', ') : null,
      isNum(v.invT) ? 'Inverter ' + v.invT.toFixed(1) + ' °C' + (isNum(v.loadPct) ? ', load ' + Math.round(v.loadPct) + '%' : '') : null].filter(Boolean);
    el.innerHTML = '<div class="sol-row"><span class="sol-h">Today</span>' +
      chip(ic('pv', C.pv), 'Generated', k(e.gen), 'kWh') + chip(ic('non', C.inv), 'Used', k(e.used), 'kWh') +
      chip(ic('grid', C.grid), 'Grid import', k(e.imp), 'kWh') + chip(ic('grid', C.batt), 'Grid export', k(e.exp), 'kWh') +
      chip(ic('batt', C.batt), 'Battery charged', k(e.chg), 'kWh') + chip(ic('batt', '#E58A00'), 'Battery discharged', k(e.dis), 'kWh') + '</div>' +
      (more.length ? '<div class="sol-more">' + more.map(esc).join(' · ') + '</div>' : '');
  }

  // ---- the page -----------------------------------------------------------------
  function fetchAll(force) {
    getSolar().then(function (d) {
      st.data = d; render();
      if (force || !st.archAt || Date.now() - st.archAt > 600000) {
        st.archAt = Date.now();
        getJSON(dir + 'archive.json').then(function (a) {
          var m = (a && a.meta) || {}, w = parseFloat(m.solar_array_watts);
          st.watts = isFinite(w) && w > 0 ? w : null; st.tz = m.timezone || null; render();
        }).catch(function () { /* the diagram works without it */ });
      }
    }).catch(function () { st.data = null; render(); });
  }
  function show() {
    var ov = $('overlay'), body = $('ov-body'), title = $('ov-title'), tabs = $('ov-tabs');
    if (!ov || !body) return;
    if (!ov.hidden && !open() && $('ov-close')) $('ov-close').click();   // let console.js close its own panel first
    remember(true);
    title.textContent = 'Solar';
    if (tabs) tabs.hidden = true;
    body.className = '';
    var key = '<div class="sf-key">' + [['pv', 'From PV'], ['grid', 'From Grid'], ['batt', 'From Battery'], ['inv', 'From Inverter']].map(function (x) {
      return '<span><i style="background:' + C[x[0]] + '"></i>' + x[1] + '</span>'; }).join('') + '</div>';
    body.innerHTML = '<div class="sol" data-solar-flow><div class="sf-status"><i></i><span></span></div><div class="sf-wrap"></div>' + key +
      '<div class="sol-today"></div><div class="sol-src">SolarAssistant readings from weewx-divumwx</div></div>';
    body.scrollTop = 0;
    ov.hidden = false;
    st.layout = null;
    layout();
    fetchAll(true);
    clearInterval(st.timer);
    st.timer = setInterval(function () {
      if (!open()) { clearInterval(st.timer); st.timer = null; return; }
      fetchAll(false);
    }, POLL_MS);
  }
  window.addEventListener('resize', layout);

  // ---- the toolbar button ------------------------------------------------------
  // Its own name ('solarflow'), so console.js (any version) leaves it alone; and if
  // anything clears or hides it, it is put back.
  function addButton() {
    var bar = $('toolbar'); if (!bar) return null;
    var b = bar.querySelector('[data-act="solarflow"]');
    if (!b) {
      b = document.createElement('button');
      b.setAttribute('data-act', 'solarflow'); b.title = 'Solar';
      b.addEventListener('click', function (ev) { ev.preventDefault(); show(); });
      var after = bar.querySelector('[data-act="records"]') || bar.querySelector('[data-act="graphs"]');
      if (after && after.nextSibling) bar.insertBefore(b, after.nextSibling); else bar.appendChild(b);
    }
    if (!b.querySelector('svg')) b.innerHTML = TOOL_ICON;
    b.hidden = false;
    return b;
  }
  // ---- staying open --------------------------------------------------------------
  // The Solar page stays up until you close it (X, Esc, a tap outside it, or another
  // toolbar page). If anything else takes it down, or the browser reloads the page,
  // it comes back - also when the page is loaded afresh (a kiosk or cast screen that
  // reloads it). #solar in the address opens it directly.
  var KEY = 'ecce-solarflow', userAt = 0;
  function remember(on) {
    try { if (on) localStorage.setItem(KEY, '1'); else localStorage.removeItem(KEY); } catch (e) { /* not kept */ }
    try {
      var h = on ? '#solar' : '';
      if ((location.hash || '') !== h) history.replaceState(null, '', location.pathname + location.search + h);
    } catch (e) { /* not kept */ }
  }
  function remembered() {
    if (/^#solar$/i.test(location.hash || '')) return true;
    try { return localStorage.getItem(KEY) === '1'; } catch (e) { return false; }
  }
  function watch() {
    var ov = $('overlay'), body = $('ov-body'); if (!ov || !body || !window.MutationObserver) return;
    var mark = function () { userAt = Date.now(); };
    if ($('ov-close')) $('ov-close').addEventListener('click', mark, true);
    ov.addEventListener('click', function (e) { if (e.target === ov) mark(); }, true);
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') mark(); }, true);
    var bar = $('toolbar');
    if (bar) bar.addEventListener('click', function (e) { var t = e.target.closest && e.target.closest('[data-act]'); if (t && t.getAttribute('data-act') !== 'solarflow') mark(); }, true);
    var was = open(), pending = null;
    new MutationObserver(function () {
      var now = open();
      if (was && !now && !pending) {
        pending = setTimeout(function () {
          pending = null;
          if (open()) return;
          if (Date.now() - userAt < 1500) { remember(false); return; }
          if (window.console) console.info('solar-flow: the Solar page was replaced by the dashboard; reopening it');
          show();
        }, 50);
      }
      was = now;
    }).observe(document.body, { attributes: true, attributeFilter: ['hidden'], childList: true, subtree: true });
  }
  function start() {
    var b = addButton(); if (!b) return;
    if (window.MutationObserver) new MutationObserver(function () {
      if (b.hidden || !b.querySelector('svg')) addButton();
    }).observe(b, { attributes: true, childList: true });
    watch();
    if (remembered()) setTimeout(show, 300);   // after console.js has drawn the page
  }
  // after console.js has built its toolbar
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { setTimeout(start, 0); });
  else setTimeout(start, 0);
})();
