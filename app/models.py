from . import db
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


class User(UserMixin, db.Model):
    """ตารางผู้ใช้งาน"""
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='Employee')
    # Role: Admin, Employee, Manager, Vendor, Customer
    department = db.Column(db.String(80))
    avatar = db.Column(db.String(200), default='default.png')
    line_user_id = db.Column(db.String(100))
    is_active_user = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    tickets_created = db.relationship('Ticket', foreign_keys='Ticket.requester_id',
                                      backref='requester', lazy='dynamic')
    tickets_assigned = db.relationship('Ticket', foreign_keys='Ticket.assignee_id',
                                       backref='assignee', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_initials(self):
        """คืนค่าตัวอักษรย่อจากชื่อ เช่น 'สมชาย ใจดี' => 'สม'"""
        if self.name:
            parts = self.name.split()
            if len(parts) >= 2:
                return parts[0][0] + parts[1][0]
            return self.name[0:2]
        return self.username[0:2].upper()


class Category(db.Model):
    """หมวดหมู่งาน"""
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    icon = db.Column(db.String(10), default='🔧')
    tickets = db.relationship('Ticket', backref='category', lazy='dynamic')


class Ticket(db.Model):
    """ตารางใบแจ้งซ่อม"""
    __tablename__ = 'tickets'
    id = db.Column(db.Integer, primary_key=True)
    ticket_number = db.Column(db.String(20), unique=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(50), default='Pending')
    # Status: Pending, Head_Approved, Manager_Approved, In_Progress, Resolved, Rejected, Closed
    priority = db.Column(db.String(20), default='Medium')
    # Priority: Low, Medium, High, Critical
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    equipment_id = db.Column(db.Integer, db.ForeignKey('equipments.id'))  # เชื่อมกับอุปกรณ์ (ถ้าเป็นการแจ้งซ่อมเครื่อง)
    requester_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assignee_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    due_date = db.Column(db.DateTime)
    resolved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    logs = db.relationship('TicketLog', backref='ticket', lazy='dynamic',
                           order_by='TicketLog.created_at.desc()')
    comments = db.relationship('TicketComment', backref='ticket', lazy='dynamic',
                               order_by='TicketComment.created_at.asc()')

    @staticmethod
    def generate_ticket_number():
        """สร้างเลข Ticket อัตโนมัติ เช่น TK-0001"""
        last = Ticket.query.order_by(Ticket.id.desc()).first()
        num = (last.id + 1) if last else 1
        return f"TK-{num:04d}"

    def get_status_thai(self):
        status_map = {
            'Pending': 'รอดำเนินการ',
            'Head_Approved': 'หัวหน้าอนุมัติแล้ว',
            'Manager_Approved': 'ผู้จัดการอนุมัติแล้ว',
            'In_Progress': 'กำลังดำเนินการ',
            'Resolved': 'เสร็จสิ้น',
            'Rejected': 'ปฏิเสธ',
            'Closed': 'ปิดงาน',
        }
        return status_map.get(self.status, self.status)

    def get_priority_thai(self):
        priority_map = {
            'Low': 'ต่ำ',
            'Medium': 'ปานกลาง',
            'High': 'สูง',
            'Critical': 'วิกฤต',
        }
        return priority_map.get(self.priority, self.priority)


class TicketLog(db.Model):
    """ตารางเก็บประวัติการดำเนินการ (Audit Log)"""
    __tablename__ = 'ticket_logs'
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(255), nullable=False)
    old_value = db.Column(db.String(255))
    new_value = db.Column(db.String(255))
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    actor = db.relationship('User', backref='actions')


class TicketComment(db.Model):
    """ตารางข้อความสนทนาภายใน Ticket"""
    __tablename__ = 'ticket_comments'
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='comments')


class FileAttachment(db.Model):
    """ตารางเก็บไฟล์แนบของ Ticket"""
    __tablename__ = 'file_attachments'
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer, default=0)  # bytes
    mime_type = db.Column(db.String(100))
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ticket = db.relationship('Ticket', backref=db.backref('attachments', lazy='dynamic'))
    uploader = db.relationship('User', backref='uploads')

    def get_size_display(self):
        """แสดงขนาดไฟล์แบบอ่านง่าย"""
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        else:
            return f"{self.file_size / (1024 * 1024):.1f} MB"

    def is_image(self):
        return self.mime_type and self.mime_type.startswith('image/')


