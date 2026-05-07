from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from ..models import User
from .. import db

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user, remember=True)
            flash(f'ยินดีต้อนรับ, {user.name}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard.index'))
        else:
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'danger')

    return render_template('login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        name = request.form.get('name', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        department = request.form.get('department', '').strip()

        # Validation
        if not all([username, email, name, password]):
            flash('กรุณากรอกข้อมูลให้ครบทุกช่อง', 'danger')
            return render_template('register.html')

        if password != confirm:
            flash('รหัสผ่านไม่ตรงกัน', 'danger')
            return render_template('register.html')

        if User.query.filter_by(username=username).first():
            flash('ชื่อผู้ใช้นี้ถูกใช้งานแล้ว', 'danger')
            return render_template('register.html')

        if User.query.filter_by(email=email).first():
            flash('อีเมลนี้ถูกใช้งานแล้ว', 'danger')
            return render_template('register.html')

        user = User(username=username, email=email, name=name,
                    department=department, role='Employee')
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('สมัครสมาชิกเรียบร้อย! กรุณาเข้าสู่ระบบ', 'success')
        return redirect(url_for('auth.login'))

    return render_template('register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('ออกจากระบบเรียบร้อย', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """หน้าโปรไฟล์ — แก้ไขข้อมูลส่วนตัว + เปลี่ยนรหัสผ่าน"""
    if request.method == 'POST':
        action = request.form.get('action', '')

        if action == 'update_info':
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            department = request.form.get('department', '').strip()

            if not name or not email:
                flash('กรุณากรอกชื่อและอีเมล', 'danger')
                return redirect(url_for('auth.profile'))

            # ตรวจสอบอีเมลซ้ำ
            existing = User.query.filter(User.email == email, User.id != current_user.id).first()
            if existing:
                flash('อีเมลนี้ถูกใช้งานแล้ว', 'danger')
                return redirect(url_for('auth.profile'))

            current_user.name = name
            current_user.email = email
            current_user.department = department
            db.session.commit()
            flash('อัปเดตข้อมูลส่วนตัวเรียบร้อย', 'success')

        elif action == 'change_password':
            current_pw = request.form.get('current_password', '')
            new_pw = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')

            if not current_user.check_password(current_pw):
                flash('รหัสผ่านเดิมไม่ถูกต้อง', 'danger')
                return redirect(url_for('auth.profile'))

            if len(new_pw) < 4:
                flash('รหัสผ่านใหม่ต้องมีอย่างน้อย 4 ตัวอักษร', 'danger')
                return redirect(url_for('auth.profile'))

            if new_pw != confirm_pw:
                flash('รหัสผ่านใหม่ไม่ตรงกัน', 'danger')
                return redirect(url_for('auth.profile'))

            current_user.set_password(new_pw)
            db.session.commit()
            flash('เปลี่ยนรหัสผ่านเรียบร้อย', 'success')

        return redirect(url_for('auth.profile'))

    # GET — นับ ticket ของ user
    from ..models import Ticket
    my_tickets = Ticket.query.filter_by(requester_id=current_user.id).count()
    my_assigned = Ticket.query.filter_by(assignee_id=current_user.id).count()

    return render_template('profile.html',
                           my_tickets=my_tickets,
                           my_assigned=my_assigned)
