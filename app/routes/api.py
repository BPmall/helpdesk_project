from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from ..models import Ticket, User, Category, TicketLog, TicketComment
from ..utils import to_buddhist_era
from .. import db, csrf

api_bp = Blueprint('api', __name__, url_prefix='/api/v1')

# ปิด CSRF สำหรับ API (ใช้ Token Auth แทนในอนาคต)
csrf.exempt(api_bp)


def ticket_to_dict(t):
    """แปลง Ticket object เป็น dictionary"""
    return {
        'id': t.id,
        'ticket_number': t.ticket_number,
        'title': t.title,
        'description': t.description,
        'status': t.status,
        'status_thai': t.get_status_thai(),
        'priority': t.priority,
        'priority_thai': t.get_priority_thai(),
        'category': t.category.name if t.category else None,
        'requester': t.requester.name if t.requester else None,
        'assignee': t.assignee.name if t.assignee else None,
        'created_at': t.created_at.isoformat() if t.created_at else None,
        'created_at_thai': to_buddhist_era(t.created_at),
        'resolved_at': t.resolved_at.isoformat() if t.resolved_at else None,
    }


# ==========================================
# Tickets API
# ==========================================

@api_bp.route('/tickets', methods=['GET'])
@login_required
def get_tickets():
    """GET /api/v1/tickets — ดึงรายการ Ticket ทั้งหมด"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', '')
    priority = request.args.get('priority', '')
    search = request.args.get('search', '')

    query = Ticket.query
    if status:
        query = query.filter_by(status=status)
    if priority:
        query = query.filter_by(priority=priority)
    if search:
        query = query.filter(Ticket.title.ilike(f'%{search}%'))

    pagination = query.order_by(Ticket.created_at.desc()).paginate(
        page=page, per_page=min(per_page, 100), error_out=False
    )

    return jsonify({
        'success': True,
        'data': [ticket_to_dict(t) for t in pagination.items],
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages,
        }
    })


@api_bp.route('/tickets/<int:ticket_id>', methods=['GET'])
@login_required
def get_ticket(ticket_id):
    """GET /api/v1/tickets/:id — ดึงรายละเอียด Ticket"""
    ticket = Ticket.query.get_or_404(ticket_id)
    data = ticket_to_dict(ticket)
    data['comments'] = [{
        'id': c.id,
        'user': c.user.name,
        'message': c.message,
        'created_at': to_buddhist_era(c.created_at),
    } for c in ticket.comments.all()]
    data['logs'] = [{
        'id': l.id,
        'actor': l.actor.name,
        'action': l.action,
        'old_value': l.old_value,
        'new_value': l.new_value,
        'comment': l.comment,
        'created_at': to_buddhist_era(l.created_at),
    } for l in ticket.logs.all()]
    return jsonify({'success': True, 'data': data})


@api_bp.route('/tickets', methods=['POST'])
@login_required
def create_ticket():
    """POST /api/v1/tickets — สร้าง Ticket ใหม่"""
    data = request.get_json()
    if not data or not data.get('title'):
        return jsonify({'success': False, 'error': 'title is required'}), 400

    ticket = Ticket(
        ticket_number=Ticket.generate_ticket_number(),
        title=data['title'],
        description=data.get('description', ''),
        priority=data.get('priority', 'Medium'),
        category_id=data.get('category_id'),
        requester_id=current_user.id,
        status='Pending',
    )
    db.session.add(ticket)
    db.session.flush()

    log = TicketLog(ticket_id=ticket.id, actor_id=current_user.id,
                    action='สร้างใบแจ้งซ่อม (API)', new_value='Pending')
    db.session.add(log)
    db.session.commit()

    return jsonify({'success': True, 'data': ticket_to_dict(ticket)}), 201


@api_bp.route('/tickets/<int:ticket_id>/status', methods=['PUT'])
@login_required
def update_status(ticket_id):
    """PUT /api/v1/tickets/:id/status — เปลี่ยนสถานะ Ticket"""
    ticket = Ticket.query.get_or_404(ticket_id)
    data = request.get_json()
    new_status = data.get('status') if data else None

    from ..utils import get_allowed_statuses
    allowed = get_allowed_statuses(ticket.status, current_user.role)
    if new_status not in allowed:
        return jsonify({'success': False, 'error': 'status not allowed'}), 403

    old = ticket.status
    ticket.status = new_status
    log = TicketLog(ticket_id=ticket.id, actor_id=current_user.id,
                    action='เปลี่ยนสถานะ (API)', old_value=old, new_value=new_status)
    db.session.add(log)
    db.session.commit()

    return jsonify({'success': True, 'data': ticket_to_dict(ticket)})


# ==========================================
# Users / Categories API
# ==========================================

@api_bp.route('/users', methods=['GET'])
@login_required
def get_users():
    """GET /api/v1/users — ดึงรายการผู้ใช้"""
    users = User.query.all()
    return jsonify({
        'success': True,
        'data': [{
            'id': u.id, 'username': u.username, 'name': u.name,
            'email': u.email, 'role': u.role, 'department': u.department,
        } for u in users]
    })


@api_bp.route('/categories', methods=['GET'])
@login_required
def get_categories():
    """GET /api/v1/categories — ดึงรายการหมวดหมู่"""
    cats = Category.query.all()
    return jsonify({
        'success': True,
        'data': [{'id': c.id, 'name': c.name, 'icon': c.icon, 'description': c.description} for c in cats]
    })


# ==========================================
# Statistics API
# ==========================================

@api_bp.route('/stats', methods=['GET'])
@login_required
def get_stats():
    """GET /api/v1/stats — ดึงสถิติ"""
    from sqlalchemy import func
    total = Ticket.query.count()
    by_status = dict(db.session.query(Ticket.status, func.count(Ticket.id)).group_by(Ticket.status).all())
    by_priority = dict(db.session.query(Ticket.priority, func.count(Ticket.id)).group_by(Ticket.priority).all())

    return jsonify({
        'success': True,
        'data': {
            'total': total,
            'by_status': by_status,
            'by_priority': by_priority,
        }
    })


# ==========================================
# Calendar Events API
# ==========================================

@api_bp.route('/calendar/events', methods=['GET'])
@login_required
def calendar_events():
    """GET /api/v1/calendar/events — ดึงข้อมูล Ticket สำหรับ Calendar"""
    tickets = Ticket.query.all()
    color_map = {
        'Pending': '#3B82F6', 'Head_Approved': '#8B5CF6',
        'Manager_Approved': '#6366F1', 'In_Progress': '#F59E0B',
        'Resolved': '#10B981', 'Rejected': '#EF4444', 'Closed': '#6B7280',
    }
    events = []
    for t in tickets:
        events.append({
            'id': t.id,
            'title': f'{t.ticket_number} — {t.title}',
            'start': t.created_at.strftime('%Y-%m-%d') if t.created_at else None,
            'end': t.resolved_at.strftime('%Y-%m-%d') if t.resolved_at else None,
            'color': color_map.get(t.status, '#9CA3AF'),
            'url': f'/tickets/{t.id}',
        })
    return jsonify(events)