class SparePart(db.Model):
    """ตารางอะไหล่/วัสดุสิ้นเปลือง"""
    __tablename__ = 'spare_parts'
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), unique=True)  # รหัสอะไหล่
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100), default='ทั่วไป')
    # หมวดหมู่: อะไหล่คอมพิวเตอร์, อุปกรณ์เครือข่าย, อะไหล่อาคาร, วัสดุสำนักงาน, อื่นๆ
    unit = db.Column(db.String(30), default='ชิ้น')  # หน่วยนับ
    unit_price = db.Column(db.Float, default=0)  # ราคาต่อหน่วย
    stock_quantity = db.Column(db.Integer, default=0)  # จำนวนคงเหลือ
    min_stock = db.Column(db.Integer, default=5)  # แจ้งเตือนเมื่อเหลือน้อยกว่า
    location = db.Column(db.String(100))  # ที่เก็บ
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transactions = db.relationship('StockTransaction', backref='spare_part', lazy='dynamic',
                                   order_by='StockTransaction.created_at.desc()')

    def is_low_stock(self):
        return self.stock_quantity <= self.min_stock

    @staticmethod
    def generate_sku():
        last = SparePart.query.order_by(SparePart.id.desc()).first()
        num = (last.id + 1) if last else 1
        return f"SP-{num:04d}"


class StockTransaction(db.Model):
    """ตารางประวัติการเคลื่อนไหวสต๊อก (เข้า/ออก)"""
    __tablename__ = 'stock_transactions'
    id = db.Column(db.Integer, primary_key=True)
    spare_part_id = db.Column(db.Integer, db.ForeignKey('spare_parts.id'), nullable=False)
    transaction_type = db.Column(db.String(10), nullable=False)  # IN (รับเข้า) / OUT (เบิกออก)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, default=0)  # ราคาต่อหน่วย ณ ตอนทำรายการ
    total_price = db.Column(db.Float, default=0)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'))  # เชื่อมกับเคส (ถ้าเบิกออก)
    reference = db.Column(db.String(200))  # เลขที่อ้างอิง/ใบสั่งซื้อ
    note = db.Column(db.Text)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    actor = db.relationship('User', backref='stock_actions')
    ticket = db.relationship('Ticket', backref=db.backref('stock_transactions', lazy='dynamic'))

    def get_type_display(self):
        return 'รับเข้า' if self.transaction_type == 'IN' else 'เบิกออก'


class TicketExpense(db.Model):
    """ตารางค่าใช้จ่ายต่อเคส"""
    __tablename__ = 'ticket_expenses'
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False)
    expense_type = db.Column(db.String(50), nullable=False)
    # ประเภท: parts (อะไหล่), labor (ค่าแรง), outsource (จ้างภายนอก), transport (ค่าเดินทาง), other (อื่นๆ)
    description = db.Column(db.String(300), nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0)
    quantity = db.Column(db.Integer, default=1)
    total = db.Column(db.Float, nullable=False, default=0)  # amount * quantity
    spare_part_id = db.Column(db.Integer, db.ForeignKey('spare_parts.id'))  # ถ้าเป็นอะไหล่
    stock_transaction_id = db.Column(db.Integer, db.ForeignKey('stock_transactions.id'))
    receipt_number = db.Column(db.String(100))  # เลขที่ใบเสร็จ
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ticket = db.relationship('Ticket', backref=db.backref('expenses', lazy='dynamic'))
    spare_part = db.relationship('SparePart', backref='expenses')
    stock_transaction = db.relationship('StockTransaction', backref='expense')
    creator = db.relationship('User', backref='expense_entries')

    EXPENSE_TYPES = {
        'parts': '🔧 อะไหล่',
        'labor': '👷 ค่าแรง',
        'outsource': '🏢 จ้างภายนอก',
        'transport': '🚗 ค่าเดินทาง',
        'other': '📋 อื่นๆ',
    }

    def get_type_display(self):
        return self.EXPENSE_TYPES.get(self.expense_type, self.expense_type)


class SystemConfig(db.Model):
    """ตารางเก็บค่าตั้งค่าระบบ (key-value)"""
    __tablename__ = 'system_config'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, default='')
    description = db.Column(db.String(255))

    @staticmethod
    def get(key, default=''):
        config = SystemConfig.query.filter_by(key=key).first()
        return config.value if config else default

    @staticmethod
    def set(key, value, description=''):
        from . import db as _db
        config = SystemConfig.query.filter_by(key=key).first()
        if config:
            config.value = value
        else:
            config = SystemConfig(key=key, value=value, description=description)
            _db.session.add(config)
        _db.session.commit()

    @staticmethod
    def get_notification_config():
        """คืนค่า config ทั้งหมดสำหรับระบบแจ้งเตือน"""
        keys = [
            'line_enabled', 'line_token', 'line_default_group',
            'email_enabled', 'smtp_host', 'smtp_port', 'smtp_user', 'smtp_pass', 'email_default_to',
            'telegram_enabled', 'telegram_token', 'telegram_chat_id',
        ]
        return {k: SystemConfig.get(k, '') for k in keys}


class KnowledgeArticle(db.Model):
    """ตารางบทความ/ฐานความรู้ (Knowledge Base)"""
    __tablename__ = 'knowledge_articles'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    view_count = db.Column(db.Integer, default=0)
    is_published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = db.relationship('Category', backref='articles')
    author = db.relationship('User', backref='authored_articles')


