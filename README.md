# 🏢 Corporate Helpdesk & IT Support System

ระบบแจ้งซ่อมบำรุงและ IT Helpdesk สำหรับองค์กร พัฒนาด้วย Python Flask

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-3.0-green?logo=flask)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## ✨ ฟีเจอร์หลัก

| ฟีเจอร์ | รายละเอียด |
|---------|-----------|
| 🔐 **ระบบสมาชิก** | Login / Register / Role-based access (Admin, Manager, Employee, Vendor, Customer) |
| 🎫 **CRUD Ticket** | สร้าง / ดู / ค้นหา / กรอง / แก้ไขสถานะ ใบแจ้งซ่อม |
| 🔄 **Approval Workflow** | อนุมัติหลายขั้น (หัวหน้า → ผู้จัดการ) ตามสิทธิ์ Role |
| 📊 **Dashboard** | กราฟสถิติ Chart.js (Doughnut + Bar) + ตาราง Ticket ล่าสุด |
| 📅 **Calendar** | ปฏิทินแสดง Ticket แบบ Color-coded |
| 🔔 **แจ้งเตือน** | LINE Messaging API / Email SMTP / Telegram Bot |
| 📱 **QR Code** | สร้าง QR Code อัตโนมัติทุกใบแจ้งซ่อม |
| 📋 **Audit Log** | บันทึกทุกการกระทำ (ใครทำอะไร เมื่อไหร่) |
| 👥 **จัดการผู้ใช้** | ดูรายชื่อ / เปลี่ยน Role ผู้ใช้ (Admin only) |
| 📥 **Export** | ดาวน์โหลด CSV / Excel (.xlsx) |
| 📡 **REST API** | Full CRUD API + API Documentation page |
| 💬 **Comments** | ระบบแสดงความคิดเห็นใน Ticket |
| 🌙 **Dark Mode** | สลับ Light / Dark Mode + จำค่า |
| 📱 **Responsive** | รองรับ Desktop / Tablet / Mobile |
| 🖨️ **Print** | พิมพ์ใบแจ้งซ่อมได้ |

---

## 🚀 Quick Start (Development)

### 1. ติดตั้ง
```bash
# Clone โปรเจกต์
cd helpdesk_project

# สร้าง Virtual Environment
python -m venv venv

# เปิดใช้งาน venv
# Windows:
.\venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# ติดตั้ง Dependencies
pip install -r requirements.txt
```

### 2. รันระบบ
```bash
python run.py
```

### 3. เปิดเบราว์เซอร์
```
http://127.0.0.1:5000
```

### 4. บัญชีทดสอบ
| Username | Password | Role |
|----------|----------|------|
| `admin` | `1234` | Admin |
| `somchai` | `1234` | Employee |
| `manager1` | `1234` | Manager |
| `head1` | `1234` | Manager |

---

## 🐳 Docker Deployment

```bash
# Build & Run
docker compose up -d --build

# ดู Logs
docker compose logs -f
```

---

## 📁 โครงสร้างโปรเจกต์

```
helpdesk_project/
├── run.py                    # Entry point
├── requirements.txt          # Python dependencies
├── Dockerfile               # Docker config
├── docker-compose.yml       # Docker Compose
├── README.md                # เอกสารนี้
├── USER_MANUAL.md           # คู่มือผู้ใช้งาน
│
├── app/
│   ├── __init__.py          # Flask factory + config
│   ├── models.py            # Database models (SQLAlchemy ORM)
│   ├── utils.py             # Helpers: QR, Notifications, Workflow
│   │
│   ├── routes/
│   │   ├── auth.py          # Login / Register / Logout
│   │   ├── dashboard.py     # Dashboard + Charts API + Calendar + API Docs
│   │   ├── tickets.py       # CRUD Tickets + Search + Export
│   │   ├── admin.py         # Audit Log / Users / Settings
│   │   └── api.py           # REST API v1
│   │
│   └── templates/           # Jinja2 HTML templates
│       ├── base.html        # Layout (Sidebar + Navbar + Dark Mode)
│       ├── login.html / register.html
│       ├── index.html       # Dashboard
│       ├── ticket_*.html    # Ticket pages
│       ├── audit_log.html / users.html / settings.html
│       ├── calendar.html    # Calendar view
│       └── api_docs.html    # API Documentation
│
└── instance/
    └── helpdesk.db          # SQLite database (auto-created)
```

---

## 📡 REST API

| Method | Endpoint | คำอธิบาย |
|--------|----------|---------|
| `GET` | `/api/v1/tickets` | ดึง Ticket ทั้งหมด |
| `GET` | `/api/v1/tickets/:id` | ดึงรายละเอียด Ticket |
| `POST` | `/api/v1/tickets` | สร้าง Ticket ใหม่ |
| `PUT` | `/api/v1/tickets/:id/status` | เปลี่ยนสถานะ |
| `GET` | `/api/v1/users` | ดึงรายการผู้ใช้ |
| `GET` | `/api/v1/categories` | ดึงหมวดหมู่ |
| `GET` | `/api/v1/stats` | ดึงสถิติ |
| `GET` | `/api/v1/calendar/events` | ข้อมูล Calendar |

เอกสาร API แบบเต็มดูได้ที่: `http://127.0.0.1:5000/api-docs`

---

## 🔐 Role & Permission

```
Admin     → ทำได้ทุกอย่าง, เปลี่ยน Role ผู้ใช้
Manager   → อนุมัติ/ปฏิเสธ Ticket, มอบหมายงาน
Employee  → สร้าง Ticket, ปิดงาน Ticket ตัวเอง
Vendor    → ดำเนินการแก้ไข, เสร็จสิ้น
Customer  → ดู Ticket ของตัวเอง
```

---

## 🔄 Approval Workflow

```
สร้างใหม่ (Pending)
    ↓
หัวหน้าอนุมัติ (Head_Approved)
    ↓
ผู้จัดการอนุมัติ (Manager_Approved)
    ↓
กำลังแก้ไข (In_Progress)
    ↓
เสร็จสิ้น (Resolved)
    ↓
ปิดงาน (Closed)

⛔ ปฏิเสธ (Rejected) — ส่งกลับไปสถานะ Pending ได้
```

---

## 🛠 Tech Stack

- **Backend:** Python 3.11, Flask 3.0, SQLAlchemy
- **Database:** SQLite (dev) / MySQL 8 (production)
- **Frontend:** Tailwind CSS CDN, Chart.js, Font Awesome
- **Font:** Google Fonts — Prompt (ภาษาไทย)
- **Auth:** Flask-Login (session-based)
- **QR Code:** python-qrcode + Pillow
- **Export:** openpyxl (Excel), csv (CSV)

---

## 📄 License

MIT License — ใช้งานได้อย่างอิสระ
