"""KAT SERVICE Mobile V1: เปิดงาน, รูปตามขั้น, มอบหมาย, ลงเวลา, ขอเบิก/อนุมัติ, SOS"""
import io

from tests.conftest import login


def _jpg():
    return io.BytesIO(b'\xff\xd8\xff fake jpeg'), 'p.jpg'


def test_mobile_login_page_for_field(app):
    html = app.test_client().get('/login?next=/field/').get_data(as_text=True)
    assert 'จดจำการเข้าสู่ระบบ (30 วัน)' in html and 'field/app.css' in html
    desktop = app.test_client().get('/login').get_data(as_text=True)
    assert 'บัญชีทดสอบ' in desktop  # dev แสดงบัญชีทดสอบ


def test_remember_checkbox(app, tech):
    c = app.test_client()
    r = c.post('/login', data={'username': 'tu', 'password': 'pw', 'remember_field': '1'})
    assert 'remember_token' not in r.headers.get('Set-Cookie', '')
    c2 = app.test_client()
    r = c2.post('/login', data={'username': 'tu', 'password': 'pw', 'remember_field': '1', 'remember': 'on'})
    assert any('remember_token' in h for h in r.headers.getlist('Set-Cookie'))


def test_technician_opens_job_with_before_photos(app, tech):
    c = app.test_client(); login(c, 'tu', 'pw')
    r = c.post('/field/api/jobs', data={'site_name': 'หอพัก Net_DD', 'job_type': 'KAT', 'description': 'กล้องไม่ออนไลน์ 2 ตัว',
                                        'lat': '17.862689', 'lng': '102.749284', 'photos': [_jpg(), _jpg()]},
               content_type='multipart/form-data')
    assert r.status_code == 201, r.get_json()
    job = r.get_json()['job']
    assert job['assignee_id'] == tech and job['ticket_status'] == 'Pending' and job['photo_count'] == 2
    d = c.get(f"/field/api/jobs/{job['id']}").get_json()['job']
    assert len(d['photos']['before']) == 2 and d['can_act']
    # สถานที่ถูกจำไว้พร้อมพิกัด
    sites = c.get('/field/api/sites?q=Net').get_json()['sites']
    assert sites[0]['lat'] == 17.862689
    # เปิดงานซ้ำที่เดิม (ตัวพิมพ์ต่างกัน) ไม่สร้างสถานที่ซ้ำ
    c.post('/field/api/jobs', data={'site_name': 'หอพัก net_dd', 'job_type': 'PM', 'description': 'PM'})
    assert len(c.get('/field/api/sites').get_json()['sites']) == 1


def test_create_job_validation(app, tech):
    c = app.test_client(); login(c, 'tu', 'pw')
    assert c.post('/field/api/jobs', data={'site_name': 'A', 'job_type': 'KAT'}).status_code == 400
    assert c.post('/field/api/jobs', data={'site_name': 'A', 'job_type': 'X', 'description': 'x'}).status_code == 400
    assert c.post('/field/api/jobs', data={'job_type': 'KAT', 'description': 'x'}).status_code == 400


def test_owner_creates_and_assigns(app, tech):
    o = app.test_client(); login(o, 'admin')
    r = o.post('/field/api/jobs', data={'site_name': 'บริษัท ซินโฟนี่', 'job_type': 'MA_FIBER',
                                        'description': 'ไฟเบอร์ขาด', 'appointment_at': '2026-11-29T17:00'})
    job = r.get_json()['job']
    assert job['ticket_status'] == 'Manager_Approved' and job['assignee_id'] is None
    assert job['appointment_at'].startswith('2026-11-29T10:00')
    st = o.get('/field/api/state').get_json()
    assert st['user']['is_owner'] and st['counts']['unassigned'] >= 1
    techs = o.get('/field/api/technicians').get_json()['technicians']
    assert techs[0]['id'] == tech  # Technician มาก่อน
    r = o.post(f"/field/api/jobs/{job['id']}/assign", json={'assignee_id': tech})
    assert r.get_json()['job']['assignee_name'] == 'ตู่ ช่างไฟ'

    t = app.test_client(); login(t, 'tu', 'pw')
    assert t.post(f"/field/api/jobs/{job['id']}/assign", json={'assignee_id': tech}).status_code == 403
    assert t.get('/field/api/technicians').status_code == 403
    mine = t.get('/field/api/jobs').get_json()['jobs']
    assert [j['id'] for j in mine] == [job['id']]
    # owner ดูได้ทุกงาน, ช่างเห็นเฉพาะของตัวเองแม้ขอ scope=all
    assert len(o.get('/field/api/jobs?scope=all').get_json()['jobs']) >= 1
    assert all(j['assignee_id'] == tech for j in t.get('/field/api/jobs?scope=all').get_json()['jobs'])


def test_photo_stages_and_notes(app, tech):
    c = app.test_client(); login(c, 'tu', 'pw')
    job = c.post('/field/api/jobs', data={'site_name': 'S', 'job_type': 'KAT', 'description': 'x'}).get_json()['job']
    for stage in ('during', 'after', 'bogus'):
        c.post('/field/api/photo', data={'job_id': job['id'], 'stage': stage, 'photo': _jpg()},
               content_type='multipart/form-data')
    p = c.get(f"/field/api/jobs/{job['id']}").get_json()['job']['photos']
    assert len(p['during']) == 1 and len(p['after']) == 1 and len(p['before']) == 1  # bogus → ค่าเริ่มต้นตามสถานะ (Assigned=before)
    assert c.post(f"/field/api/jobs/{job['id']}/note", json={'body': ''}).status_code == 400
    assert c.post(f"/field/api/jobs/{job['id']}/note", json={'body': 'เปลี่ยนหัว SC แล้ว'}).status_code == 201
    assert c.get(f"/field/api/jobs/{job['id']}").get_json()['job']['notes'][0]['body'] == 'เปลี่ยนหัว SC แล้ว'
    other = app.test_client(); login(other, 'somchai')
    assert other.get(f"/field/api/jobs/{job['id']}").status_code == 403


