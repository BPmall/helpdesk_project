import os
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import qrcode
from io import BytesIO
from flask import send_file
from ..models import db, Equipment, EquipmentTransaction, Ticket

equipment_bp = Blueprint('equipment', __name__, url_prefix='/equipment')

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_evidence_image(file):
    if file and allowed_file(file.filename):
        # Create a unique filename
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"eq_{uuid.uuid4().hex[:10]}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}"
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        return filename
    return None

@equipment_bp.route('/')
@login_required
def index():
    # Filters
    eq_type = request.args.get('type', 'All')
    status = request.args.get('status', 'All')
    search = request.args.get('search', '')
    
    query = Equipment.query
    
    if eq_type != 'All':
        query = query.filter(Equipment.type == eq_type)
    if status != 'All':
        query = query.filter(Equipment.status == status)
    if search:
        query = query.filter(Equipment.name.ilike(f'%{search}%') | Equipment.code.ilike(f'%{search}%'))
        
    equipments = query.order_by(Equipment.id.desc()).all()
    
    return render_template('equipment/index.html', equipments=equipments, 
                           current_type=eq_type, current_status=status, search=search)

@equipment_bp.route('/add', methods=['POST'])
@login_required
def add():
    name = request.form.get('name')
    eq_type = request.form.get('type')
    description = request.form.get('description')
    image_file = request.files.get('image')
    
    if not name:
        flash('กรุณากรอกชื่ออุปกรณ์', 'danger')
        return redirect(url_for('equipment.index'))
        
    image_filename = None
    if image_file and image_file.filename != '':
        image_filename = save_evidence_image(image_file)
        
    code = Equipment.generate_code()
    
    # ดึงค่าสเปก
    acquired_date_str = request.form.get('acquired_date')
    acquired_date = datetime.strptime(acquired_date_str, '%Y-%m-%d').date() if acquired_date_str else None
    
    warranty_expiry_str = request.form.get('warranty_expiry_date')
    warranty_expiry_date = datetime.strptime(warranty_expiry_str, '%Y-%m-%d').date() if warranty_expiry_str else None

    new_eq = Equipment(
        code=code, name=name, type=eq_type, description=description, status='Available', image=image_filename,
        acquired_date=acquired_date, warranty_info=request.form.get('warranty_info'), 
        warranty_expiry_date=warranty_expiry_date, vendor_name=request.form.get('vendor_name'),
        vendor_contact=request.form.get('vendor_contact'), model=request.form.get('model'),
        voltage=request.form.get('voltage'), power_consumption=request.form.get('power_consumption'),
        current_amps=request.form.get('current_amps'), refrigerant=request.form.get('refrigerant')
    )
    db.session.add(new_eq)
    db.session.commit()
    
    flash(f'เพิ่มอุปกรณ์ {name} ({code}) เรียบร้อยแล้ว', 'success')
    return redirect(url_for('equipment.index'))

@equipment_bp.route('/edit/<int:id>', methods=['POST'])
@login_required
def edit(id):
    eq = Equipment.query.get_or_404(id)
    eq.name = request.form.get('name')
    eq.type = request.form.get('type')
    eq.description = request.form.get('description')
    
    image_file = request.files.get('image')
    if image_file and image_file.filename != '':
        image_filename = save_evidence_image(image_file)
        if image_filename:
            eq.image = image_filename
            
    # อัพเดทสเปก
    acquired_date_str = request.form.get('acquired_date')
    eq.acquired_date = datetime.strptime(acquired_date_str, '%Y-%m-%d').date() if acquired_date_str else None
    
    warranty_expiry_str = request.form.get('warranty_expiry_date')
    eq.warranty_expiry_date = datetime.strptime(warranty_expiry_str, '%Y-%m-%d').date() if warranty_expiry_str else None

    eq.warranty_info = request.form.get('warranty_info')
    eq.vendor_name = request.form.get('vendor_name')
    eq.vendor_contact = request.form.get('vendor_contact')
    eq.model = request.form.get('model')
    eq.voltage = request.form.get('voltage')
    eq.power_consumption = request.form.get('power_consumption')
    eq.current_amps = request.form.get('current_amps')
    eq.refrigerant = request.form.get('refrigerant')
            
    db.session.commit()
    flash('อัพเดทข้อมูลอุปกรณ์เรียบร้อยแล้ว', 'success')
    return redirect(url_for('equipment.index'))

