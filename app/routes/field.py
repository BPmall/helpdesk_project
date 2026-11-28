"""
Field Service — แอปช่างภาคสนาม (FIBER RANGER MA-PM)

หน้าเว็บมือถือ:   GET  /field/
JSON API (session + CSRF header X-CSRFToken):
    GET  /field/api/state                     สถานะรวมสำหรับหน้า Home
    POST /field/api/jobs/<id>/<action>        accept | depart | arrive | finish
    POST /field/api/clock                     ลงเวลาเข้า/ออก (สลับอัตโนมัติ)
    POST /field/api/photo                     อัปโหลดรูปหน้างาน (multipart)
    GET  /field/api/messages?after=<id>       ดึงแชททีม (polling)
    POST /field/api/messages                  ส่งข้อความ
    POST /field/api/voice                     ส่งข้อความเสียง (กดพูด / PTT)
    GET  /field/media/<name>                  ไฟล์รูป/เสียง (ต้องล็อกอิน)
งานฝั่งออฟฟิศ:
    POST /field/dispatch/<ticket_id>          ตั้งค่าข้อมูลหน้างานของ Ticket (Admin/Manager)
เชื่อม CRM (server-to-server, API key):
    POST /field/api/crm/jobs                  CRM ส่งใบงานเข้ามา (upsert ตาม external_ref)
"""
import hmac
import math
import os
import re
import uuid
from datetime import datetime, timedelta

import requests
from flask import (Blueprint, abort, current_app, flash, jsonify, redirect,
                   render_template, request, send_from_directory, url_for)
from flask_login import current_user, login_required

from .. import csrf, db
from ..models import (FieldEvent, FieldJob, FieldSite, SparePart, StockRequest, StockTransaction,
                      SystemConfig, Ticket, TicketComment, TicketExpense, TicketLog, TeamMessage, User)
from ..utils import send_custom_notification

field_bp = Blueprint('field', __name__, url_prefix='/field')

OPEN_TICKET_STATUSES = ('Pending', 'Head_Approved', 'Manager_Approved', 'In_Progress')
PHOTO_EXT = {'jpg', 'jpeg', 'png', 'webp', 'heic'}
VOICE_EXT = {'webm', 'ogg', 'm4a', 'mp4', 'aac', 'wav'}
MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_VOICE_BYTES = 3 * 1024 * 1024
MAX_VOICE_SECONDS = 60
MAX_TEXT_LEN = 1000
CLIENT_UUID_RE = re.compile(r'^[A-Za-z0-9_-]{8,64}$')


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------

def _media_dir():
    path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'field')
    os.makedirs(path, exist_ok=True)
    return path


def _err(message, status=400, **extra):
    return jsonify({'success': False, 'error': message, **extra}), status


def _float(value):
    try:
        f = float(value)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _payload():
    """อ่านได้ทั้ง JSON และ form-data"""
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict()


def _client_uuid(data):
    value = (data.get('client_uuid') or '').strip()
    return value if CLIENT_UUID_RE.match(value) else None


def _parse_iso_utc(raw, naive_offset=timedelta(0)):
    """ISO string → naive UTC datetime. ถ้าไม่มี timezone ให้ถือว่าเป็น UTC+naive_offset"""
    try:
        t = datetime.fromisoformat(str(raw).strip().replace('Z', '+00:00'))
    except ValueError:
        return None
    offset = t.utcoffset() if t.tzinfo is not None else naive_offset
    return t.replace(tzinfo=None) - offset


def _client_time(data):
    """เวลาที่ช่างกดจริงบนเครื่อง (ISO, UTC) — รับเฉพาะช่วง 48 ชม. ย้อนหลังถึงปัจจุบัน"""
    raw = (data.get('client_time') or '').strip()
    t = _parse_iso_utc(raw) if raw else None
    if t is None:
        return None
    now = datetime.utcnow()
    if now - timedelta(hours=48) <= t <= now + timedelta(minutes=5):
        return t
    return None


