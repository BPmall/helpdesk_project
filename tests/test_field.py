import io

from tests.conftest import login


def _assign(app, ticket_id, user_id, **job):
    from app import db
    from app.models import Ticket
    from app.routes.field import get_or_create_field_job
    with app.app_context():
        t = db.session.get(Ticket, ticket_id)
        t.assignee_id = user_id
        fj = get_or_create_field_job(t)
        for k, v in job.items():
            setattr(fj, k, v)
        db.session.commit()
        return fj.id


def test_technician_login_lands_on_field_app(app, tech):
    c = app.test_client()
    r = login(c, 'tu', 'pw')
    assert r.status_code == 302 and r.headers['Location'].endswith('/field/')
    assert c.get('/field/').status_code == 200


def test_login_rejects_open_redirect(app):
    c = app.test_client()
    r = c.post('/login?next=//evil.example.com', data={'username': 'admin', 'password': '1234'})
    assert 'evil' not in r.headers['Location']


def test_inactive_user_cannot_login(app, tech):
    from app import db
    from app.models import User
    with app.app_context():
        db.session.get(User, tech).is_active_user = False
        db.session.commit()
    r = login(app.test_client(), 'tu', 'pw')
    assert r.status_code == 200  # stays on login page


def test_full_job_flow(app, tech):
    job_id = _assign(app, 5, tech, lat=13.8621, lng=100.5144, geofence_m=200,
                     coordinator_name='คุณเอ', site_name='ไซต์ทดสอบ')
    c = app.test_client(); login(c, 'tu', 'pw')

    s = c.get('/field/api/state').get_json()
    assert s['pending_count'] == 1
    assert s['active_job']['id'] == job_id and s['active_job']['next_action'] == 'accept'

    # ข้ามขั้นไม่ได้
    assert c.post(f'/field/api/jobs/{job_id}/finish', json={}).status_code == 409

    r = c.post(f'/field/api/jobs/{job_id}/accept', json={'client_uuid': 'acceptuuid01'})
    assert r.get_json()['job']['field_status'] == 'Accepted'
    # ส่งซ้ำ (offline retry) ต้องไม่ error และไม่ทำซ้ำ
    r = c.post(f'/field/api/jobs/{job_id}/accept', json={'client_uuid': 'acceptuuid01'})
    assert r.get_json()['duplicate'] is True

    assert c.post(f'/field/api/jobs/{job_id}/depart', json={}).status_code == 200

    # ถึงหน้างาน: ไม่มี GPS → 422 / ไกลเกิน → 409 ต้องมีเหตุผล
    assert c.post(f'/field/api/jobs/{job_id}/arrive', json={}).status_code == 422
    far = {'lat': 13.90, 'lng': 100.60, 'accuracy': 10}
    r = c.post(f'/field/api/jobs/{job_id}/arrive', json=far)
    assert r.status_code == 409 and r.get_json()['code'] == 'outside_geofence'
    near = {'lat': 13.8625, 'lng': 100.5146, 'accuracy': 15}
    r = c.post(f'/field/api/jobs/{job_id}/arrive', json=near)
    assert r.status_code == 200 and r.get_json()['job']['field_status'] == 'OnSite'

    # ปิดงานต้องมีรูป
    r = c.post(f'/field/api/jobs/{job_id}/finish', json={})
    assert r.status_code == 422 and r.get_json()['code'] == 'photo_required'
    r = c.post('/field/api/photo', data={'job_id': job_id, 'photo': (io.BytesIO(b'\xff\xd8fakejpeg'), 'a.jpg')},
               content_type='multipart/form-data')
    assert r.status_code == 200
    photo_url = r.get_json()['url']
    assert c.get(photo_url).status_code == 200
    assert c.post(f'/field/api/jobs/{job_id}/finish', json={}).status_code == 200

    from app import db
    from app.models import Ticket, TicketLog
    with app.app_context():
        t = db.session.get(Ticket, 5)
        assert t.status == 'Resolved' and t.resolved_at is not None
        assert TicketLog.query.filter(TicketLog.ticket_id == 5, TicketLog.action.like('%แอปช่าง%')).count() == 4
    assert c.get('/field/api/state').get_json()['pending_count'] == 0


def test_cannot_act_on_someone_elses_job(app, tech):
    job_id = _assign(app, 5, 1)  # มอบให้ admin
    c = app.test_client(); login(c, 'tu', 'pw')
    assert c.post(f'/field/api/jobs/{job_id}/accept', json={}).status_code == 403


def test_arrive_learns_site_location_when_missing(app, tech):
    job_id = _assign(app, 5, tech)
    c = app.test_client(); login(c, 'tu', 'pw')
    c.post(f'/field/api/jobs/{job_id}/accept', json={})
    c.post(f'/field/api/jobs/{job_id}/arrive', json={'lat': 13.7, 'lng': 100.5})
    from app import db
    from app.models import FieldJob
    with app.app_context():
        assert db.session.get(FieldJob, job_id).lat == 13.7


