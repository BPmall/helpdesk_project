/* KAT SERVICE Mobile V1 — แอปช่างภาคสนาม (vanilla JS, hash router) */
(() => {
'use strict';
const CFG = JSON.parse(document.getElementById('cfg').textContent);
const BASE = CFG.base, ME = CFG.me;
const CSRF = document.querySelector('meta[name=csrf-token]').content;
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const view = $('#view'), top = $('#top');
const K = {queue: 'kat_q_' + ME, seen: 'kat_seen_' + ME, spk: 'kat_spk_' + ME, splash: 'kat_splash'};
const store = {
  get(k, d = null) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
};

/* ================= utils ================= */
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const uid = () => (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)).replace(/[^A-Za-z0-9_-]/g, '');
const TZ = {timeZone: 'Asia/Bangkok'};
const fTime = iso => iso ? new Date(iso).toLocaleTimeString('th-TH', {...TZ, hour: '2-digit', minute: '2-digit'}) : '';
const fTimeS = iso => iso ? new Date(iso).toLocaleTimeString('th-TH', {...TZ, hour: '2-digit', minute: '2-digit', second: '2-digit'}) : '';
const fDate = iso => iso ? new Date(iso).toLocaleDateString('th-TH', {...TZ, day: 'numeric', month: 'short', year: 'numeric'}) : '';
const fDT = iso => iso ? `${fDate(iso)} ${fTime(iso)}` : '';
const initials = n => { const p = String(n || '?').trim().split(/\s+/); return (p[0]?.[0] || '') + (p[1]?.[0] || p[0]?.[1] || ''); };
const typeTag = j => `<span class="tag ${esc((j.job_type || '').toLowerCase())}">${esc(j.job_type_label)}</span>`;
const stTag = (code, label) => `<span class="tag st st-${esc(code)}">${esc(label)}</span>`;
const mapsUrl = j => j.lat != null ? `https://www.google.com/maps/dir/?api=1&destination=${j.lat},${j.lng}`
  : j.address ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(j.address)}` : null;

function toast(msg, kind = '', ms = 3200) {
  const el = document.createElement('div');
  el.className = 'toast ' + kind; el.textContent = msg;
  $('#toasts').appendChild(el); setTimeout(() => el.remove(), ms);
}

class NetErr extends Error {}
let lastOk = 0;
async function api(path, {method = 'GET', body = null, form = null} = {}) {
  const headers = {'X-CSRFToken': CSRF, 'Accept': 'application/json'};
  if (body) headers['Content-Type'] = 'application/json';
  let res;
  try {
    res = await fetch(BASE + path, {method, headers, credentials: 'same-origin', body: form || (body ? JSON.stringify(body) : null)});
  } catch (e) { renderNet(true); throw new NetErr('offline'); }
  if (res.redirected && res.url.includes('/login')) { location.href = res.url; throw new Error('login'); }
  let data = {};
  try { data = await res.json(); } catch (e) { if (res.status >= 500) throw new NetErr('server'); }
  if (res.status >= 500) throw new NetErr(data.error || 'server');
  lastOk = Date.now(); renderNet(false);
  return {status: res.status, data};
}
async function apiOk(path, opts, fallbackMsg = 'ทำรายการไม่สำเร็จ') {
  try {
    const r = await api(path, opts);
    if (!r.data.success) { toast(r.data.error || fallbackMsg, 'err', 4500); return null; }
    return r.data;
  } catch (e) { if (e instanceof NetErr) toast('ไม่มีสัญญาณ — ลองใหม่อีกครั้ง', 'err'); return null; }
}

/* ---- offline queue (เฉพาะคำสั่ง JSON) ---- */
const readQ = () => store.get(K.queue, []);
const writeQ = q => { store.set(K.queue, q); renderNet(); };
async function send(path, body, label) {
  body.client_uuid = body.client_uuid || uid();
  body.client_time = body.client_time || new Date().toISOString();
  try { return await api(path, {method: 'POST', body}); }
  catch (e) {
    if (!(e instanceof NetErr)) throw e;
    const q = readQ(); q.push({path, body, label}); writeQ(q);
    toast(`ไม่มีสัญญาณ — เก็บ "${label}" ไว้ส่งอัตโนมัติเมื่อกลับมาออนไลน์`, 'err', 5000);
    return {status: 0, queued: true, data: {}};
  }
}
async function flushQueue() {
  const q = readQ(); if (!q.length) return;
  const rest = [];
  for (const item of q) {
    try {
      const r = await api(item.path, {method: 'POST', body: item.body});
      if (r.status >= 400) toast(`"${item.label}" ส่งไม่สำเร็จ: ${r.data.error || r.status}`, 'err', 6000);
      else toast(`ส่ง "${item.label}" ที่ค้างไว้แล้ว`, 'ok');
    } catch (e) { rest.push(item); }
  }
  writeQ(rest);
  if (rest.length < q.length) loadState();
}
function renderNet(failed) {
  const q = readQ().length, bar = $('#netbar');
  const off = !navigator.onLine || failed;
  bar.classList.toggle('hidden', !off && !q);
  bar.textContent = off ? `ออฟไลน์${q ? ` · รอส่ง ${q} รายการ` : ''}` : `กำลังส่งรายการที่ค้าง ${q} รายการ…`;
}

/* ---- GPS ---- */
function gps(timeout = 12000) {
  return new Promise(resolve => {
    if (!navigator.geolocation) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      p => resolve({lat: +p.coords.latitude.toFixed(6), lng: +p.coords.longitude.toFixed(6), accuracy: Math.round(p.coords.accuracy)}),
      err => { if (err.code === 1) toast('กรุณาอนุญาตการเข้าถึงตำแหน่ง (GPS) ในการตั้งค่าเบราว์เซอร์', 'err', 5000); resolve(null); },
      {enableHighAccuracy: true, timeout, maximumAge: 20000});
  });
}

/* ---- image resize ---- */
function shrink(file, max = 1600, q = 0.82) {
  return new Promise(resolve => {
    const img = new Image(), url = URL.createObjectURL(file);
    img.onload = () => {
      const s = Math.min(1, max / Math.max(img.width, img.height));
      const c = document.createElement('canvas');
      c.width = Math.round(img.width * s); c.height = Math.round(img.height * s);
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      c.toBlob(b => resolve(b || file), 'image/jpeg', q);
    };
    img.onerror = () => { URL.revokeObjectURL(url); resolve(file); };
    img.src = url;
  });
}
function pickImages({multiple = false} = {}) {
  return new Promise(resolve => {
    const input = $('#fileInput');
    input.multiple = multiple; input.value = '';
    input.onchange = () => resolve([...input.files]);
    input.click();
  });
}

/* ---- sheet ---- */
function openSheet(html, bind) {
  $('#sheetBody').innerHTML = html;
  $('#sheet').classList.add('open'); $('#sheetBg').classList.add('open');
  if (bind) bind($('#sheetBody'));
}
function closeSheet() { $('#sheet').classList.remove('open'); $('#sheetBg').classList.remove('open'); }
$('#sheetBg').onclick = closeSheet;

/* ================= state ================= */
const S = {state: null, cart: {}, lastMsgId: 0, unread: 0, autoSpeak: store.get(K.spk, true)};
async function loadState() {
  try {
    const {data} = await api('/api/state');
    if (data.success) { S.state = data; S.lastMsgId = Math.max(S.lastMsgId, 0); }
  } catch (e) { /* offline: ใช้ข้อมูลเดิม */ }
  return S.state;
}
const isOwner = () => !!(S.state && S.state.user.is_owner);

/* ================= router ================= */
let cleanup = [];
const onLeave = fn => cleanup.push(fn);
function parseHash() {
  const h = location.hash.replace(/^#\/?/, '');
  const [path, qs] = h.split('?');
  const [name, arg] = path.split('/');
  return {name: name || '', arg, params: Object.fromEntries(new URLSearchParams(qs || ''))};
}
const go = (hash, replace = false) => { if (replace) location.replace(hash); else location.hash = hash; };

function setTop({title, back = true, right = ''}) {
  if (!title) {
    top.innerHTML = `
      <button class="ib" id="menuBtn" aria-label="เมนู"><i class="fa-solid fa-bars"></i></button>
      <div class="ttl"><div class="wordmark"><span class="k">KAT</span> <span class="s">SERVICE</span></div>
        <small>FIBER RANGER<b>STRIKE TEAM</b></small></div>
      <button class="ib" id="bellBtn" aria-label="แจ้งเตือน"><i class="fa-regular fa-bell"></i>
        <span class="badge-dot ${S.unread ? '' : 'hidden'}" id="topBadge">${S.unread > 9 ? '9+' : S.unread}</span></button>`;
    $('#menuBtn').onclick = openMenu;
    $('#bellBtn').onclick = () => go('#/alerts');
  } else {
    top.innerHTML = `${back ? `<button class="ib" id="backBtn" aria-label="ย้อนกลับ"><i class="fa-solid fa-arrow-left"></i></button>` : '<span style="width:42px"></span>'}
      <h1>${esc(title)}</h1>${right || '<span style="width:42px"></span>'}`;
    if (back) $('#backBtn').onclick = () => (history.length > 1 ? history.back() : go('#/'));
  }
}
function setNav(name) {
  const map = {'': '#/', jobs: '#/jobs', job: '#/jobs', scan: '#/scan', alerts: '#/alerts', profile: '#/profile'};
  $$('#nav button').forEach(b => b.classList.toggle('on', b.dataset.go === map[name]));
}
$$('#nav button').forEach(b => b.onclick = () => go(b.dataset.go));

const SCREENS = {};
async function route() {
  cleanup.forEach(fn => { try { fn(); } catch (e) {} }); cleanup = [];
  closeSheet();
  const {name, arg, params} = parseHash();
  const screen = SCREENS[name] || SCREENS[''];
  setNav(name);
  view.className = ''; view.innerHTML = '';
  window.scrollTo(0, 0);
  try { await screen(arg, params); }
  catch (e) { console.error(e); view.innerHTML = `<div class="empty"><i class="fa-solid fa-triangle-exclamation"></i>เปิดหน้านี้ไม่สำเร็จ</div>`; }
}
window.addEventListener('hashchange', route);

function openMenu() {
  const owner = isOwner();
  const rows = [
    ['#/', 'fa-house', 'หน้าหลัก'], ['#/jobs', 'fa-calendar-check', 'งานของฉัน'], ['#/new', 'fa-square-plus', 'เปิดงานใหม่ (To-Do)'],
    ['#/clock', 'fa-clock', 'ลงเวลาทำงาน'], ['#/stock', 'fa-boxes-stacked', 'สต็อก / ขอเบิกอุปกรณ์'], ['#/requests', 'fa-clipboard-list', 'คำขอเบิกของฉัน'],
    ['#/alerts', 'fa-comments', 'แชททีม / วอ'],
    ...(owner ? [['#/jobs?scope=all', 'fa-file-lines', 'Job Order ทั้งหมด'], ['#/assign', 'fa-users', 'มอบหมายงาน'], ['#/approvals', 'fa-check-double', 'อนุมัติเบิก']] : []),
  ];
  openSheet(`<h3>เมนู</h3>${rows.map(([h, i, t]) => `<button class="linkrow" data-h="${h}"><i class="fa-solid ${i}"></i><span>${t}</span><i class="fa-solid fa-chevron-right"></i></button>`).join('')}
    <a class="linkrow" href="${esc(CFG.urls.dashboard)}"><i class="fa-solid fa-display"></i><span>เปิดหน้าเว็บเต็ม (ออฟฟิศ)</span><i class="fa-solid fa-arrow-up-right-from-square"></i></a>
    <a class="linkrow" href="${esc(CFG.urls.logout)}"><i class="fa-solid fa-right-from-bracket"></i><span>ออกจากระบบ</span></a>`,
  root => $$('[data-h]', root).forEach(b => b.onclick = () => { closeSheet(); go(b.dataset.h); }));
}

/* ================= screens ================= */

/* ---------- หน้าหลัก ---------- */
SCREENS[''] = async () => {
  setTop({});
  const st = S.state || await loadState();
  if (!st) { view.innerHTML = '<div class="empty"><i class="fa-solid fa-wifi"></i>เชื่อมต่อเซิร์ฟเวอร์ไม่ได้</div>'; return; }
  const u = st.user, c = st.counts, owner = u.is_owner, j = st.active_job;
  const greet = `
    <section class="greet">
      <div class="avatar">${esc(initials(u.name))}</div>
      <div><h2>สวัสดีครับ ${owner ? '' : 'ช่าง'}${esc(u.name.split(' ')[0])}</h2>
        <div class="role">${esc(u.role_label)}</div>
        ${st.clock.clocked_in ? `<span class="chip ok"><i class="fa-solid fa-circle"></i>พร้อมปฏิบัติงาน · เข้า ${fTime(st.clock.first_in_at)}</span>`
                              : `<span class="chip off"><i class="fa-regular fa-clock"></i>ยังไม่ลงเวลาเข้างาน</span>`}
      </div>
      ${owner ? '<i class="fa-solid fa-crown crown" aria-hidden="true"></i>' : ''}
    </section>`;
  const stat = (cls, icon, label, n, h) => `<button class="stat ${cls}" data-h="${h}"><i class="fa-solid ${icon}"></i><span class="l">${label}</span><span class="n">${n}</span></button>`;
  const tile = (cls, icon, label, h, badge = 0, extra = '') => `<button class="tile ${cls} ${extra}" data-h="${esc(h)}"><i class="fa-solid ${icon}"></i><span>${label}</span>${badge ? `<span class="badge-dot">${badge}</span>` : ''}</button>`;
  let stats, tiles;
  if (owner) {
    stats = stat('c-blue', 'fa-calendar-days', 'งานวันนี้', c.all_open + c.all_done_today, '#/jobs?scope=all')
          + stat('c-green', 'fa-circle-check', 'เสร็จแล้ว', c.all_done_today, '#/jobs?scope=all&status=done')
          + stat('c-orange', 'fa-clock', 'รอดำเนินการ', c.all_open, '#/jobs?scope=all');
    tiles = `<div class="tiles">
      ${tile('c-red', 'fa-file-circle-plus', 'เปิดงาน<br>(To-Do)', '#/new')}
      ${tile('c-blue', 'fa-users', 'มอบหมายงาน', '#/assign', c.unassigned)}
      ${tile('c-purple', 'fa-file-lines', 'Job Order', '#/jobs?scope=all')}
      ${tile('c-purple', 'fa-tower-broadcast', 'MA Fiber', '#/jobs?scope=all&type=MA_FIBER')}
      ${tile('c-orange', 'fa-screwdriver-wrench', 'งาน PM', '#/jobs?scope=all&type=PM')}
      ${tile('c-green', 'fa-boxes-stacked', 'สต็อก', '#/stock')}
      ${tile('c-blue', 'fa-dolly', 'อนุมัติเบิก', '#/approvals', c.pending_approvals)}
      ${tile('c-pink', 'fa-chart-column', 'รายงาน', 'url:' + CFG.urls.dashboard)}
      ${tile('c-slate', 'fa-gear', 'ตั้งค่า', 'url:' + (CFG.is_admin ? CFG.urls.settings : CFG.urls.profile))}
    </div>`;
  } else {
    stats = stat('c-blue', 'fa-calendar-days', 'งานของฉัน', c.mine_open + c.mine_done_today, '#/jobs')
          + stat('c-orange', 'fa-clock', 'กำลังทำ', c.mine_working, '#/jobs')
          + stat('c-green', 'fa-check', 'เสร็จแล้ว', c.mine_done_today, '#/jobs?status=done');
    tiles = `<div class="tiles">
      ${tile('c-blue', 'fa-clipboard-check', 'รับงาน /<br>งานของฉัน', '#/jobs', st.pending_count)}
      ${tile('c-purple', 'fa-screwdriver-wrench', 'งาน PM', '#/jobs?type=PM')}
      ${tile('c-green', 'fa-clock', 'ลงเวลาทำงาน', '#/clock')}
      ${tile('c-sky', 'fa-camera', 'ถ่ายรูปส่งงาน', 'photo')}
      ${tile('c-orange', 'fa-box-open', 'ขอเบิกอุปกรณ์', '#/stock')}
      ${tile('c-green', 'fa-location-dot', 'นำทางไปหน้างาน', 'nav')}
    </div>`;
  }
  const activeCard = j ? `
    <div class="section-t" style="margin:12px 14px 6px">งานที่กำลังทำ <button class="more" data-h="#/jobs">ทั้งหมด (${st.pending_count}) ›</button></div>
    <button class="card active-job" data-h="#/job/${j.id}" style="width:calc(100% - 24px);text-align:left">
      <div class="t">${typeTag(j)} <small>${esc(j.ref)}</small><b>${esc(j.site_name)}</b><small>${esc(j.title)}</small></div>
      ${stTag(j.field_status, j.field_status_label)}</button>` : '';
  view.innerHTML = `${greet}<div class="stats">${stats}</div>${activeCard}${tiles}
    <div class="tiles two">
      <button class="tile c-red wide" data-h="sos"><i class="fa-solid fa-truck-medical"></i><span>แจ้งเหตุด่วน<br><b>SOS</b></span></button>
      <button class="tile c-purple wide" data-h="url:${esc(CFG.urls.knowledge)}"><i class="fa-solid fa-circle-info"></i><span>คู่มือ /<br>ช่วยเหลือ</span></button>
    </div>`;
  $$('[data-h]', view).forEach(b => b.onclick = () => homeAction(b.dataset.h));
};
function homeAction(h) {
  const j = S.state && S.state.active_job;
  if (h.startsWith('#')) return go(h);
  if (h.startsWith('url:')) { location.href = h.slice(4); return; }
  if (h === 'sos') return sos();
  if (h === 'photo') return j ? go(`#/job/${j.id}?tab=photos`) : toast('ยังไม่มีงานที่กำลังทำ — รับงานก่อนแล้วค่อยถ่ายรูปส่งงาน');
  if (h === 'nav') {
    const url = j && mapsUrl(j);
    return url ? window.open(url, '_blank', 'noopener') : toast(j ? 'งานนี้ยังไม่มีพิกัด/ที่อยู่หน้างาน' : 'ยังไม่มีงานที่กำลังทำ');
  }
}