def haversine_m(lat1, lng1, lat2, lng2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _is_dispatcher(user):
    return user.role in ('Admin', 'Manager')


def _parse_branch(description):
    """ดึง 'สาขา: xxx' ที่หน้าสร้าง Ticket ใส่ไว้ในบรรทัดแรกของรายละเอียด"""
    for line in (description or '').splitlines():
        if line.startswith('สาขา:'):
            return line.split(':', 1)[1].strip() or None
    return None


def get_or_create_field_job(ticket):
    job = ticket.field_job
    if job is None:
        job = FieldJob(ticket_id=ticket.id, site_name=_parse_branch(ticket.description) or ticket.title)
        db.session.add(job)
        db.session.flush()
    return job


def _my_open_tickets(user):
    return (Ticket.query
            .filter(Ticket.assignee_id == user.id, Ticket.status.in_(OPEN_TICKET_STATUSES))
            .order_by(Ticket.created_at.asc()))


def _iso(dt):
    return dt.isoformat() + 'Z' if dt else None


def _job_dict(job):
    t = job.ticket
    photos = job.events.filter_by(event_type='photo').count()
    return {
        'id': job.id,
        'ticket_id': t.id,
        'ticket_number': t.ticket_number,
        'ref': job.external_ref or t.ticket_number,
        'title': t.title,
        'priority': t.priority,
        'priority_thai': t.get_priority_thai(),
        'ticket_status': t.status,
        'ticket_status_thai': t.get_status_thai(),
        'job_type': job.job_type,
        'job_type_label': FieldJob.JOB_TYPES.get(job.job_type, job.job_type),
        'site_id': job.site_id,
        'site_name': job.site_name or t.title,
        'address': job.address,
        'lat': job.lat,
        'lng': job.lng,
        'coordinator_name': job.coordinator_name,
        'coordinator_phone': job.coordinator_phone,
        'appointment_at': _iso(job.appointment_at),
        'assignee_id': t.assignee_id,
        'assignee_name': t.assignee.name if t.assignee else None,
        'field_status': job.field_status,
        'field_status_label': FieldJob.STATUS_LABELS.get(job.field_status, job.field_status),
        'photo_count': photos,
        'next_action': _next_action(job),
        'created_at': _iso(job.created_at),
        'finished_at': _iso(job.finished_at),
        'detail_url': url_for('tickets.ticket_detail', ticket_id=t.id),
    }


def _next_action(job):
    return {
        'Assigned': 'accept',
        'Accepted': 'depart',
        'Traveling': 'arrive',
        'OnSite': 'finish',
    }.get(job.field_status)


def _clock_state(user):
    """สถานะลงเวลาวันนี้ (วันตามเวลาไทย UTC+7)"""
    day_start_utc = _today_start_utc()
    last = (FieldEvent.query
            .filter(FieldEvent.user_id == user.id,
                    FieldEvent.event_type.in_(('clock_in', 'clock_out')),
                    FieldEvent.created_at >= day_start_utc)
            .order_by(FieldEvent.created_at.desc()).first())
    first_in = (FieldEvent.query
                .filter(FieldEvent.user_id == user.id, FieldEvent.event_type == 'clock_in',
                        FieldEvent.created_at >= day_start_utc)
                .order_by(FieldEvent.created_at.asc()).first())
    return {
        'clocked_in': bool(last and last.event_type == 'clock_in'),
        'last_at': last.created_at.isoformat() + 'Z' if last else None,
        'first_in_at': first_in.created_at.isoformat() + 'Z' if first_in else None,
    }


def _message_dict(m):
    return {
        'id': m.id,
        'channel': m.channel,
        'kind': m.kind,
        'body': m.body,
        'file_url': url_for('field.media', name=m.file) if m.file else None,
        'duration_s': m.duration_s,
        'user_id': m.user_id,
        'user_name': m.user.name if m.user else 'ระบบ',
        'mine': m.user_id == current_user.id,
        'created_at': m.created_at.isoformat() + 'Z',
    }


def _post_system_message(text, channel='team'):
    db.session.add(TeamMessage(channel=channel, user_id=current_user.id, kind='system', body=text))


def _notify_external(job, action, event):
    """แจ้ง LINE/Telegram/Email (ตามที่เปิดไว้ในหน้าตั้งค่า) + callback กลับ CRM ถ้าตั้งค่าไว้"""
    label = {'accept': 'รับงาน', 'depart': 'เริ่มเดินทาง', 'arrive': 'ถึงหน้างาน', 'finish': 'ปิดงานหน้างาน'}[action]
    text = (f"🛠 {label}\n📋 {job.external_ref or job.ticket.ticket_number}: {job.site_name or job.ticket.title}\n"
            f"👷 {current_user.name}")
    if event.lat is not None and event.lng is not None:
        text += f"\n📍 https://maps.google.com/?q={event.lat:.6f},{event.lng:.6f}"
    try:
        send_custom_notification(text, SystemConfig.get_notification_config(),
                                 email_subject=f'[Field] {label} {job.ticket.ticket_number}')
    except Exception as e:  # แจ้งเตือนล้มเหลวต้องไม่ทำให้การกดของช่างล้ม
        current_app.logger.warning(f'field notify failed: {e}')

    callback = SystemConfig.get('crm_callback_url', '').strip()
    if callback and job.external_ref:
        try:
            requests.post(callback, timeout=5, headers={'X-API-Key': _crm_api_key() or ''}, json={
                'external_ref': job.external_ref,
                'action': action,
                'field_status': job.field_status,
                'at': event.created_at.isoformat() + 'Z',
                'lat': event.lat, 'lng': event.lng,
                'technician': current_user.username,
            })
        except Exception as e:
            current_app.logger.warning(f'CRM callback failed: {e}')


def _save_upload(file_storage, allowed_ext, max_bytes, prefix):
    if not file_storage or not file_storage.filename:
        return None, 'ไม่พบไฟล์'
    name = file_storage.filename
    ext = name.rsplit('.', 1)[1].lower() if '.' in name else ''
    if not ext:
        # MediaRecorder บางเครื่องส่ง blob มาไม่มีนามสกุล → เดาจาก mimetype
        mt = (file_storage.mimetype or '').split(';')[0]
        ext = {'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'm4a', 'audio/aac': 'aac',
               'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}.get(mt, '')
    if ext not in allowed_ext:
        return None, 'ชนิดไฟล์ไม่รองรับ'
    data = file_storage.read(max_bytes + 1)
    if len(data) > max_bytes:
        return None, f'ไฟล์ใหญ่เกิน {max_bytes // (1024 * 1024)} MB'
    if not data:
        return None, 'ไฟล์ว่าง'
    safe = f"{prefix}_{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(_media_dir(), safe), 'wb') as fh:
        fh.write(data)
    return safe, None


ROLE_LABELS = {'Admin': 'Owner', 'Manager': 'Manager', 'Technician': 'Technician',
               'Vendor': 'Vendor', 'Employee': 'Employee', 'Customer': 'Customer'}
PHOTO_STAGES = {'before': 'ก่อนดำเนินการ', 'during': 'ระหว่างดำเนินการ', 'after': 'หลังดำเนินการ'}
ASSIGNABLE_ROLES = ('Technician', 'Admin', 'Manager', 'Vendor')


def _today_start_utc():
    now_th = datetime.utcnow() + timedelta(hours=7)
    return datetime(now_th.year, now_th.month, now_th.day) - timedelta(hours=7)


def _default_stage(job):
    if job is None:
        return None
    return {'Assigned': 'before', 'Accepted': 'before', 'Traveling': 'before',
            'OnSite': 'during', 'Done': 'after'}.get(job.field_status, 'during')


def _can_view(job):
    return job.ticket.assignee_id == current_user.id or _is_dispatcher(current_user)


def _jobs_query(mine=True, status='open', job_type=None, q=None):
    query = FieldJob.query.join(Ticket, FieldJob.ticket_id == Ticket.id)
    if mine or not _is_dispatcher(current_user):
        query = query.filter(Ticket.assignee_id == current_user.id)
    if status == 'open':
        query = query.filter(Ticket.status.in_(OPEN_TICKET_STATUSES),
                             FieldJob.field_status.notin_(('Done', 'Cancelled')))
    elif status == 'done':
        query = query.filter(FieldJob.field_status == 'Done')
    elif status == 'unassigned':
        query = query.filter(Ticket.assignee_id.is_(None), Ticket.status.in_(OPEN_TICKET_STATUSES))
    if job_type in FieldJob.JOB_TYPES:
        query = query.filter(FieldJob.job_type == job_type)
    if q:
        like = f'%{q}%'
        query = query.filter(db.or_(Ticket.title.ilike(like), Ticket.ticket_number.ilike(like),
                                    FieldJob.site_name.ilike(like), FieldJob.external_ref.ilike(like)))
    return query


def _crm_api_key():
    return os.environ.get('FIELD_CRM_API_KEY') or SystemConfig.get('crm_api_key', '')


# ------------------------------------------------------------------
# หน้าแอป
# ------------------------------------------------------------------

@field_bp.route('/')
@login_required
def app_home():
    # cache-busting ไฟล์ css/js ตามเวลาแก้ไขล่าสุด
    static_dir = os.path.join(current_app.static_folder, 'field')
    asset_v = int(max(os.path.getmtime(os.path.join(static_dir, f)) for f in ('app.css', 'app.js')))
    return render_template('field/app.html', asset_v=asset_v)


@field_bp.route('/manifest.webmanifest')
def manifest():
    resp = jsonify({
        'name': 'KAT SERVICE · Fiber Ranger',
        'short_name': 'KAT SERVICE',
        'start_url': url_for('field.app_home'),
        'scope': url_for('field.app_home'),
        'display': 'standalone',
        'background_color': '#0a1d4a',
        'theme_color': '#0a1d4a',
        'lang': 'th',
        'icons': [{'src': url_for('static', filename='field/logo.png'), 'sizes': '496x324', 'type': 'image/png', 'purpose': 'any'},
                  {'src': url_for('field.icon'), 'sizes': 'any', 'type': 'image/svg+xml', 'purpose': 'any'}],
    })
    resp.mimetype = 'application/manifest+json'
    return resp


@field_bp.route('/icon.svg')
def icon():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">'
           '<rect width="96" height="96" rx="20" fill="#07111f"/>'
           '<path d="M24 66 L48 22 L72 66 Z" fill="none" stroke="#22d3ee" stroke-width="7" stroke-linejoin="round"/>'
           '<path d="M38 60 L58 36" stroke="#ef4444" stroke-width="7" stroke-linecap="round"/></svg>')
    return current_app.response_class(svg, mimetype='image/svg+xml')


@field_bp.route('/media/<path:name>')
@login_required
def media(name):
    if '/' in name or '\\' in name:
        abort(404)
    return send_from_directory(_media_dir(), name, max_age=86400)


# ------------------------------------------------------------------
# API: state
# ------------------------------------------------------------------

@field_bp.route('/api/state')
@login_required
def api_state():
    # สร้าง field_job ให้ Ticket ที่มอบหมายมาจากหน้าเว็บออฟฟิศ (ยังไม่มี field_job)
    for t in _my_open_tickets(current_user).all():
        get_or_create_field_job(t)
    db.session.commit()

    is_owner = _is_dispatcher(current_user)
    order = {'OnSite': 0, 'Traveling': 1, 'Accepted': 2, 'Assigned': 3}
    my_jobs = [j for j in _jobs_query(mine=True, status='open').all() if j.field_status in order]
    my_jobs.sort(key=lambda j: (order[j.field_status], j.appointment_at or datetime.max, j.id))

    selected_id = request.args.get('job', type=int)
    active = next((j for j in my_jobs if j.id == selected_id), None) or (my_jobs[0] if my_jobs else None)
    last_msg = TeamMessage.query.order_by(TeamMessage.id.desc()).first()

    day_start = _today_start_utc()
    mine_done_today = _jobs_query(mine=True, status='done').filter(FieldJob.finished_at >= day_start).count()
    counts = {
        'mine_open': len(my_jobs),
        'mine_working': sum(1 for j in my_jobs if j.field_status in ('Accepted', 'Traveling', 'OnSite')),
        'mine_done_today': mine_done_today,
    }
    if is_owner:
        open_all = _jobs_query(mine=False, status='open').count()
        done_today = _jobs_query(mine=False, status='done').filter(FieldJob.finished_at >= day_start).count()
        counts.update({
            'all_open': open_all,
            'all_done_today': done_today,
            'unassigned': _jobs_query(mine=False, status='unassigned').count(),
            'pending_approvals': StockRequest.query.filter_by(status='Pending').count(),
        })

    return jsonify({
        'success': True,
        'server_time': _iso(datetime.utcnow()),
        'user': {'id': current_user.id, 'name': current_user.name, 'role': current_user.role,
                 'role_label': ROLE_LABELS.get(current_user.role, current_user.role),
                 'initials': current_user.get_initials(), 'is_owner': is_owner},
        'pending_count': len(my_jobs),
        'counts': counts,
        'active_job': _job_dict(active) if active else None,
        'jobs': [_job_dict(j) for j in my_jobs],
        'clock': _clock_state(current_user),
        'last_message_id': last_msg.id if last_msg else 0,
    })


# ------------------------------------------------------------------
# API: job transitions
# ------------------------------------------------------------------

@field_bp.route('/api/jobs/<int:job_id>/<action>', methods=['POST'])
@login_required
def api_job_action(job_id, action):
    if action not in FieldJob.TRANSITIONS:
        return _err('ไม่รู้จักคำสั่งนี้', 404)
    data = _payload()

    cu = _client_uuid(data)
    if cu:
        dup = FieldEvent.query.filter_by(client_uuid=cu).first()
        if dup:  # ส่งซ้ำจากคิว offline → ตอบผลเดิม ไม่ทำซ้ำ
            return jsonify({'success': True, 'duplicate': True, 'job': _job_dict(dup.job) if dup.job else None})

    job = FieldJob.query.get_or_404(job_id)
    ticket = job.ticket
    if ticket.assignee_id != current_user.id:
        return _err('ใบงานนี้ไม่ได้มอบหมายให้คุณ', 403)

    sources, target = FieldJob.TRANSITIONS[action]
    if job.field_status not in sources:
        return _err(f'ทำรายการนี้ไม่ได้ในสถานะ "{FieldJob.STATUS_LABELS.get(job.field_status)}"', 409,
                    job=_job_dict(job))

    lat, lng, acc = _float(data.get('lat')), _float(data.get('lng')), _float(data.get('accuracy'))
    note = (data.get('note') or '').strip()[:500] or None
    distance = None

    if action == 'arrive':
        if lat is None or lng is None:
            return _err('ต้องเปิด GPS เพื่อยืนยันการถึงหน้างาน', 422, code='gps_required')
        if job.lat is not None and job.lng is not None:
            distance = haversine_m(lat, lng, job.lat, job.lng)
            limit = (job.geofence_m or 300) + min(acc or 0, 200)
            if distance > limit and not note:
                return _err(f'ตำแหน่งห่างจากหน้างาน {distance:,.0f} ม. — กรุณาระบุเหตุผล', 409,
                            code='outside_geofence', distance_m=round(distance))
        else:
            # ยังไม่มีพิกัดหน้างาน → เรียนรู้จากจุดที่ช่างกดถึงหน้างานครั้งแรก
            job.lat, job.lng = lat, lng

    if action == 'finish':
        if job.events.filter_by(event_type='photo').count() == 0:
            return _err('ต้องถ่ายรูปหน้างานอย่างน้อย 1 รูปก่อนปิดงาน', 422, code='photo_required')

    when = _client_time(data) or datetime.utcnow()
    event = FieldEvent(user_id=current_user.id, job_id=job.id, event_type=action, lat=lat, lng=lng,
                       accuracy_m=acc, distance_m=distance, note=note, client_uuid=cu,
                       client_time=_client_time(data), created_at=datetime.utcnow())
    db.session.add(event)

    job.field_status = target
    setattr(job, {'accept': 'accepted_at', 'depart': 'depart_at',
                  'arrive': 'arrive_at', 'finish': 'finished_at'}[action], when)

    # sync กับ Ticket เดิม เพื่อให้ Dashboard ออฟฟิศเห็นทันที
    old_status = ticket.status
    if action == 'accept' and ticket.status != 'In_Progress':
        ticket.status = 'In_Progress'
    if action == 'finish':
        ticket.status = 'Resolved'
        ticket.resolved_at = when
    action_th = {'accept': 'รับงาน', 'depart': 'เริ่มเดินทาง', 'arrive': 'ถึงหน้างาน', 'finish': 'ปิดงานหน้างาน'}[action]
    db.session.add(TicketLog(
        ticket_id=ticket.id, actor_id=current_user.id, action=f'{action_th} (แอปช่าง)',
        old_value=old_status if old_status != ticket.status else None,
        new_value=ticket.status if old_status != ticket.status else None,
        comment=note,
    ))
    _post_system_message(f'{current_user.name} · {action_th} · {job.external_ref or ticket.ticket_number} {job.site_name or ""}'.strip())
    db.session.commit()

    _notify_external(job, action, event)
    return jsonify({'success': True, 'job': _job_dict(job)})


# ------------------------------------------------------------------
# API: clock in/out
# ------------------------------------------------------------------

@field_bp.route('/api/clock')
@login_required
def api_clock_today():
    events = (FieldEvent.query
              .filter(FieldEvent.user_id == current_user.id,
                      FieldEvent.event_type.in_(('clock_in', 'clock_out')),
                      FieldEvent.created_at >= _today_start_utc())
              .order_by(FieldEvent.created_at.desc()).all())
    return jsonify({'success': True, 'clock': _clock_state(current_user), 'history': [{
        'type': e.event_type, 'at': _iso(e.client_time or e.created_at),
        'lat': e.lat, 'lng': e.lng, 'accuracy_m': e.accuracy_m} for e in events]})


@field_bp.route('/api/clock', methods=['POST'])
@login_required
def api_clock():
    data = _payload()
    cu = _client_uuid(data)
    if cu and FieldEvent.query.filter_by(client_uuid=cu).first():
        return jsonify({'success': True, 'duplicate': True, 'clock': _clock_state(current_user)})

    lat, lng = _float(data.get('lat')), _float(data.get('lng'))
    if lat is None or lng is None:
        return _err('ต้องเปิด GPS เพื่อลงเวลา', 422, code='gps_required')

    state = _clock_state(current_user)
    wanted = data.get('type')
    if wanted not in ('clock_in', 'clock_out'):
        wanted = 'clock_out' if state['clocked_in'] else 'clock_in'   # ไม่ระบุ = สลับอัตโนมัติ
    if wanted == 'clock_in' and state['clocked_in']:
        return _err('ลงเวลาเข้างานไปแล้ว', 409, code='already_in', clock=state)
    if wanted == 'clock_out' and not state['clocked_in']:
        return _err('ยังไม่ได้ลงเวลาเข้างาน', 409, code='not_in', clock=state)

    db.session.add(FieldEvent(user_id=current_user.id, event_type=wanted, lat=lat, lng=lng,
                              accuracy_m=_float(data.get('accuracy')), client_uuid=cu,
                              client_time=_client_time(data)))
    db.session.commit()
    return jsonify({'success': True, 'event': wanted, 'clock': _clock_state(current_user)})


# ------------------------------------------------------------------
# API: photo
# ------------------------------------------------------------------

def _store_photo(file_storage, job, stage, lat=None, lng=None, accuracy=None, note=None, client_uuid=None):
    name, error = _save_upload(file_storage, PHOTO_EXT, MAX_PHOTO_BYTES, 'photo')
    if error:
        return None, error
    ev = FieldEvent(user_id=current_user.id, job_id=job.id if job else None, event_type='photo',
                    stage=stage, lat=lat, lng=lng, accuracy_m=accuracy, photo=name, note=note,
                    client_uuid=client_uuid)
    db.session.add(ev)
    return ev, None


@field_bp.route('/api/photo', methods=['POST'])
@login_required
def api_photo():
    job_id = request.form.get('job_id', type=int)
    job = None
    if job_id:
        job = FieldJob.query.get_or_404(job_id)
        if not _can_view(job):
            return _err('ใบงานนี้ไม่ได้มอบหมายให้คุณ', 403)

    cu = _client_uuid(request.form)
    if cu and FieldEvent.query.filter_by(client_uuid=cu).first():
        return jsonify({'success': True, 'duplicate': True})

    stage = request.form.get('stage')
    if stage not in PHOTO_STAGES:
        stage = _default_stage(job)
    ev, error = _store_photo(request.files.get('photo'), job, stage,
                             _float(request.form.get('lat')), _float(request.form.get('lng')),
                             _float(request.form.get('accuracy')),
                             (request.form.get('note') or '').strip()[:500] or None, cu)
    if error:
        return _err(error)
    label = f'รูป{PHOTO_STAGES[stage]} {job.external_ref or job.ticket.ticket_number}' if job else 'รูปหน้างาน'
    db.session.add(TeamMessage(channel='team', user_id=current_user.id, kind='image', file=ev.photo, body=label))
    db.session.commit()
    return jsonify({'success': True, 'url': url_for('field.media', name=ev.photo), 'stage': stage,
                    'job': _job_dict(job) if job else None})


# ------------------------------------------------------------------
# API: team chat + voice (PTT)
# ------------------------------------------------------------------

@field_bp.route('/api/messages')
@login_required
def api_messages():
    after = request.args.get('after', 0, type=int)
    q = TeamMessage.query.filter(TeamMessage.channel == 'team')
    if after:
        msgs = q.filter(TeamMessage.id > after).order_by(TeamMessage.id.asc()).limit(100).all()
    else:
        msgs = list(reversed(q.order_by(TeamMessage.id.desc()).limit(30).all()))
    return jsonify({'success': True, 'messages': [_message_dict(m) for m in msgs]})


@field_bp.route('/api/messages', methods=['POST'])
@login_required
def api_send_message():
    data = _payload()
    body = (data.get('body') or '').strip()
    if not body:
        return _err('ข้อความว่าง')
    if len(body) > MAX_TEXT_LEN:
        return _err(f'ข้อความยาวเกิน {MAX_TEXT_LEN} ตัวอักษร')
    cu = _client_uuid(data)
    if cu:
        dup = TeamMessage.query.filter_by(client_uuid=cu).first()
        if dup:
            return jsonify({'success': True, 'duplicate': True, 'message': _message_dict(dup)})
    m = TeamMessage(channel='team', user_id=current_user.id, kind='text', body=body, client_uuid=cu)
    db.session.add(m)
    db.session.commit()
    return jsonify({'success': True, 'message': _message_dict(m)}), 201


@field_bp.route('/api/voice', methods=['POST'])
@login_required
def api_voice():
    cu = _client_uuid(request.form)
    if cu:
        dup = TeamMessage.query.filter_by(client_uuid=cu).first()
        if dup:
            return jsonify({'success': True, 'duplicate': True, 'message': _message_dict(dup)})
    duration = _float(request.form.get('duration'))
    if duration is not None and (duration < 0.3 or duration > MAX_VOICE_SECONDS + 1):
        return _err('ความยาวเสียงต้องอยู่ระหว่าง 0.3–60 วินาที')
    name, error = _save_upload(request.files.get('audio'), VOICE_EXT, MAX_VOICE_BYTES, 'voice')
    if error:
        return _err(error)
    m = TeamMessage(channel='team', user_id=current_user.id, kind='voice', file=name,
                    duration_s=duration, client_uuid=cu)
    db.session.add(m)
    db.session.commit()
    return jsonify({'success': True, 'message': _message_dict(m)}), 201


# ------------------------------------------------------------------
# ฝั่งออฟฟิศ: ตั้งค่าข้อมูลหน้างานให้ Ticket (dispatch)
# ------------------------------------------------------------------

@field_bp.route('/dispatch/<int:ticket_id>', methods=['POST'])
@login_required
def dispatch(ticket_id):
    if not _is_dispatcher(current_user):
        flash('เฉพาะ Admin/Manager เท่านั้น', 'danger')
        return redirect(url_for('tickets.ticket_detail', ticket_id=ticket_id))
    ticket = Ticket.query.get_or_404(ticket_id)
    job = get_or_create_field_job(ticket)
    f = request.form
    job_type = f.get('job_type', job.job_type)
    job.job_type = job_type if job_type in FieldJob.JOB_TYPES else job.job_type
    job.site_name = f.get('site_name', '').strip()[:200] or job.site_name
    job.address = f.get('address', '').strip()[:300] or None
    job.coordinator_name = f.get('coordinator_name', '').strip()[:100] or None
    job.coordinator_phone = f.get('coordinator_phone', '').strip()[:30] or None

    latlng = f.get('latlng', '').strip()
    if latlng:
        parts = [p.strip() for p in latlng.split(',')]
        lat, lng = (_float(parts[0]), _float(parts[1])) if len(parts) == 2 else (None, None)
        if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
            flash('พิกัดไม่ถูกต้อง ใช้รูปแบบ 13.8621, 100.5144', 'danger')
            return redirect(url_for('tickets.ticket_detail', ticket_id=ticket_id))
        job.lat, job.lng = lat, lng
    geofence = f.get('geofence_m', type=int)
    if geofence:
        job.geofence_m = max(50, min(geofence, 5000))
    appt = f.get('appointment_at', '').strip()
    if appt:
        try:  # input datetime-local เป็นเวลาไทย → เก็บเป็น UTC
            job.appointment_at = datetime.fromisoformat(appt) - timedelta(hours=7)
        except ValueError:
            flash('รูปแบบวันนัดไม่ถูกต้อง', 'warning')
    db.session.add(TicketLog(ticket_id=ticket.id, actor_id=current_user.id, action='ตั้งค่าข้อมูลหน้างาน'))
    db.session.commit()
    flash('บันทึกข้อมูลหน้างานเรียบร้อย', 'success')
    return redirect(url_for('tickets.ticket_detail', ticket_id=ticket_id))


# ------------------------------------------------------------------
# CRM → ระบบนี้ (server-to-server)
# ------------------------------------------------------------------

@field_bp.route('/api/crm/jobs', methods=['POST'])
@csrf.exempt
def crm_upsert_job():
    expected = _crm_api_key()
    if not expected:
        return _err('CRM integration is disabled (set FIELD_CRM_API_KEY)', 503)
    if not hmac.compare_digest(request.headers.get('X-API-Key', ''), expected):
        return _err('unauthorized', 401)

    data = request.get_json(silent=True) or {}
    ref = (data.get('external_ref') or '').strip()[:50]
    title = (data.get('title') or '').strip()[:200]
    if not ref or not title:
        return _err('external_ref and title are required')

    assignee = None
    if data.get('assignee_username'):
        assignee = User.query.filter_by(username=data['assignee_username']).first()
        if not assignee:
            return _err('assignee_username not found', 422)
    requester = User.query.filter_by(role='Admin').order_by(User.id.asc()).first()
    if not requester:
        return _err('no Admin user to own CRM tickets', 500)

    job = FieldJob.query.filter_by(external_ref=ref).first()
    created = job is None
    if created:
        ticket = Ticket(ticket_number=Ticket.generate_ticket_number(), title=title,
                        description=(data.get('description') or '').strip(),
                        priority=data.get('priority') if data.get('priority') in ('Low', 'Medium', 'High', 'Critical') else 'Medium',
                        requester_id=requester.id, status='Manager_Approved')
        db.session.add(ticket)
        db.session.flush()
        job = FieldJob(ticket_id=ticket.id, external_ref=ref)
        db.session.add(job)
        db.session.add(TicketLog(ticket_id=ticket.id, actor_id=requester.id, action=f'รับใบงานจาก CRM ({ref})',
                                 new_value='Manager_Approved'))
    else:
        ticket = job.ticket
        ticket.title = title
        if data.get('description') is not None:
            ticket.description = data['description']

    if assignee and ticket.assignee_id != assignee.id:
        ticket.assignee_id = assignee.id
        if job.field_status not in ('Done', 'Cancelled'):
            job.field_status = 'Assigned'
        db.session.add(TicketLog(ticket_id=ticket.id, actor_id=requester.id, action='มอบหมายงาน (CRM)',
                                 new_value=assignee.name))

    if data.get('job_type') in FieldJob.JOB_TYPES:
        job.job_type = data['job_type']
    for key in ('site_name', 'address', 'coordinator_name', 'coordinator_phone'):
        if data.get(key) is not None:
            setattr(job, key, str(data[key]).strip() or None)
    lat, lng = _float(data.get('lat')), _float(data.get('lng'))
    if lat is not None and lng is not None:
        job.lat, job.lng = lat, lng
    if data.get('appointment_at'):
        # ไม่มี timezone → ถือเป็นเวลาไทย
        job.appointment_at = _parse_iso_utc(data['appointment_at'], naive_offset=timedelta(hours=7))
    if data.get('cancelled'):
        job.field_status = 'Cancelled'
        ticket.status = 'Rejected'

    db.session.commit()
    return jsonify({'success': True, 'created': created, 'job': {
        'id': job.id, 'ticket_number': ticket.ticket_number, 'external_ref': ref,
        'field_status': job.field_status}}), 201 if created else 200


# ==================================================================
# KAT SERVICE Mobile V1 — ใบงาน / เปิดงาน / มอบหมาย / สต๊อก / SOS
# ==================================================================

def _owner_required():
    if not _is_dispatcher(current_user):
        return _err('เฉพาะหัวหน้างาน (Admin/Manager) เท่านั้น', 403)
    return None


@field_bp.route('/api/jobs')
@login_required
def api_jobs():
    scope = request.args.get('scope', 'mine')
    status = request.args.get('status', 'open')
    if status not in ('open', 'done', 'unassigned'):
        status = 'open'
    q = (request.args.get('q') or '').strip()[:100] or None
    query = _jobs_query(mine=(scope != 'all'), status=status, job_type=request.args.get('type'), q=q)
    if status == 'done':
        query = query.order_by(FieldJob.finished_at.desc())
    else:
        query = query.order_by(FieldJob.appointment_at.is_(None), FieldJob.appointment_at.asc(), FieldJob.id.desc())
    return jsonify({'success': True, 'jobs': [_job_dict(j) for j in query.limit(100).all()]})


@field_bp.route('/api/jobs/<int:job_id>')
@login_required
def api_job_detail(job_id):
    job = FieldJob.query.get_or_404(job_id)
    if not _can_view(job):
        return _err('ใบงานนี้ไม่ได้มอบหมายให้คุณ', 403)
    t = job.ticket
    photos = {k: [] for k in PHOTO_STAGES}
    photos['other'] = []
    timeline = []
    for ev in job.events.all():
        if ev.event_type == 'photo':
            photos.get(ev.stage or 'other', photos['other']).append({
                'id': ev.id, 'url': url_for('field.media', name=ev.photo), 'at': _iso(ev.created_at),
                'by': ev.user.name, 'note': ev.note})
        else:
            timeline.append({'type': ev.event_type, 'at': _iso(ev.client_time or ev.created_at),
                             'by': ev.user.name, 'lat': ev.lat, 'lng': ev.lng,
                             'distance_m': ev.distance_m, 'note': ev.note})
    notes = [{'id': c.id, 'by': c.user.name, 'body': c.message, 'at': _iso(c.created_at)}
             for c in t.comments.all()]
    requests_ = [_stock_request_dict(r) for r in
                 StockRequest.query.filter_by(job_id=job.id).order_by(StockRequest.id.desc()).all()]
    data = _job_dict(job)
    data.update({'description': t.description, 'photos': photos, 'timeline': timeline,
                 'notes': notes, 'stock_requests': requests_,
                 'can_act': t.assignee_id == current_user.id,
                 'stages': PHOTO_STAGES})
    return jsonify({'success': True, 'job': data})


@field_bp.route('/api/jobs', methods=['POST'])
@login_required
def api_job_create():
    """เปิดงาน (To-Do): เลือกลูกค้า/สถานที่ + ประเภท + อาการ + รูปก่อนดำเนินการ + พิกัด"""
    f = request.form
    description = (f.get('description') or '').strip()
    if not description:
        return _err('กรุณาระบุรายละเอียดปัญหา')
    job_type = f.get('job_type') if f.get('job_type') in FieldJob.JOB_TYPES else None
    if not job_type:
        return _err('กรุณาเลือกประเภทงาน')

    site = None
    if f.get('site_id', type=int):
        site = db.session.get(FieldSite, f.get('site_id', type=int))
        if not site or not site.is_active:
            return _err('ไม่พบลูกค้า/สถานที่')
    else:
        site_name = (f.get('site_name') or '').strip()[:200]
        if not site_name:
            return _err('กรุณาเลือกหรือพิมพ์ชื่อลูกค้า/สถานที่')
        site = FieldSite.query.filter(db.func.lower(FieldSite.name) == site_name.lower()).first()
        if not site:
            site = FieldSite(name=site_name, address=(f.get('address') or '').strip()[:300] or None)
            db.session.add(site)
            db.session.flush()

    lat, lng = _float(f.get('lat')), _float(f.get('lng'))
    if lat is not None and lng is not None and site.lat is None:
        site.lat, site.lng = lat, lng   # สถานที่ใหม่ → จำพิกัดไว้ใช้ครั้งต่อไป

    is_owner = _is_dispatcher(current_user)
    assignee_id = current_user.id
    if is_owner:
        assignee_id = f.get('assignee_id', type=int) or None
        if assignee_id:
            a = db.session.get(User, assignee_id)
            if not a or a.role not in ASSIGNABLE_ROLES or a.is_active_user is False:
                return _err('ไม่พบช่างที่เลือก')

    priority = f.get('priority') if f.get('priority') in ('Low', 'Medium', 'High', 'Critical') else 'Medium'
    title = (f.get('title') or '').strip()[:200] or f'{FieldJob.JOB_TYPES[job_type]} — {site.name}'
    ticket = Ticket(ticket_number=Ticket.generate_ticket_number(), title=title, description=description,
                    priority=priority, requester_id=current_user.id, assignee_id=assignee_id,
                    status='Manager_Approved' if is_owner else 'Pending')
    db.session.add(ticket)
    db.session.flush()
    job = FieldJob(ticket_id=ticket.id, site_id=site.id, job_type=job_type, site_name=site.name,
                   address=site.address, lat=lat if lat is not None else site.lat,
                   lng=lng if lng is not None else site.lng,
                   coordinator_name=site.contact_name, coordinator_phone=site.contact_phone)
    appt = (f.get('appointment_at') or '').strip()
    if appt:
        job.appointment_at = _parse_iso_utc(appt, naive_offset=timedelta(hours=7))
    db.session.add(job)
    db.session.flush()
    db.session.add(TicketLog(ticket_id=ticket.id, actor_id=current_user.id, action='เปิดงาน (แอปช่าง)',
                             new_value=ticket.status))

    errors = []
    for fs in request.files.getlist('photos')[:10]:
        _, error = _store_photo(fs, job, 'before', lat, lng)
        if error:
            errors.append(error)
    _post_system_message(f'{current_user.name} เปิดงาน {ticket.ticket_number} · {site.name}')
    db.session.commit()
    try:
        send_custom_notification(f'🆕 เปิดงาน {ticket.ticket_number}\n🏢 {site.name}\n📋 {description[:200]}\n👷 {current_user.name}',
                                 SystemConfig.get_notification_config(), email_subject=f'[Field] เปิดงาน {ticket.ticket_number}')
    except Exception as e:
        current_app.logger.warning(f'notify failed: {e}')
    return jsonify({'success': True, 'job': _job_dict(job), 'photo_errors': errors}), 201


@field_bp.route('/api/jobs/<int:job_id>/assign', methods=['POST'])
@login_required
def api_job_assign(job_id):
    denied = _owner_required()
    if denied:
        return denied
    job = FieldJob.query.get_or_404(job_id)
    data = _payload()
    user = db.session.get(User, int(data.get('assignee_id') or 0))
    if not user or user.role not in ASSIGNABLE_ROLES or user.is_active_user is False:
        return _err('ไม่พบช่างที่เลือก')
    t = job.ticket
    if t.status not in OPEN_TICKET_STATUSES or job.field_status in ('Done', 'Cancelled'):
        return _err('งานนี้ปิดไปแล้ว', 409)
    t.assignee_id = user.id
    job.field_status = 'Assigned'
    if t.status == 'Pending':
        t.status = 'Manager_Approved'   # หัวหน้ามอบหมาย = อนุมัติให้ออกงาน
    db.session.add(TicketLog(ticket_id=t.id, actor_id=current_user.id, action='มอบหมายงาน (แอป)', new_value=user.name))
    _post_system_message(f'มอบหมาย {t.ticket_number} · {job.site_name or t.title} ให้ {user.name}')
    db.session.commit()
    if user.line_user_id:
        try:
            from ..utils import send_line_message
            cfg = SystemConfig.get_notification_config()
            if cfg.get('line_enabled') == '1' and cfg.get('line_token'):
                send_line_message(cfg['line_token'], user.line_user_id,
                                  f'📌 งานใหม่ {t.ticket_number}\n🏢 {job.site_name or t.title}\nเปิดแอป: {url_for("field.app_home", _external=True)}')
        except Exception as e:
            current_app.logger.warning(f'LINE notify failed: {e}')
    return jsonify({'success': True, 'job': _job_dict(job)})


@field_bp.route('/api/jobs/<int:job_id>/note', methods=['POST'])
@login_required
def api_job_note(job_id):
    """อัปเดตรายงาน / บันทึกงาน"""
    job = FieldJob.query.get_or_404(job_id)
    if not _can_view(job):
        return _err('ใบงานนี้ไม่ได้มอบหมายให้คุณ', 403)
    body = (_payload().get('body') or '').strip()
    if not body:
        return _err('กรุณาพิมพ์บันทึกงาน')
    c = TicketComment(ticket_id=job.ticket_id, user_id=current_user.id, message=body[:2000])
    db.session.add(c)
    db.session.commit()
    return jsonify({'success': True, 'note': {'id': c.id, 'by': current_user.name, 'body': c.message,
                                              'at': _iso(c.created_at)}}), 201


@field_bp.route('/api/sites')
@login_required
def api_sites():
    q = (request.args.get('q') or '').strip()[:100]
    query = FieldSite.query.filter(FieldSite.is_active.isnot(False))
    if q:
        query = query.filter(FieldSite.name.ilike(f'%{q}%'))
    return jsonify({'success': True, 'sites': [{
        'id': s.id, 'name': s.name, 'address': s.address, 'lat': s.lat, 'lng': s.lng,
        'contact_name': s.contact_name, 'contact_phone': s.contact_phone}
        for s in query.order_by(FieldSite.name).limit(200).all()]})


@field_bp.route('/api/technicians')
@login_required
def api_technicians():
    denied = _owner_required()
    if denied:
        return denied
    users = (User.query.filter(User.role.in_(ASSIGNABLE_ROLES), User.is_active_user.isnot(False))
             .order_by(db.case((User.role == 'Technician', 0), else_=1), User.name).all())
    open_counts = dict(db.session.query(Ticket.assignee_id, db.func.count(Ticket.id))
                       .filter(Ticket.status.in_(OPEN_TICKET_STATUSES)).group_by(Ticket.assignee_id).all())
    return jsonify({'success': True, 'technicians': [{
        'id': u.id, 'name': u.name, 'role': u.role, 'open_jobs': open_counts.get(u.id, 0),
        'clocked_in': _clock_state(u)['clocked_in']} for u in users]})


# ---------------- สต๊อก / ขอเบิก / อนุมัติเบิก ----------------

def _stock_request_dict(r):
    p = r.spare_part
    return {
        'id': r.id, 'status': r.status, 'status_label': StockRequest.STATUS_LABELS.get(r.status, r.status),
        'part_id': p.id, 'part_name': p.name, 'sku': p.sku, 'unit': p.unit, 'quantity': r.quantity,
        'stock_quantity': p.stock_quantity, 'requester': r.requester.name, 'requester_id': r.requester_id,
        'job_id': r.job_id, 'job_ref': (r.job.external_ref or r.job.ticket.ticket_number) if r.job else None,
        'note': r.note, 'decision_note': r.decision_note,
        'decider': r.decider.name if r.decider else None,
        'created_at': _iso(r.created_at), 'decided_at': _iso(r.decided_at),
    }


@field_bp.route('/api/stock')
@login_required
def api_stock():
    q = (request.args.get('q') or '').strip()[:100]
    category = (request.args.get('category') or '').strip()
    query = SparePart.query.filter(SparePart.is_active.isnot(False))
    if q:
        like = f'%{q}%'
        query = query.filter(db.or_(SparePart.name.ilike(like), SparePart.sku.ilike(like),
                                    SparePart.description.ilike(like)))
    if category:
        query = query.filter(SparePart.category == category)
    categories = [c for (c,) in db.session.query(SparePart.category)
                  .filter(SparePart.is_active.isnot(False)).distinct().order_by(SparePart.category).all() if c]
    return jsonify({'success': True, 'categories': categories, 'parts': [{
        'id': p.id, 'sku': p.sku, 'name': p.name, 'category': p.category, 'unit': p.unit,
        'stock_quantity': p.stock_quantity, 'low': p.is_low_stock(), 'location': p.location,
        'description': p.description} for p in query.order_by(SparePart.name).limit(300).all()]})


@field_bp.route('/api/stock/requests')
@login_required
def api_stock_requests():
    status = request.args.get('status')
    query = StockRequest.query
    if request.args.get('scope') != 'all' or not _is_dispatcher(current_user):
        query = query.filter(StockRequest.requester_id == current_user.id)
    if status in StockRequest.STATUS_LABELS:
        query = query.filter(StockRequest.status == status)
    return jsonify({'success': True, 'requests': [_stock_request_dict(r) for r in
                                                   query.order_by(StockRequest.id.desc()).limit(100).all()]})


@field_bp.route('/api/stock/requests', methods=['POST'])
@login_required
def api_stock_request_create():
    data = request.get_json(silent=True) or {}
    items = data.get('items') or []
    if not isinstance(items, list) or not items or len(items) > 30:
        return _err('กรุณาเลือกอุปกรณ์ที่จะเบิก')
    job = None
    if data.get('job_id'):
        job = db.session.get(FieldJob, int(data['job_id']))
        if not job or not _can_view(job):
            return _err('ไม่พบใบงาน', 404)
    note = (data.get('note') or '').strip()[:300] or None
    created = []
    for it in items:
        try:
            part_id, qty = int(it.get('part_id')), int(it.get('quantity'))
        except (TypeError, ValueError, AttributeError):
            return _err('ข้อมูลรายการไม่ถูกต้อง')
        part = db.session.get(SparePart, part_id)
        if not part or part.is_active is False:
            return _err('ไม่พบอุปกรณ์')
        if qty <= 0 or qty > 1000:
            return _err(f'จำนวน {part.name} ไม่ถูกต้อง')
        if qty > part.stock_quantity:
            return _err(f'{part.name} คงเหลือ {part.stock_quantity} {part.unit} ไม่พอเบิก {qty}', 409)
        r = StockRequest(spare_part_id=part.id, quantity=qty, requester_id=current_user.id,
                         job_id=job.id if job else None, note=note)
        db.session.add(r)
        created.append(r)
    db.session.flush()
    summary = ', '.join(f'{r.spare_part.name} ×{r.quantity}' for r in created)
    _post_system_message(f'{current_user.name} ขอเบิก {summary}' + (f' (งาน {job.ticket.ticket_number})' if job else ''))
    db.session.commit()
    try:
        send_custom_notification(f'📦 ขอเบิกอุปกรณ์ (รออนุมัติ)\n👷 {current_user.name}\n{summary}',
                                 SystemConfig.get_notification_config(), email_subject='[Field] ขอเบิกอุปกรณ์')
    except Exception as e:
        current_app.logger.warning(f'notify failed: {e}')
    return jsonify({'success': True, 'requests': [_stock_request_dict(r) for r in created]}), 201


@field_bp.route('/api/stock/requests/<int:req_id>/<decision>', methods=['POST'])
@login_required
def api_stock_request_decide(req_id, decision):
    if decision not in ('approve', 'reject'):
        return _err('ไม่รู้จักคำสั่งนี้', 404)
    denied = _owner_required()
    if denied:
        return denied
    r = StockRequest.query.get_or_404(req_id)
    if r.status != 'Pending':
        return _err(f'คำขอนี้{r.status == "Approved" and "อนุมัติ" or "ปฏิเสธ"}ไปแล้ว', 409)
    data = _payload()
    r.decision_note = (data.get('note') or '').strip()[:300] or None
    r.decided_by, r.decided_at = current_user.id, datetime.utcnow()

    if decision == 'reject':
        r.status = 'Rejected'
        db.session.commit()
        return jsonify({'success': True, 'request': _stock_request_dict(r)})

    # ตัดสต๊อกแบบ atomic: UPDATE ... WHERE stock_quantity >= qty กันอนุมัติพร้อมกันจนติดลบ
    part = r.spare_part
    updated = (SparePart.query.filter(SparePart.id == part.id, SparePart.stock_quantity >= r.quantity)
               .update({SparePart.stock_quantity: SparePart.stock_quantity - r.quantity}, synchronize_session=False))
    if not updated:
        db.session.rollback()
        db.session.refresh(part)
        return _err(f'สต๊อก {part.name} คงเหลือ {part.stock_quantity} {part.unit} ไม่พอ', 409)
    db.session.refresh(part)
    ticket_id = r.job.ticket_id if r.job else None
    txn = StockTransaction(spare_part_id=part.id, transaction_type='OUT', quantity=r.quantity,
                           unit_price=part.unit_price, total_price=part.unit_price * r.quantity,
                           ticket_id=ticket_id, reference=f'REQ-{r.id}',
                           note=f'เบิกโดย {r.requester.name} (อนุมัติโดย {current_user.name})' + (f' — {r.note}' if r.note else ''),
                           actor_id=current_user.id)
    db.session.add(txn)
    db.session.flush()
    if ticket_id:
        db.session.add(TicketExpense(ticket_id=ticket_id, expense_type='parts', description=f'{part.name} ({part.sku})',
                                     amount=part.unit_price, quantity=r.quantity, total=part.unit_price * r.quantity,
                                     spare_part_id=part.id, stock_transaction_id=txn.id, created_by=current_user.id))
    r.status, r.stock_transaction_id = 'Approved', txn.id
    _post_system_message(f'อนุมัติเบิก {part.name} ×{r.quantity} ให้ {r.requester.name}')
    db.session.commit()
    return jsonify({'success': True, 'request': _stock_request_dict(r)})


# ---------------- แจ้งเหตุด่วน ----------------

@field_bp.route('/api/sos', methods=['POST'])
@login_required
def api_sos():
    data = _payload()
    cu = _client_uuid(data)
    if cu and FieldEvent.query.filter_by(client_uuid=cu).first():
        return jsonify({'success': True, 'duplicate': True})
    lat, lng = _float(data.get('lat')), _float(data.get('lng'))
    note = (data.get('note') or '').strip()[:500] or None
    job = None
    if data.get('job_id'):
        job = db.session.get(FieldJob, int(data['job_id']))
        if job and not _can_view(job):
            job = None
    db.session.add(FieldEvent(user_id=current_user.id, job_id=job.id if job else None, event_type='sos',
                              lat=lat, lng=lng, accuracy_m=_float(data.get('accuracy')), note=note,
                              client_uuid=cu, client_time=_client_time(data)))
    where = f'https://maps.google.com/?q={lat:.6f},{lng:.6f}' if lat is not None and lng is not None else 'ไม่ทราบตำแหน่ง (GPS ปิด)'
    _post_system_message(f'🚨 SOS จาก {current_user.name}' + (f' — {note}' if note else ''))
    db.session.commit()
    sent = {}
    try:
        sent = send_custom_notification(
            f'🚨 แจ้งเหตุด่วน (SOS)\n👷 {current_user.name}\n📍 {where}' + (f'\n📝 {note}' if note else '') +
            (f'\n📋 งาน {job.ticket.ticket_number}' if job else ''),
            SystemConfig.get_notification_config(), email_subject=f'[SOS] {current_user.name}')
    except Exception as e:
        current_app.logger.warning(f'SOS notify failed: {e}')
    return jsonify({'success': True, 'notified': [k for k, v in (sent or {}).items() if v]})
