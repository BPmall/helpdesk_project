import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'test.db'))
    monkeypatch.setenv('FIELD_CRM_API_KEY', 'test-crm-key')
    from app import create_app
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                              UPLOAD_FOLDER=str(tmp_path / 'uploads'))
    os.makedirs(application.config['UPLOAD_FOLDER'], exist_ok=True)
    yield application


@pytest.fixture()
def tech(app):
    from app import db
    from app.models import User
    with app.app_context():
        u = User(username='tu', email='tu@example.com', name='ตู่ ช่างไฟ', role='Technician')
        u.set_password('pw')
        db.session.add(u)
        db.session.commit()
        return u.id


def login(client, username, password='1234'):
    return client.post('/login', data={'username': username, 'password': password})