/* ---------- SOS ---------- */
async function sos() {
  if (!confirm('ยืนยันแจ้งเหตุด่วน (SOS)?\nระบบจะส่งตำแหน่งของคุณให้หัวหน้าและทีมทันที')) return;
  const note = prompt('เหตุการณ์ (ไม่บังคับ) เช่น อุบัติเหตุ / ไฟดูด / รถเสีย') || '';
  toast('กำลังหาตำแหน่งและส่งแจ้งเหตุ…');
  const pos = await gps(10000);
  const j = S.state && S.state.active_job;
  const r = await send('/api/sos', {...(pos || {}), note, job_id: j ? j.id : null}, 'แจ้งเหตุด่วน SOS');
  if (r.queued) return;
  if (r.data.success) toast(pos ? '🚨 ส่งแจ้งเหตุพร้อมตำแหน่งแล้ว' : '🚨 ส่งแจ้งเหตุแล้ว (ไม่มีตำแหน่ง GPS)', 'ok', 6000);
  else toast(r.data.error || 'ส่งไม่สำเร็จ', 'err');
}

/* ---------- รายการงาน ---------- */
SCREENS.jobs = async (_, p) => {
  const owner = isOwner();
  const scope = owner && p.scope === 'all' ? 'all' : 'mine';
  const status = p.status === 'done' ? 'done' : 'open';
  const typeLabel = {MA_FIBER: 'MA Fiber', PM: 'งาน PM', KAT: 'งานซ่อม'}[p.type];
  setTop({title: typeLabel ? `${typeLabel}${scope === 'all' ? '' : 'ของฉัน'}` : scope === 'all' ? 'Job Order' : 'งานของฉัน',
          right: owner ? `<button class="ib" id="addJob" aria-label="เปิดงาน"><i class="fa-solid fa-plus"></i></button>` : ''});
  if (owner) $('#addJob').onclick = () => go('#/new');
  const qs = new URLSearchParams({...p, scope, status});
  view.innerHTML = `<div class="pad">
    <div class="seg" style="margin-bottom:10px">
      <button data-s="open" class="${status === 'open' ? 'on' : ''}">งานค้าง</button>
      <button data-s="done" class="${status === 'done' ? 'on' : ''}">เสร็จแล้ว</button></div>
    <div class="search"><i class="fa-solid fa-magnifying-glass" style="color:var(--muted)"></i>
      <input id="q" placeholder="ค้นหา เลขงาน / ลูกค้า / อาการ" value="${esc(p.q || '')}" enterkeyhint="search"></div>
    <div id="list" style="margin-top:10px"><div class="empty"><i class="fa-solid fa-spinner fa-spin"></i>กำลังโหลด…</div></div></div>`;
  $$('[data-s]', view).forEach(b => b.onclick = () => go('#/jobs?' + new URLSearchParams({...p, status: b.dataset.s})));
  let t;
  const load = async () => {
    qs.set('q', $('#q').value.trim());
    const d = await apiOk('/api/jobs?' + qs);
    if (!d) return;
    $('#list').innerHTML = d.jobs.length ? d.jobs.map(j => `
      <button class="jitem" data-id="${j.id}">
        <div class="r1">${typeTag(j)}<span>${esc(j.ref)}</span>${stTag(j.field_status, j.field_status_label)}</div>
        <div class="r2">${esc(j.site_name)}</div>
        <div class="r1" style="color:var(--text)">${esc(j.title)}</div>
        <div class="r3">${j.appointment_at ? `<span><i class="fa-regular fa-calendar"></i> ${fDT(j.appointment_at)}</span>` : ''}
          ${scope === 'all' ? `<span><i class="fa-solid fa-user-gear"></i> ${esc(j.assignee_name || 'ยังไม่มอบหมาย')}</span>` : ''}
          <span class="prio-${esc(j.priority)}">${esc(j.priority_thai)}</span>
          ${j.photo_count ? `<span><i class="fa-solid fa-image"></i> ${j.photo_count}</span>` : ''}</div>
      </button>`).join('') : `<div class="empty"><i class="fa-regular fa-circle-check"></i>${status === 'open' ? 'ไม่มีงานค้าง' : 'ยังไม่มีงานที่เสร็จ'}</div>`;
    $$('.jitem', view).forEach(b => b.onclick = () => go('#/job/' + b.dataset.id));
  };
  $('#q').oninput = () => { clearTimeout(t); t = setTimeout(load, 350); };
  load();
};

