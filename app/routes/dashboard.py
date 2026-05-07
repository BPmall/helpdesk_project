from flask import Blueprint, render_template, jsonify, make_response
from flask_login import login_required, current_user
from ..models import Ticket, User, Category
from .. import db
from sqlalchemy import func

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/health')
@dashboard_bp.route('/ping')
def health():
    response = make_response('OK', 200)
    response.headers['Content-Type'] = 'text/plain'
    return response


@dashboard_bp.route('/')
@login_required
def index():
    # นับจำนวน Ticket ตามสถานะ
    total = Ticket.query.count()
    pending = Ticket.query.filter(Ticket.status.in_(['Pending', 'Head_Approved', 'Manager_Approved'])).count()
    in_progress = Ticket.query.filter_by(status='In_Progress').count()
    resolved = Ticket.query.filter(Ticket.status.in_(['Resolved', 'Closed'])).count()
    rejected = Ticket.query.filter_by(status='Rejected').count()

    # ดึง Ticket ล่าสุด 10 รายการ
    recent_tickets = Ticket.query.order_by(Ticket.created_at.desc()).limit(10).all()

    return render_template('index.html',
                           total=total,
                           pending=pending,
                           in_progress=in_progress,
                           resolved=resolved,
                           rejected=rejected,
                           recent_tickets=recent_tickets)


@dashboard_bp.route('/api/chart/status')
@login_required
def chart_status():
    """API สำหรับกราฟวงกลม — สัดส่วนสถานะ Ticket"""
    results = db.session.query(
        Ticket.status, func.count(Ticket.id)
    ).group_by(Ticket.status).all()

    labels = []
    data = []
    colors = []
    color_map = {
        'Pending': '#3B82F6',
        'Head_Approved': '#8B5CF6',
        'Manager_Approved': '#6366F1',
        'In_Progress': '#F59E0B',
        'Resolved': '#10B981',
        'Rejected': '#EF4444',
        'Closed': '#6B7280',
    }
    label_map = {
        'Pending': 'รอดำเนินการ',
        'Head_Approved': 'หัวหน้าอนุมัติ',
        'Manager_Approved': 'ผจก.อนุมัติ',
        'In_Progress': 'กำลังแก้ไข',
        'Resolved': 'เสร็จสิ้น',
        'Rejected': 'ปฏิเสธ',
        'Closed': 'ปิดงาน',
    }

    for status, count in results:
        labels.append(label_map.get(status, status))
        data.append(count)
        colors.append(color_map.get(status, '#9CA3AF'))

    return jsonify({'labels': labels, 'data': data, 'colors': colors})


@dashboard_bp.route('/api/chart/priority')
@login_required
def chart_priority():
    """API สำหรับกราฟแท่ง — จำนวน Ticket แยกตามความสำคัญ"""
    results = db.session.query(
        Ticket.priority, func.count(Ticket.id)
    ).group_by(Ticket.priority).all()

    label_map = {'Low': 'ต่ำ', 'Medium': 'ปานกลาง', 'High': 'สูง', 'Critical': 'วิกฤต'}
    color_map = {'Low': '#6B7280', 'Medium': '#F59E0B', 'High': '#F97316', 'Critical': '#EF4444'}

    labels = []
    data = []
    colors = []
    for priority, count in results:
        labels.append(label_map.get(priority, priority))
        data.append(count)
        colors.append(color_map.get(priority, '#9CA3AF'))

    return jsonify({'labels': labels, 'data': data, 'colors': colors})


@dashboard_bp.route('/api/chart/category')
@login_required
def chart_category():
    """API สำหรับกราฟแท่ง — จำนวน Ticket แยกตามหมวดหมู่"""
    results = db.session.query(
        Category.name, func.count(Ticket.id)
    ).join(Ticket, Ticket.category_id == Category.id
    ).group_by(Category.name).all()

    return jsonify({
        'labels': [r[0] for r in results],
        'data': [r[1] for r in results],
    })


@dashboard_bp.route('/calendar')
@login_required
def calendar():
    """หน้าปฏิทินงาน"""
    return render_template('calendar.html')


@dashboard_bp.route('/api-docs')
@login_required
def api_docs():
    """หน้า API Documentation"""
    return render_template('api_docs.html')


@dashboard_bp.route('/er-diagram')
@login_required
def er_diagram():
    """หน้า ER Diagram Database Schema"""
    return render_template('er_diagram.html')

