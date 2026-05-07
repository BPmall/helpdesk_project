from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from ..models import SparePart, StockTransaction, Ticket, TicketExpense
from .. import db
from functools import wraps

inventory_bp = Blueprint('inventory', __name__, url_prefix='/inventory')


def admin_manager_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['Admin', 'Manager']:
            flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function


# ==========================================
# สต๊อกอะไหล่
# ==========================================

@inventory_bp.route('/')
@login_required
def stock_list():
    """หน้ารายการอะไหล่ทั้งหมด"""
    search = request.args.get('search', '').strip()
    category = request.args.get('category', '')
    low_stock = request.args.get('low_stock', '')

    query = SparePart.query.filter_by(is_active=True)

    if search:
        query = query.filter(
            db.or_(
                SparePart.name.ilike(f'%{search}%'),
                SparePart.sku.ilike(f'%{search}%'),
            )
        )
    if category:
        query = query.filter_by(category=category)
    if low_stock:
        query = query.filter(SparePart.stock_quantity <= SparePart.min_stock)

    parts = query.order_by(SparePart.name).all()

    categories = db.session.query(SparePart.category).distinct().all()
    categories = [c[0] for c in categories if c[0]]

    total_value = sum(p.unit_price * p.stock_quantity for p in parts)
    low_count = sum(1 for p in parts if p.is_low_stock())

    # Ticket ที่ยังเปิดอยู่ (สำหรับ modal เบิกออก)
    open_tickets = Ticket.query.filter(
        Ticket.status.notin_(['Closed', 'Resolved', 'Rejected'])
    ).order_by(Ticket.created_at.desc()).all()

    return render_template('inventory.html',
                           parts=parts,
                           categories=categories,
                           search=search,
                           category_filter=category,
                           low_stock_filter=low_stock,
                           total_value=total_value,
                           low_count=low_count,
                           open_tickets=open_tickets)