/* ---------- รายละเอียดงาน (Job Order) ---------- */
const ACTION = {
  accept: {label: 'รับงาน', icon: 'fa-hand', cls: 'red', gps: false},
  depart: {label: 'เริ่มเดินทาง', icon: 'fa-paper-plane', cls: 'blue', gps: false},
  arrive: {label: 'ถึงหน้างาน', icon: 'fa-location-dot', cls: 'blue', gps: true},
  finish: {label: 'ปิดงาน', icon: 'fa-check', cls: 'green', gps: false},
};
const STAGES = {before: 'ก่อนดำเนินการ', during: 'ระหว่างดำเนินการ', after: 'หลังดำเนินการ'};

SCREENS.job = async (id, p) => {
  setTop({title: 'Job Order'});
  view.innerHTML = '<div class="empty"><i class="fa-solid fa-spinner fa-spin"></i>กำลังโหลด…</div>';
  const d = await apiOk(`/api/jobs/${+id}`);
  if (!d) { view.innerHTML = '<div class="empty"><i class="fa-solid fa-ban"></i>เปิดใบงานไม่ได้</div>'; return; }
  const j = d.job, tab = p.tab || 'detail';
  setTop({title: `Job Order : ${j.ref}`});
  const nPhotos = Object.values(j.photos).reduce((a, x) => a + x.length, 0);
  const canPhoto = j.can_act || isOwner();
  const maps = mapsUrl(j);
  const kv = (icon, k, v) => v ? `<i class="fa-solid ${icon}"></i><span class="k">${k}</span><span>${v}</span>` : '';
  const firstLine = (j.description || '').split('\n').filter(l => l.trim() && !/^(สาขา|เบอร์ติดต่อ):/.test(l))[0] || j.title;

  let body = '';
  if (tab === 'photos') {
    body = Object.entries(STAGES).map(([k, label]) => `
      <div class="stage"><h4>${label} (${j.photos[k].length} รูป)</h4>
        <div class="thumbs">${j.photos[k].map(ph => `<a class="thumb" href="${esc(ph.url)}" target="_blank"><img loading="lazy" src="${esc(ph.url)}" alt="${label}"></a>`).join('')}
        ${canPhoto && j.field_status !== 'Cancelled' ? `<button class="thumb add" data-stage="${k}"><i class="fa-solid fa-camera"></i>เพิ่มรูป</button>` : ''}</div></div>`).join('')
      + (j.photos.other.length ? `<div class="stage"><h4>อื่น ๆ</h4><div class="thumbs">${j.photos.other.map(ph => `<a class="thumb" href="${esc(ph.url)}" target="_blank"><img loading="lazy" src="${esc(ph.url)}" alt=""></a>`).join('')}</div></div>` : '');
  } else if (tab === 'notes') {
    body = `<div class="card">${j.notes.length ? j.notes.map(n => `<div class="note"><small>${esc(n.by)} · ${fDT(n.at)}</small>${esc(n.body)}</div>`).join('')
      : '<div class="empty" style="padding:20px">ยังไม่มีบันทึกงาน</div>'}</div>`;
  } else {
    const evLabel = {accept: 'รับงาน', depart: 'เริ่มเดินทาง', arrive: 'ถึงหน้างาน', finish: 'ปิดงาน', sos: '🚨 SOS'};
    body = `<div class="card" style="padding:12px 14px;white-space:pre-wrap;font-size:14.5px">${esc(j.description || '-')}</div>
      <div class="section-t">ไทม์ไลน์</div>
      <div class="card"><ul class="tl">${j.timeline.length ? j.timeline.map(e => `<li><time>${fDT(e.at)}</time><span>${evLabel[e.type] || esc(e.type)} · ${esc(e.by)}
        ${e.distance_m != null ? `<br><small style="color:var(--muted)">ห่างหน้างาน ${Math.round(e.distance_m)} ม.</small>` : ''}
        ${e.note ? `<br><small style="color:var(--muted)">"${esc(e.note)}"</small>` : ''}</span></li>`).join('') : '<li>ยังไม่เริ่มงาน</li>'}</ul></div>
      <div class="section-t">อุปกรณ์ที่เบิก ${j.can_act && j.field_status !== 'Done' ? '<button class="more" id="reqForJob">+ ขอเบิกสำหรับงานนี้</button>' : ''}</div>
      <div class="card">${j.stock_requests.length ? j.stock_requests.map(r => `<div class="note" style="display:flex;gap:8px;align-items:center;white-space:normal">
        <span style="flex:1">${esc(r.part_name)} × ${r.quantity} ${esc(r.unit)}<small>${esc(r.requester)} · ${fDT(r.created_at)}</small></span>${stTag(r.status, r.status_label)}</div>`).join('')
        : '<div class="empty" style="padding:16px">ยังไม่มีการเบิก</div>'}</div>`;
  }

  view.className = 'with-actions';
  view.innerHTML = `<div class="pad">
    <div class="status-pill"><span class="st-${esc(j.field_status)}"><i class="fa-solid fa-circle-check"></i>${esc(j.field_status_label)}</span></div>
    <div class="card"><div class="kv" style="padding-top:12px">
      ${kv('fa-building', 'ลูกค้า', `: ${esc(j.site_name)}`)}
      ${kv('fa-location-dot', 'สถานที่', `: ${esc(j.address || (j.lat != null ? `${j.lat}, ${j.lng}` : '-'))}${maps ? ` <a href="${maps}" target="_blank" rel="noopener">นำทาง</a>` : ''}`)}
      ${kv('fa-screwdriver-wrench', 'ประเภท', `: ${esc(j.job_type_label)}`)}
      ${kv('fa-triangle-exclamation', 'อาการ', `: ${esc(firstLine)}`)}
      ${kv('fa-user-gear', 'ผู้รับผิดชอบ', `: ${esc(j.assignee_name || 'ยังไม่มอบหมาย')}`)}
      ${kv('fa-calendar', 'กำหนดเสร็จ', j.appointment_at ? `: ${fDT(j.appointment_at)}` : '')}
      ${kv('fa-phone', 'ผู้ประสานงาน', j.coordinator_name ? `: ${esc(j.coordinator_name)} ${j.coordinator_phone ? `<a href="tel:${esc(j.coordinator_phone)}">${esc(j.coordinator_phone)}</a>` : ''}` : '')}
      ${kv('fa-flag', 'ความสำคัญ', `: <span class="prio-${esc(j.priority)}">${esc(j.priority_thai)}</span>`)}
    </div></div>
    <div class="tabs">
      <button data-tab="detail" class="${tab === 'detail' ? 'on' : ''}">รายละเอียด</button>
      <button data-tab="photos" class="${tab === 'photos' ? 'on' : ''}">รูปภาพ (${nPhotos})</button>
      <button data-tab="notes" class="${tab === 'notes' ? 'on' : ''}">บันทึกงาน</button>
    </div>
    ${body}</div>`;
  $$('[data-tab]', view).forEach(b => b.onclick = () => go(`#/job/${j.id}?tab=${b.dataset.tab}`, true));
  $$('[data-stage]', view).forEach(b => b.onclick = () => addPhotos(j, b.dataset.stage));
  const rq = $('#reqForJob'); if (rq) rq.onclick = () => go(`#/stock?job=${j.id}`);

  // ปุ่มด้านล่าง
  const btns = [];
  if (j.can_act && j.field_status !== 'Done' && j.field_status !== 'Cancelled') {
    btns.push(`<button class="btn blue" id="noteBtn"><i class="fa-solid fa-pen-to-square"></i>อัปเดตรายงาน</button>`);
    if (j.next_action) { const a = ACTION[j.next_action]; btns.push(`<button class="btn ${a.cls}" id="actBtn"><i class="fa-solid ${a.icon}"></i>${a.label}</button>`); }
  } else if (isOwner() && !['Done', 'Cancelled'].includes(j.field_status)) {
    btns.push(`<button class="btn blue" id="noteBtn"><i class="fa-solid fa-pen-to-square"></i>บันทึกงาน</button>`);
    btns.push(`<button class="btn red" id="assignBtn"><i class="fa-solid fa-user-plus"></i>${j.assignee_id ? 'มอบหมายใหม่' : 'มอบหมายงาน'}</button>`);
  } else {
    btns.push(`<button class="btn blue" id="noteBtn"><i class="fa-solid fa-pen-to-square"></i>เพิ่มบันทึก</button>`);
  }
  const bar = document.createElement('div');
  bar.className = 'actions'; bar.innerHTML = `<div class="in">${btns.join('')}</div>`;
  document.body.appendChild(bar); onLeave(() => bar.remove());
  $('#noteBtn', bar).onclick = () => noteSheet(j);
  if ($('#actBtn', bar)) $('#actBtn', bar).onclick = () => jobAction(j, j.next_action);
  if ($('#assignBtn', bar)) $('#assignBtn', bar).onclick = () => assignSheet(j, () => route());
};