@equipment_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete(id):
    eq = Equipment.query.get_or_404(id)
    # Check if there are transactions
    if eq.transactions.count() > 0:
        flash('ไม่สามารถลบอุปกรณ์ที่มีประวัติการใช้งานได้ กรุณาเปลี่ยนสถานะแทน', 'warning')
        return redirect(url_for('equipment.index'))
        
    db.session.delete(eq)
    db.session.commit()
    flash('ลบอุปกรณ์เรียบร้อยแล้ว', 'success')
    return redirect(url_for('equipment.index'))

@equipment_bp.route('/<int:id>/borrow', methods=['POST'])
@login_required
def borrow(id):
    eq = Equipment.query.get_or_404(id)
    if eq.status != 'Available':
        flash('อุปกรณ์นี้ไม่พร้อมให้ยืม', 'danger')
        return redirect(url_for('equipment.index'))
        
    borrower_name = request.form.get('borrower_name')
    purpose = request.form.get('purpose')
    image_file = request.files.get('evidence_image')
    
    if not image_file or image_file.filename == '':
        flash('กรุณาแนบรูปถ่ายเป็นหลักฐานการยืม (สำคัญ)', 'danger')
        return redirect(url_for('equipment.index'))
        
    image_filename = save_evidence_image(image_file)
    if not image_filename:
        flash('รูปแบบไฟล์ภาพไม่ถูกต้อง', 'danger')
        return redirect(url_for('equipment.index'))
        
    # Update equipment status
    eq.status = 'Borrowed'
    
    # Create transaction
    tx = EquipmentTransaction(
        equipment_id=eq.id,
        transaction_type='Borrow',
        borrower_name=borrower_name,
        purpose=purpose,
        evidence_image=image_filename,
        created_by=current_user.id
    )
    db.session.add(tx)
    db.session.commit()
    
    flash('บันทึกการยืมเรียบร้อยแล้ว', 'success')
    return redirect(url_for('equipment.index'))

@equipment_bp.route('/<int:id>/return', methods=['POST'])
@login_required
def return_eq(id):
    eq = Equipment.query.get_or_404(id)
    if eq.status != 'Borrowed':
        flash('อุปกรณ์นี้ไม่ได้ถูกยืมอยู่', 'danger')
        return redirect(url_for('equipment.index'))
        
    return_status = request.form.get('return_status') # ปกติ, ชำรุด
    notes = request.form.get('notes')
    image_file = request.files.get('evidence_image')
    
    if not image_file or image_file.filename == '':
        flash('กรุณาแนบรูปถ่ายเป็นหลักฐานการคืน (สำคัญ)', 'danger')
        return redirect(url_for('equipment.index'))
        
    image_filename = save_evidence_image(image_file)
    if not image_filename:
        flash('รูปแบบไฟล์ภาพไม่ถูกต้อง', 'danger')
        return redirect(url_for('equipment.index'))
        
    # Get the last borrow transaction to know who borrowed it (optional for reference, but we just record new tx)
    last_borrow = eq.transactions.filter_by(transaction_type='Borrow').order_by(EquipmentTransaction.id.desc()).first()
    borrower_name = last_borrow.borrower_name if last_borrow else 'ไม่ทราบ'
    
    # Update equipment status
    if return_status == 'ชำรุด':
        eq.status = 'Broken'
    else:
        eq.status = 'Available'
        
    # Create transaction
    tx = EquipmentTransaction(
        equipment_id=eq.id,
        transaction_type='Return',
        borrower_name=borrower_name, # Record who is returning (same as borrower usually)
        purpose='คืนอุปกรณ์',
        evidence_image=image_filename,
        return_status=return_status,
        notes=notes,
        created_by=current_user.id
    )
    db.session.add(tx)
    db.session.commit()
    
    flash('บันทึกการคืนเรียบร้อยแล้ว', 'success')
    return redirect(url_for('equipment.index'))