@inventory_bp.route('/add', methods=['GET', 'POST'])
@login_required
@admin_manager_required
def add_part():
    """เพิ่มอะไหล่ใหม่"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('กรุณากรอกชื่ออะไหล่', 'danger')
            return redirect(url_for('inventory.add_part'))

        part = SparePart(
            sku=request.form.get('sku', '').strip() or SparePart.generate_sku(),
            name=name,
            category=request.form.get('category', 'ทั่วไป').strip(),
            unit=request.form.get('unit', 'ชิ้น').strip(),
            unit_price=float(request.form.get('unit_price', 0) or 0),
            stock_quantity=int(request.form.get('stock_quantity', 0) or 0),
            min_stock=int(request.form.get('min_stock', 5) or 5),
            location=request.form.get('location', '').strip(),
            description=request.form.get('description', '').strip(),
        )
        db.session.add(part)

        # ถ้ามีจำนวนเริ่มต้น ให้สร้าง transaction
        if part.stock_quantity > 0:
            db.session.flush()
            txn = StockTransaction(
                spare_part_id=part.id,
                transaction_type='IN',
                quantity=part.stock_quantity,
                unit_price=part.unit_price,
                total_price=part.unit_price * part.stock_quantity,
                reference='เปิดสต๊อกเริ่มต้น',
                actor_id=current_user.id,
            )
            db.session.add(txn)

        db.session.commit()
        flash(f'เพิ่มอะไหล่ "{name}" เรียบร้อย', 'success')
        return redirect(url_for('inventory.stock_list'))

    return render_template('inventory_form.html', part=None, action='add')


@inventory_bp.route('/<int:part_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_manager_required
def edit_part(part_id):
    """แก้ไขอะไหล่"""
    part = SparePart.query.get_or_404(part_id)

    if request.method == 'POST':
        part.name = request.form.get('name', '').strip()
        part.category = request.form.get('category', 'ทั่วไป').strip()
        part.unit = request.form.get('unit', 'ชิ้น').strip()
        part.unit_price = float(request.form.get('unit_price', 0) or 0)
        part.min_stock = int(request.form.get('min_stock', 5) or 5)
        part.location = request.form.get('location', '').strip()
        part.description = request.form.get('description', '').strip()
        db.session.commit()
        flash('แก้ไขข้อมูลอะไหล่เรียบร้อย', 'success')
        return redirect(url_for('inventory.stock_list'))

    return render_template('inventory_form.html', part=part, action='edit')


@inventory_bp.route('/<int:part_id>/stock-in', methods=['POST'])
@login_required
@admin_manager_required
def stock_in(part_id):
    """รับสต๊อกเข้า"""
    part = SparePart.query.get_or_404(part_id)
    quantity = int(request.form.get('quantity', 0))
    unit_price = float(request.form.get('unit_price', part.unit_price) or part.unit_price)
    reference = request.form.get('reference', '').strip()
    note = request.form.get('note', '').strip()

    if quantity <= 0:
        flash('จำนวนต้องมากกว่า 0', 'danger')
        return redirect(url_for('inventory.stock_list'))

    part.stock_quantity += quantity
    part.unit_price = unit_price  # อัปเดตราคาล่าสุด

    txn = StockTransaction(
        spare_part_id=part.id,
        transaction_type='IN',
        quantity=quantity,
        unit_price=unit_price,
        total_price=unit_price * quantity,
        reference=reference,
        note=note,
        actor_id=current_user.id,
    )
    db.session.add(txn)
    db.session.commit()

    flash(f'รับเข้า {part.name} จำนวน {quantity} {part.unit} เรียบร้อย', 'success')
    return redirect(url_for('inventory.stock_list'))


@inventory_bp.route('/<int:part_id>/stock-out', methods=['POST'])
@login_required
def stock_out(part_id):
    """เบิกสต๊อกออก (เชื่อมกับ Ticket)"""
    part = SparePart.query.get_or_404(part_id)
    quantity = int(request.form.get('quantity', 0))
    ticket_id = request.form.get('ticket_id', type=int)
    note = request.form.get('note', '').strip()

    if quantity <= 0:
        flash('จำนวนต้องมากกว่า 0', 'danger')
        return redirect(url_for('inventory.stock_list'))

    if quantity > part.stock_quantity:
        flash(f'สต๊อกไม่เพียงพอ (คงเหลือ {part.stock_quantity} {part.unit})', 'danger')
        return redirect(url_for('inventory.stock_list'))

    part.stock_quantity -= quantity

    txn = StockTransaction(
        spare_part_id=part.id,
        transaction_type='OUT',
        quantity=quantity,
        unit_price=part.unit_price,
        total_price=part.unit_price * quantity,
        ticket_id=ticket_id,
        note=note,
        actor_id=current_user.id,
    )
    db.session.add(txn)
    db.session.flush()

    # ถ้าเชื่อมกับ Ticket ให้สร้าง Expense อัตโนมัติ
    if ticket_id:
        expense = TicketExpense(
            ticket_id=ticket_id,
            expense_type='parts',
            description=f'{part.name} ({part.sku})',
            amount=part.unit_price,
            quantity=quantity,
            total=part.unit_price * quantity,
            spare_part_id=part.id,
            stock_transaction_id=txn.id,
            created_by=current_user.id,
        )
        db.session.add(expense)

    db.session.commit()

    flash(f'เบิก {part.name} จำนวน {quantity} {part.unit} เรียบร้อย', 'success')
    if ticket_id:
        return redirect(url_for('tickets.ticket_detail', ticket_id=ticket_id))
    return redirect(url_for('inventory.stock_list'))


@inventory_bp.route('/history')
@login_required
def stock_history():
    """ประวัติเคลื่อนไหวสต๊อกทั้งหมด"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    txn_type = request.args.get('type', '')

    query = StockTransaction.query

    if search:
        query = query.join(SparePart).filter(
            db.or_(
                SparePart.name.ilike(f'%{search}%'),
                SparePart.sku.ilike(f'%{search}%'),
                StockTransaction.reference.ilike(f'%{search}%'),
            )
        )
    if txn_type:
        query = query.filter_by(transaction_type=txn_type)

    transactions = query.order_by(StockTransaction.created_at.desc()).paginate(
        page=page, per_page=25, error_out=False
    )

    return render_template('stock_history.html',
                           transactions=transactions,
                           search=search,
                           type_filter=txn_type)