async function addPhotos(j, stage) {
  const files = await pickImages({multiple: true});
  if (!files.length) return;
  toast(`กำลังส่งรูป ${files.length} รูป…`);
  const pos = await gps(6000);
  let ok = 0;
  for (const f of files) {
    const fd = new FormData();
    fd.append('photo', await shrink(f), 'photo.jpg');
    fd.append('job_id', j.id); fd.append('stage', stage); fd.append('client_uuid', uid());
    if (pos) { fd.append('lat', pos.lat); fd.append('lng', pos.lng); fd.append('accuracy', pos.accuracy); }
    try { const r = await api('/api/photo', {method: 'POST', form: fd}); if (r.data.success) ok++; else toast(r.data.error, 'err'); }
    catch (e) { toast('ส่งรูปไม่สำเร็จ (ไม่มีสัญญาณ) — ลองใหม่เมื่อมีสัญญาณ', 'err', 5000); break; }
  }
  if (ok) { toast(`บันทึกรูป${STAGES[stage]} ${ok} รูปแล้ว`, 'ok'); go(`#/job/${j.id}?tab=photos`, true); route(); }
}

function noteSheet(j) {
  openSheet(`<h3>อัปเดตรายงาน · ${esc(j.ref)}</h3>
    <textarea class="inp" id="noteBody" placeholder="เช่น ตรวจพบสายไฟเบอร์ขาดช่วงเสา 12 เปลี่ยนหัว SC/UPC แล้ว รอวัดค่า"></textarea>
    <div style="display:flex;gap:10px;margin-top:12px"><button class="btn gray" id="nCancel">ยกเลิก</button><button class="btn blue" id="nSave">บันทึก</button></div>`, root => {
    $('#noteBody', root).focus();
    $('#nCancel', root).onclick = closeSheet;
    $('#nSave', root).onclick = async () => {
      const body = $('#noteBody', root).value.trim(); if (!body) return toast('กรุณาพิมพ์บันทึก', 'err');
      const d = await apiOk(`/api/jobs/${j.id}/note`, {method: 'POST', body: {body}});
      if (d) { closeSheet(); toast('บันทึกแล้ว', 'ok'); go(`#/job/${j.id}?tab=notes`, true); route(); }
    };
  });
}

let acting = false;
async function jobAction(j, action, note) {
  if (acting) return;
  const a = ACTION[action];
  if (action === 'finish' && !confirm(`ยืนยันปิดงาน ${j.ref}?`)) return;
  acting = true;
  try {
    const pos = await gps(a.gps ? 15000 : 6000);
    if (a.gps && !pos) return toast('หาตำแหน่ง GPS ไม่ได้ — ออกไปที่โล่งแล้วลองใหม่', 'err', 5000);
    const body = {...(pos || {})}; if (note) body.note = note;
    const r = await send(`/api/jobs/${j.id}/${action}`, body, a.label);
    if (r.queued) return;
    const d = r.data;
    if (r.status === 409 && d.code === 'outside_geofence') {
      const why = prompt(`${d.error}\nเช่น ทางเข้าอยู่อีกฝั่ง / GPS คลาด`);
      if (why && why.trim()) { acting = false; return jobAction(j, action, why.trim()); }
      return;
    }
    if (r.status === 422 && d.code === 'photo_required') {
      toast(d.error, 'err', 4500); go(`#/job/${j.id}?tab=photos`, true); setTimeout(() => addPhotos(j, 'after'), 400); return;
    }
    if (!d.success) { toast(d.error || 'ทำรายการไม่สำเร็จ', 'err'); return; }
    toast(`${a.label} เรียบร้อย`, 'ok');
    await loadState(); route();
  } finally { acting = false; }
}

async function assignSheet(j, done) {
  const d = await apiOk('/api/technicians'); if (!d) return;
  openSheet(`<h3>มอบหมาย ${esc(j.ref)} · ${esc(j.site_name)}</h3>
    ${d.technicians.map(t => `<button class="linkrow" data-id="${t.id}">
      <i class="fa-solid fa-circle" style="font-size:10px;color:${t.clocked_in ? 'var(--green)' : '#c8ced9'}"></i>
      <span><b>${esc(t.name)}</b><br><small style="color:var(--muted)">${esc(t.role)} · งานค้าง ${t.open_jobs}${t.clocked_in ? ' · ลงเวลาแล้ว' : ''}</small></span>
      ${j.assignee_id === t.id ? '<i class="fa-solid fa-check" style="color:var(--green)"></i>' : '<i class="fa-solid fa-chevron-right"></i>'}</button>`).join('')}`,
  root => $$('[data-id]', root).forEach(b => b.onclick = async () => {
    const r = await apiOk(`/api/jobs/${j.id}/assign`, {method: 'POST', body: {assignee_id: +b.dataset.id}});
    if (r) { closeSheet(); toast(`มอบหมายให้ ${r.job.assignee_name} แล้ว`, 'ok'); loadState(); done && done(); }
  }));
}

/* ---------- เปิดงาน (To-Do) ---------- */
SCREENS.new = async () => {
  setTop({title: 'เปิดงาน (To-Do)'});
  const owner = isOwner();
  const photos = [];   // {blob, url}
  let site = null, sites = [];
  view.className = 'with-actions';
  view.innerHTML = `<form class="pad form" id="f" autocomplete="off">
    <label class="l" for="site">ลูกค้า / สถานที่ <em>*</em></label>
    <div class="inp-ico"><i class="fa-solid fa-building"></i><input class="inp" id="site" placeholder="พิมพ์หรือเลือกชื่อลูกค้า / สถานที่" required></div>
    <div id="sugg" class="sugg hidden"></div>
    <label class="l" for="jtype">ประเภทงาน <em>*</em></label>
    <div class="inp-ico"><i class="fa-solid fa-screwdriver-wrench"></i><select class="inp" id="jtype" required>
      <option value="KAT">งานซ่อม (KAT Service)</option><option value="MA_FIBER">MA Fiber</option><option value="PM">งาน PM (บำรุงรักษาตามรอบ)</option></select></div>
    <label class="l" for="desc">รายละเอียดปัญหา <em>*</em></label>
    <textarea class="inp" id="desc" placeholder="ระบุอาการ / ปัญหา / ความต้องการ" required></textarea>
    <label class="l" for="prio">ความสำคัญ</label>
    <select class="inp" id="prio"><option value="Medium">ปานกลาง</option><option value="High">สูง</option><option value="Critical">วิกฤต</option><option value="Low">ต่ำ</option></select>
    ${owner ? `<label class="l" for="assignee">มอบหมายให้</label><select class="inp" id="assignee"><option value="">— ยังไม่มอบหมาย —</option></select>
      <label class="l" for="appt">กำหนดเสร็จ / วันนัด</label><input class="inp" type="datetime-local" id="appt">` : ''}
    <label class="l">รูปประกอบ (ก่อนดำเนินการ)</label>
    <div class="thumbs" id="thumbs"></div>
    <label class="l" for="coords">พิกัดหน้างาน</label>
    <div class="inp-btn"><div class="inp-ico" style="flex:1"><i class="fa-solid fa-location-dot"></i><input class="inp" id="coords" placeholder="lat, lng" inputmode="decimal"></div>
      <button type="button" id="gpsBtn" aria-label="ใช้ตำแหน่งปัจจุบัน"><i class="fa-solid fa-location-crosshairs"></i></button></div>
    <small id="coordsHint" style="color:var(--muted)"></small>
  </form>`;
  const bar = document.createElement('div'); bar.className = 'actions';
  bar.innerHTML = `<div class="in"><button class="btn gray" id="cancel">ยกเลิก</button><button class="btn red" id="save">บันทึกงาน</button></div>`;
  document.body.appendChild(bar); onLeave(() => { bar.remove(); photos.forEach(p => URL.revokeObjectURL(p.url)); });

  const renderThumbs = () => {
    $('#thumbs').innerHTML = `<button type="button" class="thumb add" id="addPh"><i class="fa-solid fa-camera"></i>เพิ่มรูป</button>`
      + photos.map((p, i) => `<div class="thumb"><img src="${p.url}" alt=""><button type="button" class="x" data-i="${i}" aria-label="ลบรูป"><i class="fa-solid fa-xmark"></i></button></div>`).join('');
    $('#addPh').onclick = async () => {
      for (const f of await pickImages({multiple: true})) { if (photos.length >= 10) break; const blob = await shrink(f); photos.push({blob, url: URL.createObjectURL(blob)}); }
      renderThumbs();
    };
    $$('.x', $('#thumbs')).forEach(b => b.onclick = () => { URL.revokeObjectURL(photos[+b.dataset.i].url); photos.splice(+b.dataset.i, 1); renderThumbs(); });
  };
  renderThumbs();

  const fillGps = async (silent) => {
    $('#coordsHint').textContent = 'กำลังหาตำแหน่ง…';
    const pos = await gps(12000);
    if (pos) { $('#coords').value = `${pos.lat}, ${pos.lng}`; $('#coordsHint').textContent = `ความแม่นยำ ±${pos.accuracy} เมตร`; }
    else $('#coordsHint').textContent = silent ? '' : 'หาตำแหน่งไม่ได้';
  };
  $('#gpsBtn').onclick = () => fillGps(false);

  const siteInput = $('#site'), sugg = $('#sugg');
  const showSugg = () => {
    const q = siteInput.value.trim().toLowerCase();
    const list = sites.filter(s => !q || s.name.toLowerCase().includes(q)).slice(0, 8);
    const exact = sites.some(s => s.name.toLowerCase() === q);
    sugg.innerHTML = list.map(s => `<button type="button" data-id="${s.id}">${esc(s.name)}<small>${esc(s.address || (s.lat != null ? 'มีพิกัดแล้ว' : ''))}</small></button>`).join('')
      + (q && !exact ? `<button type="button" data-new="1"><i class="fa-solid fa-plus"></i> เพิ่มสถานที่ใหม่ "${esc(siteInput.value.trim())}"</button>` : '');
    sugg.classList.toggle('hidden', !sugg.innerHTML);
    $$('button', sugg).forEach(b => b.onmousedown = b.ontouchstart = e => {
      e.preventDefault();
      if (b.dataset.id) {
        site = sites.find(s => s.id === +b.dataset.id); siteInput.value = site.name;
        if (site.lat != null) { $('#coords').value = `${site.lat}, ${site.lng}`; $('#coordsHint').textContent = 'ใช้พิกัดที่บันทึกไว้ของสถานที่นี้'; }
      } else site = null;
      sugg.classList.add('hidden');
    });
  };
  siteInput.oninput = () => { site = null; showSugg(); };
  siteInput.onfocus = showSugg;
  siteInput.onblur = () => setTimeout(() => sugg.classList.add('hidden'), 150);
  apiOk('/api/sites').then(d => { if (d) sites = d.sites; });
  if (owner) apiOk('/api/technicians').then(d => {
    if (d) $('#assignee').insertAdjacentHTML('beforeend', d.technicians.map(t => `<option value="${t.id}">${esc(t.name)} (${esc(t.role)} · ค้าง ${t.open_jobs})</option>`).join(''));
  });
  fillGps(true);

  $('#cancel', bar).onclick = () => history.back();
  $('#save', bar).onclick = async () => {
    const name = siteInput.value.trim(), desc = $('#desc').value.trim();
    if (!name) return toast('กรุณาเลือกลูกค้า / สถานที่', 'err');
    if (!desc) return toast('กรุณาระบุรายละเอียดปัญหา', 'err');
    const fd = new FormData();
    if (site && site.name === name) fd.append('site_id', site.id); else fd.append('site_name', name);
    fd.append('job_type', $('#jtype').value); fd.append('description', desc); fd.append('priority', $('#prio').value);
    const m = $('#coords').value.match(/(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)/);
    if (m) { fd.append('lat', m[1]); fd.append('lng', m[2]); }
    else if ($('#coords').value.trim()) return toast('พิกัดไม่ถูกต้อง ใช้รูปแบบ 13.86, 100.51', 'err');
    if (owner) { fd.append('assignee_id', $('#assignee').value); if ($('#appt').value) fd.append('appointment_at', $('#appt').value); }
    photos.forEach(p => fd.append('photos', p.blob, 'before.jpg'));
    const btn = $('#save', bar); btn.disabled = true; btn.textContent = 'กำลังบันทึก…';
    const d = await apiOk('/api/jobs', {method: 'POST', form: fd});
    btn.disabled = false; btn.textContent = 'บันทึกงาน';
    if (!d) return;
    if (d.photo_errors && d.photo_errors.length) toast(`รูปบางรูปบันทึกไม่ได้: ${d.photo_errors[0]}`, 'err', 5000);
    toast(`เปิดงาน ${d.job.ref} แล้ว`, 'ok');
    await loadState();
    go(`#/job/${d.job.id}`, true);
  };
};