@equipment_bp.route('/<int:id>/report_broken', methods=['POST'])
@login_required
def report_broken(id):
    """แจ้งชำรุดตอนอุปกรณ์อยู่ที่แผนก"""
    eq = Equipment.query.get_or_404(id)
    if eq.status != 'Available':
        flash('อุปกรณ์ไม่อยู่ในสถานะที่แจ้งชำรุดได้', 'danger')
        return redirect(url_for('equipment.index'))
        
    notes = request.form.get('notes')
    
    eq.status = 'Broken'
    
    # Create an informational transaction, or just log. We use transaction table for now.
    tx = EquipmentTransaction(
        equipment_id=eq.id,
        transaction_type='Return', # Using Return as a catch-all for status update, or could be 'Report Broken'
        borrower_name=current_user.name,
        purpose='แจ้งชำรุด',
        evidence_image='N/A', # No image needed just for reporting
        return_status='ชำรุด',
        notes=notes,
        created_by=current_user.id
    )
    db.session.add(tx)
    db.session.commit()
    
    flash('บันทึกสถานะชำรุดเรียบร้อยแล้ว', 'warning')
    return redirect(url_for('equipment.index'))

@equipment_bp.route('/<int:id>/exchange', methods=['POST'])
@login_required
def exchange(id):
    """บันทึกของเก่าแลกของใหม่"""
    eq = Equipment.query.get_or_404(id)
    if eq.status != 'Broken':
        flash('เฉพาะอุปกรณ์ชำรุดเท่านั้นที่สามารถนำไปแลกของใหม่ได้', 'danger')
        return redirect(url_for('equipment.index'))
        
    notes = request.form.get('notes')
    image_file = request.files.get('evidence_image')
    
    if not image_file or image_file.filename == '':
        flash('กรุณาแนบรูปถ่ายหลักฐานการแลกเปลี่ยน', 'danger')
        return redirect(url_for('equipment.index'))
        
    image_filename = save_evidence_image(image_file)
    
    # Update equipment status to Exchanged
    eq.status = 'Exchanged'
    
    tx = EquipmentTransaction(
        equipment_id=eq.id,
        transaction_type='Exchange',
        borrower_name=current_user.name,
        purpose='แลกของใหม่',
        evidence_image=image_filename,
        is_old_for_new=True,
        notes=notes,
        created_by=current_user.id
    )
    db.session.add(tx)
    db.session.commit()
    
    flash('บันทึกการแลกของใหม่เรียบร้อยแล้ว', 'success')
    return redirect(url_for('equipment.index'))

@equipment_bp.route('/<int:id>/history')
@login_required
def history(id):
    eq = Equipment.query.get_or_404(id)
    transactions = eq.transactions.all()
    return render_template('equipment/history.html', equipment=eq, transactions=transactions)

@equipment_bp.route('/<int:id>/details')
def details(id):
    """หน้าแสดงข้อมูลละเอียดและประวัติการซ่อม (สแกนจาก QR Code เข้าหน้านี้ได้)"""
    eq = Equipment.query.get_or_404(id)
    # คำนวณค่าใช้จ่ายในการซ่อมทั้งหมด
    total_repair_cost = 0
    for ticket in eq.tickets:
        for expense in ticket.expenses:
            total_repair_cost += expense.total
            
    return render_template('equipment/details.html', equipment=eq, total_repair_cost=total_repair_cost)

@equipment_bp.route('/<int:id>/qrcode')
def generate_qrcode(id):
    """สร้าง QR Code สำหรับอุปกรณ์"""
    eq = Equipment.query.get_or_404(id)
    # URL ที่จะให้ QR Code ลิงก์ไป
    url = url_for('equipment.details', id=eq.id, _external=True)
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return send_file(img_io, mimetype='image/png')