def test_clock_explicit_and_history(app, tech):
    c = app.test_client(); login(c, 'tu', 'pw')
    pos = {'lat': 17.86, 'lng': 102.74, 'accuracy': 5}
    assert c.post('/field/api/clock', json={**pos, 'type': 'clock_out'}).status_code == 409
    assert c.post('/field/api/clock', json={**pos, 'type': 'clock_in'}).status_code == 200
    assert c.post('/field/api/clock', json={**pos, 'type': 'clock_in'}).status_code == 409
    assert c.post('/field/api/clock', json={**pos, 'type': 'clock_out'}).status_code == 200
    h = c.get('/field/api/clock').get_json()
    assert [e['type'] for e in h['history']] == ['clock_out', 'clock_in'] and not h['clock']['clocked_in']


def test_stock_request_approve_flow(app, tech):
    from app import db
    from app.models import SparePart, StockTransaction, TicketExpense
    t = app.test_client(); login(t, 'tu', 'pw')
    stock = t.get('/field/api/stock?q=LAN').get_json()
    part = stock['parts'][0]
    assert 'อุปกรณ์เครือข่าย' in stock['categories']
    job = t.post('/field/api/jobs', data={'site_name': 'S', 'job_type': 'KAT', 'description': 'x'}).get_json()['job']

    assert t.post('/field/api/stock/requests', json={'items': [{'part_id': part['id'], 'quantity': 999}]}).status_code == 409
    assert t.post('/field/api/stock/requests', json={'items': [{'part_id': part['id'], 'quantity': 0}]}).status_code == 400
    r = t.post('/field/api/stock/requests', json={'items': [{'part_id': part['id'], 'quantity': 3}], 'job_id': job['id'], 'note': 'เดินสายใหม่'})
    assert r.status_code == 201
    req = r.get_json()['requests'][0]
    assert t.post(f"/field/api/stock/requests/{req['id']}/approve").status_code == 403

    o = app.test_client(); login(o, 'admin')
    assert o.get('/field/api/state').get_json()['counts']['pending_approvals'] == 1
    r = o.post(f"/field/api/stock/requests/{req['id']}/approve", json={})
    assert r.get_json()['request']['status'] == 'Approved'
    assert o.post(f"/field/api/stock/requests/{req['id']}/approve", json={}).status_code == 409
    with app.app_context():
        assert db.session.get(SparePart, part['id']).stock_quantity == part['stock_quantity'] - 3
        txn = StockTransaction.query.filter_by(reference=f"REQ-{req['id']}").one()
        assert txn.transaction_type == 'OUT' and txn.ticket_id == job['ticket_id']
        assert TicketExpense.query.filter_by(stock_transaction_id=txn.id).count() == 1
    assert t.get(f"/field/api/jobs/{job['id']}").get_json()['job']['stock_requests'][0]['status'] == 'Approved'


def test_stock_approve_rechecks_quantity_and_reject(app, tech):
    from app import db
    from app.models import SparePart
    t = app.test_client(); login(t, 'tu', 'pw')
    part = t.get('/field/api/stock?q=RAM').get_json()['parts'][0]   # คงเหลือ 4
    a = t.post('/field/api/stock/requests', json={'items': [{'part_id': part['id'], 'quantity': 3}]}).get_json()['requests'][0]
    b = t.post('/field/api/stock/requests', json={'items': [{'part_id': part['id'], 'quantity': 3}]}).get_json()['requests'][0]
    o = app.test_client(); login(o, 'admin')
    assert o.post(f"/field/api/stock/requests/{a['id']}/approve").status_code == 200
    r = o.post(f"/field/api/stock/requests/{b['id']}/approve")
    assert r.status_code == 409   # เหลือ 1 ไม่พอ ต้องไม่ติดลบ
    with app.app_context():
        assert db.session.get(SparePart, part['id']).stock_quantity == 1
    r = o.post(f"/field/api/stock/requests/{b['id']}/reject", json={'note': 'ของไม่พอ'})
    assert r.get_json()['request']['status'] == 'Rejected'
    mine = t.get('/field/api/stock/requests').get_json()['requests']
    assert {x['status'] for x in mine} == {'Approved', 'Rejected'}


def test_sos(app, tech):
    c = app.test_client(); login(c, 'tu', 'pw')
    r = c.post('/field/api/sos', json={'lat': 17.86, 'lng': 102.74, 'note': 'รถเสีย', 'client_uuid': 'sosuuid0001'})
    assert r.get_json()['success']
    assert c.post('/field/api/sos', json={'client_uuid': 'sosuuid0001'}).get_json()['duplicate']
    msgs = c.get('/field/api/messages').get_json()['messages']
    assert any(m['kind'] == 'system' and 'SOS' in m['body'] for m in msgs)


def test_desktop_assign_creates_field_job(app, tech):
    a = app.test_client(); login(a, 'admin')
    a.post('/tickets/4/assign', data={'assignee_id': tech})
    t = app.test_client(); login(t, 'tu', 'pw')
    jobs = t.get('/field/api/jobs').get_json()['jobs']
    assert any(j['ticket_id'] == 4 for j in jobs)