/* ---------- มอบหมายงาน (หัวหน้า) ---------- */
SCREENS.assign = async (_, p) => {
  if (!isOwner()) return go('#/', true);
  setTop({title: 'มอบหมายงาน'});
  const status = p.status === 'open' ? 'open' : 'unassigned';
  view.innerHTML = `<div class="pad"><div class="seg" style="margin-bottom:10px">
    <button data-s="unassigned" class="${status === 'unassigned' ? 'on' : ''}">ยังไม่มอบหมาย</button>
    <button data-s="open" class="${status === 'open' ? 'on' : ''}">งานค้างทั้งหมด</button></div><div id="list"></div></div>`;
  $$('[data-s]', view).forEach(b => b.onclick = () => go('#/assign?status=' + b.dataset.s, true));
  const load = async () => {
    const d = await apiOk(`/api/jobs?scope=all&status=${status}`); if (!d) return;
    $('#list').innerHTML = d.jobs.length ? d.jobs.map(j => `<div class="jitem">
      <div class="r1">${typeTag(j)}<span>${esc(j.ref)}</span>${stTag(j.field_status, j.field_status_label)}</div>
      <div class="r2">${esc(j.site_name)}</div><div class="r1" style="color:var(--text)">${esc(j.title)}</div>
      <div style="display:flex;gap:8px;margin-top:8px;align-items:center">
        <span style="flex:1;font-size:13px;color:var(--muted)"><i class="fa-solid fa-user-gear"></i> ${esc(j.assignee_name || 'ยังไม่มอบหมาย')}</span>
        <button class="btn sm outline" data-open="${j.id}">ดูงาน</button><button class="btn sm red" data-assign="${j.id}">มอบหมาย</button></div></div>`).join('')
      : '<div class="empty"><i class="fa-regular fa-circle-check"></i>ไม่มีงานรอมอบหมาย</div>';
    $$('[data-open]', view).forEach(b => b.onclick = () => go('#/job/' + b.dataset.open));
    $$('[data-assign]', view).forEach(b => b.onclick = () => assignSheet(d.jobs.find(x => x.id === +b.dataset.assign), load));
  };
  load();
};

/* ---------- ลงเวลาทำงาน ---------- */
SCREENS.clock = async () => {
  setTop({title: 'ลงเวลาทำงาน'});
  let info = await apiOk('/api/clock');
  let mode = info && info.clock.clocked_in ? 'clock_out' : 'clock_in', pos = null, gpsErr = null;
  view.className = '';
  view.innerHTML = `<div class="pad">
    <div class="seg green"><button data-m="clock_in">เข้างาน</button><button data-m="clock_out">ออกงาน</button></div>
    <div class="clock-big" id="ck">--:--:--</div><div class="clock-date" id="cd"></div>
    <div class="ring wait" id="ring"><i class="fa-solid fa-location-crosshairs"></i><span id="ringT">กำลังหาตำแหน่ง GPS…</span></div>
    <div class="card gps"><i class="fa-solid fa-location-dot"></i><div class="t"><b>ตำแหน่งปัจจุบัน (GPS)</b><span id="gpsT">—</span><br><small id="gpsA"></small></div>
      <a id="gpsMap" class="hidden" target="_blank" rel="noopener" aria-label="เปิดแผนที่"><i class="fa-solid fa-map-location-dot"></i></a></div>
    <button class="btn green" id="clockBtn" style="width:100%;margin-top:12px;padding:15px;font-size:18px" disabled></button>
    <div class="section-t">ประวัติวันนี้</div><div class="card hist" id="hist"></div></div>`;
  const tick = () => { const n = new Date(); $('#ck').textContent = fTimeS(n.toISOString()); $('#cd').textContent = n.toLocaleDateString('th-TH', {...TZ, weekday: 'long', day: 'numeric', month: 'short', year: 'numeric'}); };
  tick(); const iv = setInterval(tick, 1000); onLeave(() => clearInterval(iv));

  const render = () => {
    const c = info ? info.clock : {clocked_in: false};
    $$('[data-m]', view).forEach(b => b.classList.toggle('on', b.dataset.m === mode));
    const ring = $('#ring'), btn = $('#clockBtn');
    btn.textContent = mode === 'clock_in' ? 'บันทึกเวลาเข้างาน' : 'บันทึกเวลาออกงาน';
    let cls = 'ring', icon = 'fa-check', text = 'พร้อมลงเวลาทำงาน', ok = true;
    if (mode === 'clock_in' && c.clocked_in) { cls += ' wait'; icon = 'fa-user-check'; text = `ลงเวลาเข้างานแล้ว ${fTime(c.first_in_at)} น.`; ok = false; }
    else if (mode === 'clock_out' && !c.clocked_in) { cls += ' wait'; icon = 'fa-circle-info'; text = 'ยังไม่ได้ลงเวลาเข้างาน'; ok = false; }
    else if (gpsErr) { cls += ' bad'; icon = 'fa-location-pin-lock'; text = gpsErr; ok = false; }
    else if (!pos) { cls += ' wait'; icon = 'fa-location-crosshairs'; text = 'กำลังหาตำแหน่ง GPS…'; ok = false; }
    ring.className = cls; ring.innerHTML = `<i class="fa-solid ${icon}"></i><span>${text}</span>`;
    btn.disabled = !ok;
    if (pos) {
      $('#gpsT').textContent = `${pos.lat.toFixed(6)}, ${pos.lng.toFixed(6)}`;
      $('#gpsA').textContent = `ความแม่นยำ: ±${pos.accuracy} เมตร${pos.accuracy > 100 ? ' (ต่ำ — ลองออกไปที่โล่ง)' : ''}`;
      const a = $('#gpsMap'); a.href = `https://maps.google.com/?q=${pos.lat},${pos.lng}`; a.classList.remove('hidden');
    }
    const h = info ? info.history : [];
    $('#hist').innerHTML = h.length ? h.map(e => `<div><i class="fa-regular fa-clock" style="color:${e.type === 'clock_in' ? 'var(--green)' : 'var(--red)'}"></i>
      <span>${e.type === 'clock_in' ? 'เข้างาน' : 'ออกงาน'}</span><time>${fTimeS(e.at)}</time></div>`).join('') : '<div><span style="color:var(--muted)">ยังไม่มีการลงเวลาวันนี้</span></div>';
  };
  $$('[data-m]', view).forEach(b => b.onclick = () => { mode = b.dataset.m; render(); });
  if (navigator.geolocation) {
    const w = navigator.geolocation.watchPosition(
      p => { pos = {lat: p.coords.latitude, lng: p.coords.longitude, accuracy: Math.round(p.coords.accuracy)}; gpsErr = null; render(); },
      e => { gpsErr = e.code === 1 ? 'กรุณาอนุญาตการเข้าถึงตำแหน่ง' : 'หาตำแหน่งไม่ได้ — เปิด GPS'; render(); },
      {enableHighAccuracy: true, maximumAge: 10000, timeout: 20000});
    onLeave(() => navigator.geolocation.clearWatch(w));
  } else gpsErr = 'อุปกรณ์นี้ไม่รองรับ GPS';
  render();
  $('#clockBtn').onclick = async () => {
    if (!pos) return;
    const label = mode === 'clock_in' ? 'ลงเวลาเข้า' : 'ลงเวลาออก';
    if (mode === 'clock_out' && !confirm('ยืนยันลงเวลาออกงาน?')) return;
    $('#clockBtn').disabled = true;
    const r = await send('/api/clock', {type: mode, lat: +pos.lat.toFixed(6), lng: +pos.lng.toFixed(6), accuracy: pos.accuracy}, label);
    if (r.queued) return;
    if (!r.data.success) { toast(r.data.error || 'ลงเวลาไม่สำเร็จ', 'err'); }
    else { toast(`${label} ${fTime(r.data.clock.last_at)} น. เรียบร้อย`, 'ok'); navigator.vibrate && navigator.vibrate(40); }
    info = await apiOk('/api/clock') || info;
    mode = info.clock.clocked_in ? 'clock_out' : 'clock_in';
    loadState(); render();
  };
};