def test_clock_toggle_requires_gps(app, tech):
    c = app.test_client(); login(c, 'tu', 'pw')
    assert c.post('/field/api/clock', json={}).status_code == 422
    r = c.post('/field/api/clock', json={'lat': 13.7, 'lng': 100.5}).get_json()
    assert r['event'] == 'clock_in' and r['clock']['clocked_in']
    r = c.post('/field/api/clock', json={'lat': 13.7, 'lng': 100.5}).get_json()
    assert r['event'] == 'clock_out' and not r['clock']['clocked_in']


def test_chat_text_and_voice(app, tech):
    c = app.test_client(); login(c, 'tu', 'pw')
    assert c.post('/field/api/messages', json={'body': ''}).status_code == 400
    m1 = c.post('/field/api/messages', json={'body': 'รับทราบครับ'}).get_json()['message']
    r = c.post('/field/api/voice', data={'duration': '2.4', 'audio': (io.BytesIO(b'OggS....'), 'voice.ogg')},
               content_type='multipart/form-data')
    assert r.status_code == 201
    r = c.post('/field/api/voice', data={'duration': '2', 'audio': (io.BytesIO(b'MZ'), 'evil.exe')},
               content_type='multipart/form-data')
    assert r.status_code == 400

    other = app.test_client(); login(other, 'admin')
    msgs = other.get(f"/field/api/messages?after={m1['id'] - 1}").get_json()['messages']
    assert [m['kind'] for m in msgs] == ['text', 'voice']
    assert msgs[0]['mine'] is False and msgs[1]['file_url']


def test_media_requires_login(app):
    assert app.test_client().get('/field/media/x.jpg').status_code == 302


def test_crm_webhook_upsert(app, tech):
    c = app.test_client()
    payload = {'external_ref': 'JOB-2611-00052', 'title': 'ไฟเบอร์ขาด', 'job_type': 'MA_FIBER',
               'site_name': 'บริษัท ตัวอย่าง', 'lat': 13.86, 'lng': 100.51, 'assignee_username': 'tu',
               'appointment_at': '2026-11-28T09:30:00'}
    assert c.post('/field/api/crm/jobs', json=payload).status_code == 401
    r = c.post('/field/api/crm/jobs', json=payload, headers={'X-API-Key': 'test-crm-key'})
    assert r.status_code == 201 and r.get_json()['created']
    r = c.post('/field/api/crm/jobs', json={**payload, 'title': 'ไฟเบอร์ขาด (แก้ไข)'},
               headers={'X-API-Key': 'test-crm-key'})
    assert r.status_code == 200 and not r.get_json()['created']

    login(c, 'tu', 'pw')
    s = c.get('/field/api/state').get_json()
    job = s['active_job']
    assert job['ref'] == 'JOB-2611-00052' and job['job_type'] == 'MA_FIBER'
    assert job['title'] == 'ไฟเบอร์ขาด (แก้ไข)'
    assert job['appointment_at'].startswith('2026-11-28T02:30')  # 09:30 เวลาไทย = 02:30 UTC


def test_dispatch_form_and_assign_permission(app, tech):
    c = app.test_client(); login(c, 'somchai')  # Employee
    c.post('/tickets/5/assign', data={'assignee_id': tech})
    from app import db
    from app.models import Ticket
    with app.app_context():
        assert db.session.get(Ticket, 5).assignee_id is None

    a = app.test_client(); login(a, 'admin')
    a.post('/tickets/5/assign', data={'assignee_id': tech})
    a.post('/field/dispatch/5', data={'job_type': 'MA_FIBER', 'site_name': 'ไซต์ A',
                                      'latlng': '13.8621, 100.5144', 'coordinator_name': 'คุณเอ'})
    with app.app_context():
        t = db.session.get(Ticket, 5)
        assert t.assignee_id == tech
        assert t.field_job.lat == 13.8621 and t.field_job.job_type == 'MA_FIBER'
    assert a.get('/tickets/5').status_code == 200


def test_ticket_create_form_has_branches(app):
    c = app.test_client(); login(c, 'somchai')
    html = c.get('/tickets/new').get_data(as_text=True)
    assert 'สาขารังสิต' in html
    r = c.post('/tickets/new', data={'title': 'x', 'contact_phone': '0812345678', 'branch_location': 'ไม่มีสาขานี้'})
    assert r.headers['Location'].endswith('/tickets/new')
    r = c.post('/tickets/new', data={'title': 'เน็ตล่ม', 'contact_phone': '0812345678',
                                     'branch_location': 'สาขารังสิต', 'priority': 'High'})
    assert '/tickets/6' in r.headers['Location']
