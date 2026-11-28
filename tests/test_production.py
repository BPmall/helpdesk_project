import os

from tests.conftest import login


def _prod_app(tmp_path, monkeypatch, **env):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'prod.db'))
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('UPLOAD_FOLDER', str(tmp_path / 'vol'))
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    if 'SECRET_KEY' not in env:
        monkeypatch.delenv('SECRET_KEY', raising=False)
    from app import create_app
    app = create_app()
    app.config['WTF_CSRF_ENABLED'] = False
    return app


def test_production_does_not_use_known_secret_or_1234(tmp_path, monkeypatch):
    app = _prod_app(tmp_path, monkeypatch)
    assert app.config['SECRET_KEY'] not in ('helpdesk-secret-key-change-in-production', 'helpdesk-dev-secret-key')
    assert app.config['SESSION_COOKIE_SECURE'] is True
    c = app.test_client()
    r = c.post('/login', data={'username': 'admin', 'password': '1234'})
    assert r.status_code == 200  # 1234 ใช้ไม่ได้บน production


def test_production_initial_password_and_https(tmp_path, monkeypatch):
    app = _prod_app(tmp_path, monkeypatch, SECRET_KEY='s' * 40, INITIAL_ADMIN_PASSWORD='Str0ng-Pass!')
    c = app.test_client()
    r = c.get('/login', headers={'X-Forwarded-Proto': 'http'}, base_url='http://hd.example.com')
    assert r.status_code == 301 and r.headers['Location'].startswith('https://hd.example.com/login')
    assert c.get('/health', headers={'X-Forwarded-Proto': 'http'}).status_code == 200
    r = c.post('/login', data={'username': 'admin', 'password': 'Str0ng-Pass!'},
               headers={'X-Forwarded-Proto': 'https'}, base_url='https://hd.example.com')
    assert r.status_code == 302
    assert 'Strict-Transport-Security' in r.headers
    assert os.path.isdir(app.config['UPLOAD_FOLDER']) and app.config['UPLOAD_FOLDER'].endswith('vol')


def test_uploads_require_login_except_equipment_image(app):
    from app import db
    from app.models import Equipment
    folder = app.config['UPLOAD_FOLDER']
    for name in ('secret.pdf', 'eq.jpg'):
        with open(os.path.join(folder, name), 'wb') as fh:
            fh.write(b'x')
    with app.app_context():
        db.session.get(Equipment, 1).image = 'eq.jpg'
        db.session.commit()
    c = app.test_client()
    assert c.get('/uploads/secret.pdf').status_code == 302
    assert c.get('/uploads/eq.jpg').status_code == 200
    login(c, 'admin')
    assert c.get('/uploads/../run.py').status_code == 404
    assert c.get('/uploads/%2e%2e/run.py').status_code == 404
    assert c.get('/uploads/secret.pdf').status_code == 200
    assert c.get('/uploads/missing.png').status_code == 404