class Equipment(db.Model):
    """ตารางอุปกรณ์ในแผนก"""
    __tablename__ = 'equipments'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True)  # รหัสอุปกรณ์
    name = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(50), nullable=False, default='Stationary') 
    # ประเภท: Stationary (อยู่กับที่), Mobile (เคลื่อนที่/ติดรถ)
    status = db.Column(db.String(50), default='Available')
    # สถานะ: Available (พร้อมใช้งาน), Borrowed (ถูกยืม), Broken (ชำรุด), Exchanged (แลกของใหม่แล้ว)
    description = db.Column(db.Text)
    image = db.Column(db.String(255))
    
    # --- ข้อมูลเชิงลึก & ประกัน (Warranty & Vendor) ---
    acquired_date = db.Column(db.Date) # วันที่ได้เครื่องมา
    warranty_info = db.Column(db.String(255)) # เงื่อนไขประกัน
    warranty_expiry_date = db.Column(db.Date) # วันหมดประกัน
    vendor_name = db.Column(db.String(200)) # ชื่อร้าน/ผู้ขาย
    vendor_contact = db.Column(db.String(255)) # ข้อมูลติดต่อผู้ขาย
    
    # --- ข้อมูลสเปกเครื่อง (Specs สำหรับแสดงใน QR Code) ---
    model = db.Column(db.String(100)) # รุ่นเครื่อง
    voltage = db.Column(db.String(50)) # แรงดันไฟฟ้า (เช่น 220V)
    power_consumption = db.Column(db.String(50)) # กำลังไฟฟ้า (เช่น 1500W)
    current_amps = db.Column(db.String(50)) # กระแสไฟฟ้า (เช่น 5A)
    refrigerant = db.Column(db.String(50)) # สารทำความเย็น (เช่น R-134a)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transactions = db.relationship('EquipmentTransaction', backref='equipment', lazy='dynamic',
                                   order_by='EquipmentTransaction.created_at.desc()')
    tickets = db.relationship('Ticket', backref='equipment_ref', lazy='dynamic') # ประวัติการซ่อมของเครื่องนี้

    @staticmethod
    def generate_code():
        last = Equipment.query.order_by(Equipment.id.desc()).first()
        num = (last.id + 1) if last else 1
        return f"EQ-{num:04d}"
        
    def get_type_thai(self):
        types = {'Stationary': 'อยู่กับที่', 'Mobile': 'เคลื่อนที่'}
        return types.get(self.type, self.type)
        
    def get_status_thai(self):
        statuses = {
            'Available': 'พร้อมใช้งาน',
            'Borrowed': 'ถูกยืม',
            'Broken': 'ชำรุด/เสียหาย',
            'Exchanged': 'แลกของใหม่แล้ว'
        }
        return statuses.get(self.status, self.status)


class EquipmentTransaction(db.Model):
    """ตารางประวัติการยืม-คืนอุปกรณ์"""
    __tablename__ = 'equipment_transactions'
    id = db.Column(db.Integer, primary_key=True)
    equipment_id = db.Column(db.Integer, db.ForeignKey('equipments.id'), nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)  # Borrow (ยืม), Return (คืน), Exchange (แลกของใหม่)
    
    borrower_name = db.Column(db.String(150), nullable=False)  # ใครยืม
    purpose = db.Column(db.String(255))  # ยืมไปทำอะไร
    
    # รูปถ่ายจำเป็น (ไม่มีรูปไม่จบการทำงาน)
    evidence_image = db.Column(db.String(255), nullable=False) 
    
    # สำหรับตอนคืน หรือตอนแจ้งชำรุด
    return_status = db.Column(db.String(50)) # ปกติ, ชำรุด
    is_old_for_new = db.Column(db.Boolean, default=False) # บันทึกของเก่าแลกของใหม่
    
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    creator = db.relationship('User', backref='equipment_actions')
    
    def get_transaction_type_thai(self):
        types = {'Borrow': 'ยืม', 'Return': 'คืน', 'Exchange': 'แลกของใหม่'}
        return types.get(self.transaction_type, self.transaction_type)


class BranchChecklist(db.Model):
    """เช็กลิสต์ซ่อมบำรุงตามรอบเวลาและสาขา"""
    __tablename__ = 'branch_checklists'
    id = db.Column(db.Integer, primary_key=True)
    branch_name = db.Column(db.String(150), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    period_type = db.Column(db.String(20), nullable=False, default='daily')  # daily/monthly/yearly
    checklist_date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship('User', backref='branch_checklists')

    PERIOD_LABELS = {
        'daily': 'รายวัน',
        'monthly': 'รายเดือน',
        'yearly': 'รายปี'
    }

    def get_period_type_thai(self):
        return self.PERIOD_LABELS.get(self.period_type, self.period_type)

