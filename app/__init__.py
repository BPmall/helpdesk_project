import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager

db = SQLAlchemy()
csrf = CSRFProtect()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__)

    # ======= Config =======
    from dotenv import load_dotenv
    load_dotenv()

    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'helpdesk-secret-key-change-in-production')

    # รองรับทั้ง PostgreSQL (Railway) และ SQLite (local)
    database_url = os.environ.get('DATABASE_URL', '')
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    if not database_url:
        database_url = 'sqlite:///' + os.path.join(basedir, '..', 'instance', 'helpdesk.db')

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static', 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload

    # สร้างโฟลเดอร์ที่จำเป็น
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(basedir, '..', 'instance'), exist_ok=True)

    # ======= Init Extensions =======
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'กรุณาเข้าสู่ระบบก่อนใช้งาน'
    login_manager.login_message_category = 'warning'

    # ======= User Loader =======
    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # ======= Register Blueprints =======
    from .routes.auth import auth_bp
    from .routes.dashboard import dashboard_bp
    from .routes.tickets import tickets_bp
    from .routes.admin import admin_bp
    from .routes.api import api_bp
    from .routes.inventory import inventory_bp
    from .routes.finance import finance_bp
    from .routes.knowledge import knowledge_bp
    from .routes.equipment import equipment_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(tickets_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(finance_bp)
    app.register_blueprint(knowledge_bp)
    app.register_blueprint(equipment_bp)

    # ======= Context Processor (ตัวแปรที่ใช้ได้ทุกหน้า) =======
    from .utils import to_buddhist_era, get_allowed_statuses, STATUS_LABELS

    @app.context_processor
    def utility_processor():
        return dict(
            to_buddhist_era=to_buddhist_era,
            get_allowed_statuses=get_allowed_statuses,
            STATUS_LABELS=STATUS_LABELS,
        )

    # ======= Create DB & Seed Data =======
    with app.app_context():
        db.create_all()
        _seed_data()

    return app


def _seed_data():
    """สร้างข้อมูลตัวอย่างเริ่มต้น (ถ้ายังไม่มี)"""
    from .models import User, Category, Ticket, TicketLog, FileAttachment, SparePart, StockTransaction, TicketExpense, KnowledgeArticle, Equipment, EquipmentTransaction

    # ถ้ามีข้อมูลแล้ว ไม่ต้องสร้างซ้ำ
    if User.query.first():
        return

    # === สร้างผู้ใช้ตัวอย่าง ===
    users = [
        User(username='admin', email='admin@company.com', name='ผู้ดูแลระบบ',
             role='Admin', department='IT'),
        User(username='somchai', email='somchai@company.com', name='สมชาย ใจดี',
             role='Employee', department='บัญชี'),
        User(username='somying', email='somying@company.com', name='สมหญิง สวยงาม',
             role='Employee', department='การตลาด'),
        User(username='manager1', email='manager@company.com', name='วิชัย มั่นคง',
             role='Manager', department='บัญชี'),
        User(username='head1', email='head@company.com', name='ประภาส รุ่งเรือง',
             role='Manager', department='IT'),
    ]
    for u in users:
        u.set_password('1234')  # รหัสเริ่มต้น
    db.session.add_all(users)
    db.session.commit()

    # === สร้างหมวดหมู่ ===
    categories = [
        Category(name='ซ่อมคอมพิวเตอร์', description='ปัญหาเกี่ยวกับคอมพิวเตอร์และอุปกรณ์ IT', icon='💻'),
        Category(name='ระบบเครือข่าย', description='อินเทอร์เน็ต, WiFi, VPN', icon='🌐'),
        Category(name='ซ่อมบำรุงอาคาร', description='แอร์, ไฟฟ้า, ประปา', icon='🏢'),
        Category(name='เบิกอุปกรณ์', description='ขอเบิกอุปกรณ์สำนักงาน', icon='📦'),
        Category(name='ซอฟต์แวร์', description='ติดตั้งโปรแกรม, ปัญหาซอฟต์แวร์', icon='💿'),
        Category(name='อื่นๆ', description='ปัญหาทั่วไปที่ไม่เข้าหมวดหมู่', icon='📋'),
    ]
    db.session.add_all(categories)
    db.session.commit()

    # === สร้าง Ticket ตัวอย่าง ===
    sample_tickets = [
        Ticket(ticket_number='TK-0001', title='อินเทอร์เน็ตที่แผนกบัญชีใช้งานไม่ได้',
               description='ใช้งานอินเทอร์เน็ตไม่ได้ตั้งแต่เช้า ลองรีสตาร์ทเครื่องแล้วก็ไม่หาย',
               status='Pending', priority='High', category_id=2,
               requester_id=2, assignee_id=1),
        Ticket(ticket_number='TK-0002', title='ขอเบิกเมาส์และคีย์บอร์ดใหม่',
               description='เมาส์เสีย กดคลิกแล้วไม่ตอบสนอง ต้องการเปลี่ยนใหม่',
               status='In_Progress', priority='Low', category_id=4,
               requester_id=3, assignee_id=1),
        Ticket(ticket_number='TK-0003', title='แอร์ห้องประชุม 2 น้ำแอร์หยด',
               description='น้ำหยดจากแอร์เวลาเปิดใช้งานนานกว่า 2 ชั่วโมง',
               status='Resolved', priority='Medium', category_id=3,
               requester_id=4, assignee_id=5),
        Ticket(ticket_number='TK-0004', title='ติดตั้ง Microsoft Office ใหม่',
               description='เครื่องใหม่ยังไม่มีโปรแกรม Office ช่วยติดตั้งให้ด้วยค่ะ',
               status='Head_Approved', priority='Medium', category_id=5,
               requester_id=3),
        Ticket(ticket_number='TK-0005', title='พรินเตอร์ชั้น 3 พิมพ์ไม่ออก',
               description='เครื่องพิมพ์สั่งพิมพ์แล้วไม่ออก สถานะขึ้น Error',
               status='Pending', priority='High', category_id=1,
               requester_id=2),
    ]
    db.session.add_all(sample_tickets)
    db.session.commit()

    # === สร้าง Log ตัวอย่าง ===
    logs = [
        TicketLog(ticket_id=1, actor_id=2, action='สร้างใบแจ้งซ่อม'),
        TicketLog(ticket_id=2, actor_id=3, action='สร้างใบแจ้งซ่อม'),
        TicketLog(ticket_id=2, actor_id=1, action='เปลี่ยนสถานะ',
                  old_value='Pending', new_value='In_Progress', comment='รับงานแล้ว กำลังจัดเตรียมอุปกรณ์'),
        TicketLog(ticket_id=3, actor_id=4, action='สร้างใบแจ้งซ่อม'),
        TicketLog(ticket_id=3, actor_id=5, action='เปลี่ยนสถานะ',
                  old_value='Pending', new_value='Resolved', comment='ช่างมาซ่อมเรียบร้อยแล้ว'),
    ]
    db.session.add_all(logs)
    db.session.commit()

    # === สร้างอะไหล่ตัวอย่าง ===
    parts = [
        SparePart(sku='SP-0001', name='เมาส์ Logitech B100', category='อุปกรณ์คอมพิวเตอร์',
                  unit='ตัว', unit_price=290, stock_quantity=25, min_stock=5, location='ชั้น A1'),
        SparePart(sku='SP-0002', name='คีย์บอร์ด Logitech K120', category='อุปกรณ์คอมพิวเตอร์',
                  unit='ตัว', unit_price=390, stock_quantity=15, min_stock=5, location='ชั้น A1'),
        SparePart(sku='SP-0003', name='หมึกพิมพ์ HP 680 Black', category='วัสดุสิ้นเปลือง',
                  unit='ตลับ', unit_price=350, stock_quantity=10, min_stock=3, location='ชั้น B2'),
        SparePart(sku='SP-0004', name='หมึกพิมพ์ HP 680 Color', category='วัสดุสิ้นเปลือง',
                  unit='ตลับ', unit_price=420, stock_quantity=8, min_stock=3, location='ชั้น B2'),
        SparePart(sku='SP-0005', name='สาย LAN Cat6 (3m)', category='อุปกรณ์เครือข่าย',
                  unit='เส้น', unit_price=80, stock_quantity=30, min_stock=10, location='ชั้น C1'),
        SparePart(sku='SP-0006', name='HDD 1TB Seagate', category='อุปกรณ์คอมพิวเตอร์',
                  unit='ตัว', unit_price=1490, stock_quantity=5, min_stock=2, location='ชั้น A3'),
        SparePart(sku='SP-0007', name='RAM DDR4 8GB', category='อุปกรณ์คอมพิวเตอร์',
                  unit='แถว', unit_price=890, stock_quantity=4, min_stock=3, location='ชั้น A3'),
        SparePart(sku='SP-0008', name='ปลั๊กพ่วง 6 ช่อง', category='อุปกรณ์ไฟฟ้า',
                  unit='อัน', unit_price=250, stock_quantity=12, min_stock=5, location='ชั้น D1'),
        SparePart(sku='SP-0009', name='หลอดไฟ LED 18W', category='อุปกรณ์ไฟฟ้า',
                  unit='หลอด', unit_price=120, stock_quantity=20, min_stock=10, location='ชั้น D2'),
        SparePart(sku='SP-0010', name='น้ำยาล้างแอร์', category='วัสดุซ่อมบำรุง',
                  unit='ขวด', unit_price=180, stock_quantity=6, min_stock=3, location='ชั้น E1'),
    ]
    db.session.add_all(parts)
    db.session.commit()

    # === ค่าใช้จ่ายตัวอย่างสำหรับ Ticket ===
    expenses = [
        TicketExpense(ticket_id=2, expense_type='parts', description='เมาส์ Logitech B100 (SP-0001)',
                      amount=290, quantity=1, total=290, spare_part_id=1, created_by=1),
        TicketExpense(ticket_id=2, expense_type='parts', description='คีย์บอร์ด Logitech K120 (SP-0002)',
                      amount=390, quantity=1, total=390, spare_part_id=2, created_by=1),
        TicketExpense(ticket_id=3, expense_type='outsource', description='ค่าช่างซ่อมแอร์',
                      amount=1500, quantity=1, total=1500, receipt_number='INV-2026-042', created_by=5),
        TicketExpense(ticket_id=3, expense_type='parts', description='น้ำยาล้างแอร์',
                      amount=180, quantity=2, total=360, spare_part_id=10, created_by=5),
        TicketExpense(ticket_id=1, expense_type='transport', description='ค่าเดินทางไปตรวจสอบ',
                      amount=200, quantity=1, total=200, created_by=1),
    ]
    db.session.add_all(expenses)
    db.session.commit()

    # === บทความตัวอย่าง ===
    articles = [
        KnowledgeArticle(
            title='วิธีตั้งค่าเครื่องพิมพ์ (Printer) ของสำนักงาน',
            content='1. เปิด Control Panel<br>2. เลือก Devices and Printers<br>3. คลิก Add a printer<br>4. เลือกเครื่องพิมพ์ที่ต้องการและกด Next',
            category_id=1,
            author_id=1,
            view_count=12
        ),
        KnowledgeArticle(
            title='วิธีแก้ไขปัญหาเบื้องต้นเมื่อต่อ WiFi ไม่ได้',
            content='หากท่านไม่สามารถเชื่อมต่อ WiFi ได้ ลองทำตามขั้นตอนนี้:<br>1. ตรวจสอบว่าเปิดโหมดเครื่องบิน (Airplane Mode) ไว้หรือไม่<br>2. ปิดและเปิด WiFi ใหม่<br>3. Forget network และลองกรอกรหัสผ่านใหม่<br>4. หากยังไม่ได้ กรุณาปิด-เปิดเครื่องคอมพิวเตอร์ 1 ครั้ง',
            category_id=2,
            author_id=5,
            view_count=35
        )
    ]
    db.session.add_all(articles)
    db.session.commit()

    # === อุปกรณ์ในแผนกตัวอย่าง ===
    equipments = [
        Equipment(code='EQ-0001', name='สว่านไฟฟ้า Bosch', type='Mobile', status='Available', description='สว่านกระแทกสำหรับงานช่างทั่วไป'),
        Equipment(code='EQ-0002', name='เครื่องเป่าลมร้อน', type='Mobile', status='Borrowed', description='ใช้เป่าท่อหด หรือพลาสติก'),
        Equipment(code='EQ-0003', name='บันไดอลูมิเนียม 5 ขั้น', type='Mobile', status='Available', description='บันไดพับได้'),
        Equipment(code='EQ-0004', name='เครื่องวัดไฟมัลติมิเตอร์ Fluke', type='Mobile', status='Available', description='เครื่องวัดดิจิตอล'),
        Equipment(code='EQ-0005', name='เครื่องเซิร์ฟเวอร์สำรอง', type='Stationary', status='Available', description='เครื่องทดสอบระบบภายในห้อง Server'),
        Equipment(code='EQ-0006', name='พัดลมตั้งพื้น Hatari', type='Stationary', status='Broken', description='ส่ายไม่ได้ มอเตอร์มีเสียงดัง'),
    ]
    db.session.add_all(equipments)
    db.session.commit()
    
    # === ประวัติการยืมตัวอย่าง ===
    eq_tx = [
        EquipmentTransaction(equipment_id=2, transaction_type='Borrow', borrower_name='สมชาย ใจดี', purpose='เป่าท่อสายแลน', evidence_image='default_borrow.jpg', created_by=2)
    ]
    db.session.add_all(eq_tx)
    db.session.commit()