/* ---------- สต็อก / ขอเบิก ---------- */
const partIcon = p => {
  const s = `${p.category} ${p.name} ${p.description || ''}`.toLowerCase();
  if (/กล้อง|camera|cctv|ds-2/.test(s)) return 'fa-video';
  if (/switch|สวิตช์|router|เครือข่าย/.test(s)) return 'fa-network-wired';
  if (/fiber|ไฟเบอร์|patch/.test(s)) return 'fa-bezier-curve';
  if (/lan|utp|สาย/.test(s)) return 'fa-ethernet';
  if (/ไฟ|ปลั๊ก|หลอด/.test(s)) return 'fa-plug';
  if (/หมึก|ink/.test(s)) return 'fa-print';
  return 'fa-box';
};
SCREENS.stock = async (_, p) => {
  setTop({title: 'ตรวจสอบสต็อก', right: `<button class="ib" id="myReq" aria-label="คำขอของฉัน"><i class="fa-solid fa-clipboard-list"></i></button>`});
  $('#myReq').onclick = () => go('#/requests');
  let cat = p.category || '';
  const jobId = p.job ? +p.job : null;
  view.className = 'with-actions';
  view.innerHTML = `<div class="pad">
    <div class="search"><i class="fa-solid fa-magnifying-glass" style="color:var(--muted)"></i>
      <input id="q" placeholder="ค้นหา รหัส / ชื่ออุปกรณ์" value="${esc(p.q || '')}" enterkeyhint="search">
      <button id="scanBtn" aria-label="สแกนบาร์โค้ด"><i class="fa-solid fa-barcode"></i></button></div>
    <div class="chips" id="chips" style="margin-top:10px"></div></div>
    <div id="list" style="background:#fff;border-top:1px solid var(--line)"></div>`;
  const bar = document.createElement('div'); bar.className = 'actions';
  bar.innerHTML = `<div class="in"><button class="btn blue" id="reqBtn"><i class="fa-solid fa-dolly"></i><span id="reqT">ขอเบิกอุปกรณ์</span></button></div>`;
  document.body.appendChild(bar); onLeave(() => bar.remove());
  const cartCount = () => Object.values(S.cart).reduce((a, x) => a + x.qty, 0);
  const renderBar = () => { const n = cartCount(); $('#reqT', bar).textContent = n ? `ขอเบิกอุปกรณ์ (${Object.keys(S.cart).length} รายการ)` : 'ขอเบิกอุปกรณ์'; };
  $('#scanBtn').onclick = () => go('#/scan?for=stock');
  let parts = [];
  const load = async () => {
    const d = await apiOk('/api/stock?' + new URLSearchParams({q: $('#q').value.trim(), category: cat})); if (!d) return;
    parts = d.parts;
    $('#chips').innerHTML = ['', ...d.categories].map(c => `<button data-c="${esc(c)}" class="${c === cat ? 'on' : ''}">${esc(c || 'ทั้งหมด')}</button>`).join('');
    $$('[data-c]', view).forEach(b => b.onclick = () => { cat = b.dataset.c; load(); });
    $('#list').innerHTML = parts.length ? parts.map(x => `<button class="part" data-id="${x.id}">
      <span class="ic"><i class="fa-solid ${partIcon(x)}"></i></span>
      <span class="t"><b>${esc(x.name)}${S.cart[x.id] ? `<span class="incart">×${S.cart[x.id].qty}</span>` : ''}</b><small>${esc(x.description || x.sku || '')}</small><small>${esc(x.category || '')}${x.location ? ' · ' + esc(x.location) : ''}</small></span>
      <span class="qty ${x.low ? 'low' : ''}">คงเหลือ<b>${x.stock_quantity}</b>${esc(x.unit)}</span></button>`).join('')
      : '<div class="empty"><i class="fa-solid fa-box-open"></i>ไม่พบอุปกรณ์</div>';
    $$('.part', view).forEach(b => b.onclick = () => partSheet(parts.find(x => x.id === +b.dataset.id)));
    renderBar();
  };
  const partSheet = part => {
    const cur = S.cart[part.id] ? S.cart[part.id].qty : 1;
    openSheet(`<h3>${esc(part.name)}</h3><p style="margin:-4px 0 12px;color:var(--muted)">${esc(part.sku || '')} · คงเหลือ ${part.stock_quantity} ${esc(part.unit)}</p>
      <div class="stepper"><button id="mi">−</button><input class="inp" id="qv" type="number" min="1" max="${part.stock_quantity}" value="${cur}" inputmode="numeric"><button id="pl">+</button><span>${esc(part.unit)}</span></div>
      <div style="display:flex;gap:10px;margin-top:16px">${S.cart[part.id] ? '<button class="btn gray" id="rm">เอาออก</button>' : ''}<button class="btn blue" id="ok" ${part.stock_quantity ? '' : 'disabled'}>ใส่รายการเบิก</button></div>`, root => {
      const qv = $('#qv', root), clamp = v => Math.max(1, Math.min(part.stock_quantity, v | 0));
      $('#mi', root).onclick = () => qv.value = clamp(+qv.value - 1);
      $('#pl', root).onclick = () => qv.value = clamp(+qv.value + 1);
      $('#ok', root).onclick = () => { S.cart[part.id] = {part, qty: clamp(+qv.value)}; closeSheet(); load(); };
      if ($('#rm', root)) $('#rm', root).onclick = () => { delete S.cart[part.id]; closeSheet(); load(); };
    });
  };
  $('#reqBtn', bar).onclick = () => {
    const items = Object.values(S.cart);
    if (!items.length) return toast('แตะอุปกรณ์ในรายการเพื่อเลือกจำนวนที่จะเบิก');
    const jobs = (S.state && S.state.jobs) || [];
    openSheet(`<h3>ขอเบิกอุปกรณ์</h3>
      ${items.map(x => `<div class="linkrow" style="padding:10px 0"><i class="fa-solid ${partIcon(x.part)}"></i><span>${esc(x.part.name)}</span><b>×${x.qty} ${esc(x.part.unit)}</b></div>`).join('')}
      <label class="l" style="display:block;font-weight:600;margin:12px 0 6px">ใช้กับงาน</label>
      <select class="inp" id="rjob"><option value="">— ไม่ระบุงาน —</option>${jobs.map(j => `<option value="${j.id}" ${j.id === jobId ? 'selected' : ''}>${esc(j.ref)} · ${esc(j.site_name)}</option>`).join('')}</select>
      <label class="l" style="display:block;font-weight:600;margin:12px 0 6px">หมายเหตุ</label>
      <input class="inp" id="rnote" maxlength="300" placeholder="เช่น เปลี่ยนกล้องตัวที่เสีย 2 ตัว">
      <div style="display:flex;gap:10px;margin-top:16px"><button class="btn gray" id="clr">ล้างรายการ</button><button class="btn blue" id="sub">ส่งคำขอ</button></div>`, root => {
      $('#clr', root).onclick = () => { S.cart = {}; closeSheet(); load(); };
      $('#sub', root).onclick = async () => {
        const body = {items: items.map(x => ({part_id: x.part.id, quantity: x.qty})), job_id: +$('#rjob', root).value || null, note: $('#rnote', root).value};
        const d = await apiOk('/api/stock/requests', {method: 'POST', body});
        if (d) { S.cart = {}; closeSheet(); toast('ส่งคำขอเบิกแล้ว รอหัวหน้าอนุมัติ', 'ok'); go('#/requests'); }
      };
    });
  };
  let t; $('#q').oninput = () => { clearTimeout(t); t = setTimeout(load, 300); };
  load();
};

const reqCard = (r, owner) => `<div class="jitem" style="cursor:default">
  <div class="r1"><span>#${r.id}</span>${r.job_ref ? `<span>งาน ${esc(r.job_ref)}</span>` : ''}${stTag(r.status, r.status_label)}</div>
  <div class="r2">${esc(r.part_name)} × ${r.quantity} ${esc(r.unit)}</div>
  <div class="r3"><span><i class="fa-solid fa-user"></i> ${esc(r.requester)}</span><span>${fDT(r.created_at)}</span>
    ${r.status === 'Pending' ? `<span class="${r.stock_quantity < r.quantity ? 'prio-High' : ''}">คงเหลือ ${r.stock_quantity}</span>` : ''}</div>
  ${r.note ? `<div style="font-size:13.5px;margin-top:4px">📝 ${esc(r.note)}</div>` : ''}
  ${r.decider ? `<div style="font-size:12.5px;color:var(--muted);margin-top:4px">${esc(r.status_label)}โดย ${esc(r.decider)} · ${fDT(r.decided_at)}${r.decision_note ? ` — ${esc(r.decision_note)}` : ''}</div>` : ''}
  ${owner && r.status === 'Pending' ? `<div style="display:flex;gap:8px;margin-top:10px"><button class="btn gray sm" style="flex:1" data-rej="${r.id}">ไม่อนุมัติ</button><button class="btn green sm" style="flex:1" data-apv="${r.id}">อนุมัติ</button></div>` : ''}
</div>`;

