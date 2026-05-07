# --- เริ่มต้นโค้ดที่ถูกต้อง ---

# ขั้นตอนที่ 1: ตรวจสอบและแก้ไขส่วน Import
# (ตรวจสอบว่ามีบรรทัดนี้อยู่บนสุดของไฟล์ และไม่มีบรรทัด 'from ..decorators ...' ที่ซ้ำซ้อน)

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from ..models import TicketLog, User, SystemConfig, Ticket, Category
from .. import db
from functools import wraps

# ขั้นตอนที่ 2: ตรวจสอบและแก้ไขส่วน Blueprint และ Decorator

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# นิยาม admin_required ขึ้นมาใหม่ภายในไฟล์นี้
# (เพื่อให้ระบบรู้จัก admin_required โดยไม่ต้อง import มาจากที่อื่น)
def admin_required(f):
    """Decorator: ต้องเป็น Admin หรือ Manager เท่านั้น"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['Admin', 'Manager']:
            flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function

# ขั้นตอนที่ 3: ตรวจสอบและแก้ไขส่วน Routes ต่างๆ
# (ตรวจสอบว่าคำสั่ง 'from ..decorators ...' และ 'from . import admin_bp' ที่วางผิดที่ได้ถูกลบออกแล้ว)

@admin_bp.route('/categories')
@login_required
@admin_required
def category_list():
    """หน้าจัดการหมวดหมู่"""
    categories = Category.query.all()
    return render_template('categories.html', categories=categories)


@admin_bp.route('/categories/add', methods=['POST'])
@login_required
@admin_required
def add_category():
    """เพิ่มหมวดหมู่ใหม่"""
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    icon = request.form.get('icon', '🔧').strip()

    if not name:
        flash('กรุณากรอกชื่อหมวดหมู่', 'danger')
        return redirect(url_for('admin.category_list'))

    category = Category(name=name, description=description, icon=icon)
    db.session.add(category)
    db.session.commit()
    flash(f'เพิ่มหมวดหมู่ "{name}" เรียบร้อยแล้ว', 'success')
    return redirect(url_for('admin.category_list'))


@admin_bp.route('/categories/<int:category_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_category(category_id):
    """ลบหมวดหมู่ (ลบได้เฉพาะหมวดที่ไม่มี Ticket ค้างอยู่)"""
    category = Category.query.get_or_404(category_id)
    
    # ตรวจสอบว่ามี Ticket ในหมวดนี้หรือไม่
    if category.tickets.count() > 0:
        flash(f'ไม่สามารถลบหมวดหมู่ "{category.name}" ได้ เนื่องจากมี Ticket ใช้งานอยู่ ({category.tickets.count()} รายการ)', 'danger')
        return redirect(url_for('admin.category_list'))

    db.session.delete(category)
    db.session.commit()
    flash(f'ลบหมวดหมู่ "{category.name}" เรียบร้อยแล้ว', 'success')
    return redirect(url_for('admin.category_list'))


@admin_bp.route('/audit-log')
@login_required
@admin_required
def audit_log():
    """หน้า Audit Log — ประวัติการดำเนินการทั้งหมด"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()

    query = TicketLog.query

    if search:
        query = query.join(Ticket).filter(
            db.or_(
                TicketLog.action.ilike(f'%{search}%'),
                Ticket.ticket_number.ilike(f'%{search}%'),
            )
        )

    logs = query.order_by(TicketLog.created_at.desc()).paginate(
        page=page, per_page=25, error_out=False
    )

    return render_template('audit_log.html', logs=logs, search=search)


@admin_bp.route('/users')
@login_required
@admin_required
def user_list():
    """หน้าจัดการผู้ใช้"""
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('users.html', users=users)


@admin_bp.route('/users/<int:user_id>/role', methods=['POST'])
@login_required
@admin_required
def change_role(user_id):
    """เปลี่ยน Role ผู้ใช้"""
    if current_user.role != 'Admin':
        flash('เฉพาะ Admin เท่านั้นที่สามารถเปลี่ยน Role ได้', 'danger')
        return redirect(url_for('admin.user_list'))

    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')
    valid_roles = ['Admin', 'Employee', 'Manager', 'Vendor', 'Customer']

    if new_role in valid_roles:
        user.role = new_role
        db.session.commit()
        flash(f'เปลี่ยน Role ของ {user.name} เป็น {new_role} เรียบร้อย', 'success')
    else:
        flash('Role ไม่ถูกต้อง', 'danger')

    return redirect(url_for('admin.user_list'))


@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    """หน้าตั้งค่าระบบ — การแจ้งเตือน"""
    if request.method == 'POST':
        # LINE
        SystemConfig.set('line_enabled', '1' if request.form.get('line_enabled') else '0')
        SystemConfig.set('line_token', request.form.get('line_token', '').strip())
        SystemConfig.set('line_default_group', request.form.get('line_default_group', '').strip())

        # Email
        SystemConfig.set('email_enabled', '1' if request.form.get('email_enabled') else '0')
        SystemConfig.set('smtp_host', request.form.get('smtp_host', '').strip())
        SystemConfig.set('smtp_port', request.form.get('smtp_port', '587').strip())
        SystemConfig.set('smtp_user', request.form.get('smtp_user', '').strip())
        SystemConfig.set('smtp_pass', request.form.get('smtp_pass', '').strip())
        SystemConfig.set('email_default_to', request.form.get('email_default_to', '').strip())

        # Telegram
        SystemConfig.set('telegram_enabled', '1' if request.form.get('telegram_enabled') else '0')
        SystemConfig.set('telegram_token', request.form.get('telegram_token', '').strip())
        SystemConfig.set('telegram_chat_id', request.form.get('telegram_chat_id', '').strip())

        flash('บันทึกการตั้งค่าเรียบร้อย', 'success')
        return redirect(url_for('admin.settings'))

    config = SystemConfig.get_notification_config()
    return render_template('settings.html', config=config)

# --- สิ้นสุดโค้ดที่ถูกต้อง ---