SCREENS.requests = async () => {
  setTop({title: 'คำขอเบิกของฉัน'});
  view.innerHTML = '<div class="pad" id="list"><div class="empty"><i class="fa-solid fa-spinner fa-spin"></i></div></div>';
  const d = await apiOk('/api/stock/requests'); if (!d) return;
  $('#list').innerHTML = d.requests.length ? d.requests.map(r => reqCard(r, false)).join('') : '<div class="empty"><i class="fa-solid fa-clipboard-list"></i>ยังไม่มีคำขอเบิก</div>';
};

SCREENS.approvals = async (_, p) => {
  if (!isOwner()) return go('#/', true);
  setTop({title: 'อนุมัติเบิก'});
  const status = p.status === 'history' ? 'history' : 'Pending';
  view.innerHTML = `<div class="pad"><div class="seg" style="margin-bottom:10px">
    <button data-s="Pending" class="${status === 'Pending' ? 'on' : ''}">รออนุมัติ</button><button data-s="history" class="${status === 'history' ? 'on' : ''}">ประวัติ</button></div><div id="list"></div></div>`;
  $$('[data-s]', view).forEach(b => b.onclick = () => go('#/approvals?status=' + b.dataset.s, true));
  const load = async () => {
    const d = await apiOk('/api/stock/requests?scope=all' + (status === 'Pending' ? '&status=Pending' : '')); if (!d) return;
    const list = status === 'Pending' ? d.requests : d.requests.filter(r => r.status !== 'Pending');
    $('#list').innerHTML = list.length ? list.map(r => reqCard(r, true)).join('') : '<div class="empty"><i class="fa-regular fa-circle-check"></i>ไม่มีคำขอรออนุมัติ</div>';
    $$('[data-apv]', view).forEach(b => b.onclick = async () => {
      b.disabled = true;
      const r = await apiOk(`/api/stock/requests/${b.dataset.apv}/approve`, {method: 'POST', body: {}});
      if (r) { toast('อนุมัติและตัดสต็อกแล้ว', 'ok'); loadState(); } load();
    });
    $$('[data-rej]', view).forEach(b => b.onclick = async () => {
      const note = prompt('เหตุผลที่ไม่อนุมัติ'); if (note === null) return;
      const r = await apiOk(`/api/stock/requests/${b.dataset.rej}/reject`, {method: 'POST', body: {note}});
      if (r) { toast('ไม่อนุมัติคำขอแล้ว'); loadState(); } load();
    });
  };
  load();
};

/* ---------- สแกน QR / บาร์โค้ด ---------- */
SCREENS.scan = async (_, p) => {
  const forStock = p.for === 'stock';
  setTop({title: forStock ? 'สแกนบาร์โค้ดอุปกรณ์' : 'สแกน QR ใบงาน / อุปกรณ์'});
  view.innerHTML = `<div class="pad">
    <div class="scanbox"><video id="vid" playsinline muted></video></div>
    <p id="scanMsg" style="text-align:center;color:var(--muted)">เล็ง QR Code ให้อยู่ในกรอบ</p>
    <form id="manual" class="search"><input id="code" placeholder="หรือพิมพ์เลขงาน / รหัสอุปกรณ์" enterkeyhint="go"><button aria-label="ค้นหา"><i class="fa-solid fa-arrow-right"></i></button></form>
    ${forStock ? '' : `<button class="btn blue" id="snap" style="width:100%;margin-top:12px"><i class="fa-solid fa-camera"></i>ถ่ายรูปส่งงานแทน</button>`}</div>`;
  const handle = async text => {
    text = String(text).trim(); if (!text) return;
    if (forStock) return go('#/stock?q=' + encodeURIComponent(text), true);
    try { const u = new URL(text); if (u.origin === location.origin) { location.href = u.href; return; } } catch (e) {}
    const m = text.match(/(TK-\d+|JOB-[\w-]+|JO-[\w-]+)/i);
    const d = await apiOk('/api/jobs?' + new URLSearchParams({scope: isOwner() ? 'all' : 'mine', status: 'open', q: m ? m[1] : text}));
    if (d && d.jobs.length) return go('#/job/' + d.jobs[0].id, true);
    toast(`ไม่พบงาน "${m ? m[1] : text}" ในงานค้างของคุณ`, 'err');
  };
  $('#manual').onsubmit = e => { e.preventDefault(); handle($('#code').value); };
  if ($('#snap')) $('#snap').onclick = () => homeAction('photo');
  if (!('BarcodeDetector' in window) || !navigator.mediaDevices) {
    $('#scanMsg').textContent = 'เบราว์เซอร์นี้สแกนในแอปไม่ได้ — ใช้แอปกล้องของมือถือสแกน QR หรือพิมพ์เลขด้านล่าง';
    $('.scanbox').classList.add('hidden'); return;
  }
  let stream, stop = false;
  onLeave(() => { stop = true; stream && stream.getTracks().forEach(t => t.stop()); });
  try {
    stream = await navigator.mediaDevices.getUserMedia({video: {facingMode: 'environment'}});
    if (stop) return stream.getTracks().forEach(t => t.stop());
    const vid = $('#vid'); vid.srcObject = stream; await vid.play();
    const det = new BarcodeDetector({formats: ['qr_code', 'code_128', 'ean_13', 'code_39']});
    const loop = async () => {
      if (stop) return;
      try { const codes = await det.detect(vid); if (codes.length) { navigator.vibrate && navigator.vibrate(60); stop = true; stream.getTracks().forEach(t => t.stop()); return handle(codes[0].rawValue); } } catch (e) {}
      setTimeout(loop, 250);
    };
    loop();
  } catch (e) { $('#scanMsg').textContent = 'เปิดกล้องไม่ได้ — กรุณาอนุญาตการใช้กล้อง หรือพิมพ์เลขด้านล่าง'; }
};

/* ---------- แจ้งเตือน / แชททีม / วอ ---------- */
const player = new Audio(); let playQueue = [], playingEl = null;
function setPlaying(el, on) { if (!el) return; el.querySelector('button i').className = 'fa-solid ' + (on ? 'fa-stop' : 'fa-play'); if (!on) el.querySelector('.bar i').style.width = '0'; }
function playVoice(el) {
  if (playingEl === el && !player.paused) { player.pause(); setPlaying(el, false); playingEl = null; return; }
  setPlaying(playingEl, false); playingEl = el; setPlaying(el, true);
  player.src = el.dataset.src;
  player.play().catch(() => { setPlaying(el, false); toast('แตะปุ่มเล่นเพื่อฟังเสียง'); });
}
player.ontimeupdate = () => { if (playingEl && player.duration) playingEl.querySelector('.bar i').style.width = (100 * player.currentTime / player.duration) + '%'; };
player.onended = () => { setPlaying(playingEl, false); playingEl = null; const next = playQueue.shift(); if (next) { const el = $(`.voice[data-src="${CSS.escape(next)}"]`); if (el) playVoice(el); } };

const msgHtml = m => {
  if (m.kind === 'system') return `<div class="sys ${/SOS/.test(m.body) ? 'sos' : ''}" data-id="${m.id}">${esc(m.body)} · ${fTime(m.created_at)}</div>`;
  let c = esc(m.body);
  if (m.kind === 'voice') c = `<div class="voice" data-src="${esc(m.file_url)}"><button aria-label="เล่นเสียง"><i class="fa-solid fa-play"></i></button><span class="bar"><i></i></span><span>${m.duration_s ? Math.round(m.duration_s) + '″' : ''}</span></div>`;
  if (m.kind === 'image') c = `${esc(m.body || '')}<a href="${esc(m.file_url)}" target="_blank"><img loading="lazy" src="${esc(m.file_url)}" alt="รูป"></a>`;
  return `<div class="msg ${m.mine ? 'mine' : ''}" data-id="${m.id}"><div class="av">${esc(initials(m.user_name))}</div>
    <div class="bub">${m.mine ? '' : `<div class="who">${esc(m.user_name)}</div>`}${c}</div><div class="tm">${fTime(m.created_at)}</div></div>`;
};

SCREENS.alerts = async () => {
  setTop({title: 'แจ้งเตือน / แชททีม', right: `<button class="ib" id="spk" aria-label="เล่นเสียงวออัตโนมัติ"><i class="fa-solid ${S.autoSpeak ? 'fa-volume-high' : 'fa-volume-xmark'}"></i></button>`});
  $('#spk').onclick = () => { S.autoSpeak = !S.autoSpeak; store.set(K.spk, S.autoSpeak); $('#spk').innerHTML = `<i class="fa-solid ${S.autoSpeak ? 'fa-volume-high' : 'fa-volume-xmark'}"></i>`; toast(S.autoSpeak ? 'เปิดเล่นเสียงวออัตโนมัติ' : 'ปิดเล่นเสียงวออัตโนมัติ'); };
  view.style.paddingBottom = 'calc(150px + env(safe-area-inset-bottom,0px))';
  onLeave(() => { view.style.paddingBottom = ''; });
  view.innerHTML = '<div class="feed" id="feed"><div class="empty"><i class="fa-solid fa-spinner fa-spin"></i></div></div>';
  const comp = document.createElement('form'); comp.className = 'composer'; comp.autocomplete = 'off';
  comp.innerHTML = `<div class="in"><button type="button" class="ptt" id="ptt" aria-label="กดค้างเพื่อพูด"><i class="fa-solid fa-microphone"></i></button>
    <input id="msg" maxlength="1000" placeholder="พิมพ์ข้อความ… หรือกดค้างปุ่มแดงเพื่อพูด" aria-label="ข้อความ"><button class="send" aria-label="ส่ง"><i class="fa-solid fa-paper-plane"></i></button></div>`;
  document.body.appendChild(comp); onLeave(() => comp.remove());
  const feed = $('#feed');
  let last = 0, first = true;
  const append = msgs => {
    if (first) feed.innerHTML = msgs.length ? '' : '<div class="empty"><i class="fa-regular fa-comments"></i>ยังไม่มีข้อความ</div>';
    const fresh = msgs.filter(m => m.id > last && !feed.querySelector(`[data-id="${m.id}"]`));
    if (fresh.length) { feed.querySelector('.empty')?.remove(); feed.insertAdjacentHTML('beforeend', fresh.map(msgHtml).join('')); last = Math.max(last, ...fresh.map(m => m.id)); }
    if (!first && S.autoSpeak) fresh.filter(m => !m.mine && m.kind === 'voice').forEach(m => { playQueue.push(m.file_url); if (player.paused && !recording) player.onended(); });
    if (fresh.length) window.scrollTo(0, document.body.scrollHeight);
    first = false; markSeen(last);
  };
  const poll = async () => { try { const {data} = await api('/api/messages' + (last ? `?after=${last}` : '')); if (data.success) append(data.messages); } catch (e) {} };
  await poll();
  const iv = setInterval(() => !document.hidden && poll(), 4000); onLeave(() => clearInterval(iv));
  feed.onclick = e => { const v = e.target.closest('.voice'); if (v) playVoice(v); };
  comp.onsubmit = async e => {
    e.preventDefault();
    const inp = $('#msg', comp), body = inp.value.trim(); if (!body) return;
    inp.value = '';
    const r = await send('/api/messages', {body}, 'ข้อความ');
    if (r.queued) return;
    if (!r.data.success) { inp.value = body; return toast(r.data.error || 'ส่งไม่สำเร็จ', 'err'); }
    append([r.data.message]);
  };
  setupPtt($('#ptt', comp), msg => append([msg]));
};

/* Push-to-talk: กดค้าง = อัด, ปล่อย = ส่ง */
let recording = false;
function setupPtt(btn, onSent) {
  let rec = null, stream = null, chunks = [], t0 = 0, stopTimer = null, releaseTimer = null, uploading = false, hint = null;
  const MIME = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/webm', 'audio/ogg;codecs=opus']
    .find(t => window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
  const showHint = txt => { if (!hint) { hint = document.createElement('div'); hint.className = 'ptt-hint'; document.body.appendChild(hint); } hint.textContent = txt; };
  const hideHint = () => { hint && hint.remove(); hint = null; };
  const release = () => { clearTimeout(releaseTimer); releaseTimer = setTimeout(() => { stream && stream.getTracks().forEach(t => t.stop()); stream = null; }, 30000); };
  onLeave(() => { recording = false; hideHint(); clearTimeout(stopTimer); stream && stream.getTracks().forEach(t => t.stop()); });
  const down = async e => {
    e.preventDefault();
    if (recording || uploading) return;
    if (!window.MediaRecorder || !navigator.mediaDevices) return toast('เบราว์เซอร์นี้ไม่รองรับการอัดเสียง', 'err');
    if (!window.isSecureContext) return toast('การใช้ไมค์ต้องเปิดเว็บผ่าน HTTPS', 'err');
    recording = true; player.pause(); setPlaying(playingEl, false);
    try { clearTimeout(releaseTimer); if (!stream || !stream.active) stream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true}}); }
    catch (err) { recording = false; return toast(err.name === 'NotAllowedError' ? 'กรุณาอนุญาตการใช้ไมโครโฟน' : 'เปิดไมโครโฟนไม่ได้', 'err'); }
    if (!recording) { release(); return; }
    chunks = []; rec = new MediaRecorder(stream, MIME ? {mimeType: MIME, audioBitsPerSecond: 32000} : undefined);
    rec.ondataavailable = ev => ev.data.size && chunks.push(ev.data);
    rec.onstop = upload; rec.start(); t0 = performance.now();
    navigator.vibrate && navigator.vibrate(30);
    btn.classList.add('rec'); showHint('🎙 กำลังพูด… ปล่อยเพื่อส่ง');
    stopTimer = setTimeout(up, 60000);
  };
  const up = () => { if (!recording) return; recording = false; clearTimeout(stopTimer); btn.classList.remove('rec'); hideHint(); if (rec && rec.state === 'recording') rec.stop(); };
  async function upload() {
    const dur = (performance.now() - t0) / 1000; release();
    if (dur < 0.6) return toast('กดค้างไว้แล้วพูด ปล่อยเมื่อพูดจบ');
    const type = rec.mimeType || MIME || 'audio/webm';
    const fd = new FormData();
    fd.append('audio', new Blob(chunks, {type}), 'voice.' + (type.includes('mp4') ? 'm4a' : type.includes('ogg') ? 'ogg' : 'webm'));
    fd.append('duration', dur.toFixed(1)); fd.append('client_uuid', uid());
    uploading = true; btn.classList.add('busy');
    try { const r = await api('/api/voice', {method: 'POST', form: fd}); if (r.data.success) onSent(r.data.message); else toast(r.data.error || 'ส่งเสียงไม่สำเร็จ', 'err'); }
    catch (e) { toast('ส่งเสียงไม่สำเร็จ — ไม่มีสัญญาณ', 'err'); }
    finally { uploading = false; btn.classList.remove('busy'); }
  }
  btn.addEventListener('pointerdown', down);
  ['pointerup', 'pointercancel', 'pointerleave'].forEach(ev => btn.addEventListener(ev, up));
  btn.addEventListener('contextmenu', e => e.preventDefault());
}

/* unread badge */
function markSeen(id) { if (id > store.get(K.seen, 0)) store.set(K.seen, id); S.unread = 0; renderBadge(); }
function renderBadge() {
  const n = S.unread, txt = n > 9 ? '9+' : String(n);
  [$('#navBadge'), $('#topBadge')].forEach(b => { if (b) { b.textContent = txt; b.classList.toggle('hidden', !n); } });
}
async function pollUnread() {
  if (parseHash().name === 'alerts') return;
  const seen = store.get(K.seen, 0);
  try {
    const {data} = await api('/api/messages' + (seen ? `?after=${seen}` : ''));
    if (!data.success) return;
    if (!seen) { const m = data.messages; if (m.length) store.set(K.seen, m[m.length - 1].id); return; }
    const fresh = data.messages.filter(m => !m.mine);
    S.unread = fresh.length; renderBadge();
    const sosMsg = fresh.find(m => m.kind === 'system' && /SOS/.test(m.body));
    if (sosMsg) { toast(sosMsg.body, 'err', 8000); navigator.vibrate && navigator.vibrate([200, 100, 200]); }
  } catch (e) {}
}

/* ---------- โปรไฟล์ ---------- */
SCREENS.profile = async () => {
  setTop({title: 'โปรไฟล์', back: false});
  const st = S.state || await loadState(); if (!st) return;
  const u = st.user;
  view.innerHTML = `<div class="pad"><div class="card profile-card"><div class="avatar">${esc(initials(u.name))}</div>
      <b style="font-size:18px">${esc(u.name)}</b><div style="color:var(--muted)">${esc(u.role_label)}</div>
      ${st.clock.clocked_in ? `<span class="chip ok" style="margin-top:8px"><i class="fa-solid fa-circle"></i>ลงเวลาเข้า ${fTime(st.clock.first_in_at)}</span>` : ''}</div>
    <div class="card" style="margin-top:12px">
      <button class="linkrow" data-h="#/clock"><i class="fa-solid fa-clock"></i><span>ลงเวลาทำงาน</span><i class="fa-solid fa-chevron-right"></i></button>
      <button class="linkrow" data-h="#/requests"><i class="fa-solid fa-clipboard-list"></i><span>คำขอเบิกของฉัน</span><i class="fa-solid fa-chevron-right"></i></button>
      <button class="linkrow" data-h="#/new"><i class="fa-solid fa-square-plus"></i><span>เปิดงานใหม่</span><i class="fa-solid fa-chevron-right"></i></button>
      <a class="linkrow" href="${esc(CFG.urls.profile)}"><i class="fa-solid fa-key"></i><span>แก้ไขโปรไฟล์ / เปลี่ยนรหัสผ่าน</span><i class="fa-solid fa-arrow-up-right-from-square"></i></a>
      <a class="linkrow" href="${esc(CFG.urls.dashboard)}"><i class="fa-solid fa-display"></i><span>เปิดหน้าเว็บเต็ม</span><i class="fa-solid fa-arrow-up-right-from-square"></i></a>
      <a class="linkrow" href="${esc(CFG.urls.logout)}" style="color:var(--red)"><i class="fa-solid fa-right-from-bracket" style="color:var(--red)"></i><span>ออกจากระบบ</span></a>
    </div><p style="text-align:center;color:var(--muted);font-size:12px">KAT SERVICE Mobile V1</p></div>`;
  $$('[data-h]', view).forEach(b => b.onclick = () => go(b.dataset.h));
};

/* ================= boot ================= */
(async () => {
  if (!window.isSecureContext) $('#secureBanner').classList.remove('hidden');
  const splash = $('#splash');
  let showSplash = true;
  try { showSplash = !sessionStorage.getItem(K.splash); sessionStorage.setItem(K.splash, '1'); } catch (e) {}
  const t0 = Date.now();
  if (!showSplash) splash.remove();
  await loadState();
  await route();
  if (showSplash) setTimeout(() => { splash.classList.add('out'); setTimeout(() => splash.remove(), 400); }, Math.max(0, 900 - (Date.now() - t0)));
  renderNet(); flushQueue(); pollUnread();
  setInterval(() => { if (!document.hidden) pollUnread(); }, 8000);
  setInterval(() => { if (!document.hidden) { loadState(); flushQueue(); } }, 30000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) { loadState(); flushQueue(); pollUnread(); } });
  window.addEventListener('online', () => { renderNet(); flushQueue(); });
  window.addEventListener('offline', () => renderNet(true));
})();
})();
