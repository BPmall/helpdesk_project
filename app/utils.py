from datetime import datetime
import requests
import qrcode
import io
import base64
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def to_buddhist_era(date_obj):
    """แปลง ปี ค.ศ. เป็น พ.ศ."""
    if not date_obj:
        return ""
    be_year = date_obj.year + 543
    return date_obj.strftime(f"%d/%m/{be_year} %H:%M")


# ====================================================
# QR Code Generation
# ====================================================

def generate_qr_base64(data_string, size=6):
    """สร้าง QR Code แล้วคืนค่าเป็น base64 string สำหรับแสดงบน HTML"""
    qr = qrcode.QRCode(version=1, box_size=size, border=2)
    qr.add_data(data_string)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return base64.b64encode(buffer.getvalue()).decode('utf-8')


# ====================================================
# Notification Functions
# ====================================================

def send_line_message(access_token, user_id, message):
    """ส่งแจ้งเตือนผ่าน LINE Messaging API"""
    if not access_token or not user_id:
        return False
    try:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}'
        }
        payload = {
            "to": user_id,
            "messages": [{"type": "text", "text": message}]
        }
        resp = requests.post('https://api.line.me/v2/bot/message/push',
                             headers=headers, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"[LINE Error] {e}")
        return False


def send_email(smtp_host, smtp_port, smtp_user, smtp_pass, to_email, subject, body):
    """ส่งแจ้งเตือนผ่าน Email (SMTP)"""
    if not all([smtp_host, smtp_user, smtp_pass, to_email]):
        return False
    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html', 'utf-8'))

        with smtplib.SMTP(smtp_host, int(smtp_port or 587)) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[Email Error] {e}")
        return False


def send_telegram_message(bot_token, chat_id, message):
    """ส่งแจ้งเตือนผ่าน Telegram Bot"""
    if not bot_token or not chat_id:
        return False
    try:
        url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
        payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'}
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"[Telegram Error] {e}")
        return False




def send_custom_notification(message, config, email_subject='[Helpdesk] แจ้งเตือนระบบ'):
    """ส่งแจ้งเตือนข้อความทั่วไปทุกช่องทางที่เปิดใช้งาน"""
    results = {}

    if config.get('line_enabled') == '1' and config.get('line_token'):
        target_id = (config.get('line_default_group') or '').strip()
        if target_id:
            results['line'] = send_line_message(config['line_token'], target_id, message)

    if config.get('email_enabled') == '1' and config.get('smtp_host'):
        target_email = (config.get('email_default_to') or '').strip()
        if target_email:
            html_body = f"""<div style="font-family: 'Prompt', sans-serif; padding: 20px; white-space: pre-line;">{message}</div>"""
            results['email'] = send_email(
                config['smtp_host'], config.get('smtp_port', '587'),
                config.get('smtp_user', ''), config.get('smtp_pass', ''),
                target_email, email_subject, html_body
            )

    if config.get('telegram_enabled') == '1' and config.get('telegram_token'):
        chat_id = (config.get('telegram_chat_id') or '').strip()
        if chat_id:
            results['telegram'] = send_telegram_message(config['telegram_token'], chat_id, message)

    return results
def send_notification(ticket, action_text, config):
    """ส่งการแจ้งเตือนทุกช่องทางที่เปิดใช้งาน"""
    message = (
        f"🔔 แจ้งเตือน Helpdesk\n"
        f"📋 {ticket.ticket_number}: {ticket.title}\n"
        f"📌 {action_text}\n"
        f"⏰ {to_buddhist_era(datetime.utcnow())}"
    )

    results = {}

    # LINE
    if config.get('line_enabled') and config.get('line_token'):
        target_id = config.get('line_default_group') or ''
        if target_id:
            results['line'] = send_line_message(config['line_token'], target_id, message)

    # Email
    if config.get('email_enabled') and config.get('smtp_host'):
        target_email = config.get('email_default_to') or ''
        if target_email:
            subject = f"[Helpdesk] {ticket.ticket_number} - {action_text}"
            html_body = f"""
            <div style="font-family: 'Prompt', sans-serif; padding: 20px;">
                <h2 style="color: #B91C1C;">🔔 แจ้งเตือน Helpdesk</h2>
                <p><strong>Ticket:</strong> {ticket.ticket_number}</p>
                <p><strong>หัวข้อ:</strong> {ticket.title}</p>
                <p><strong>การดำเนินการ:</strong> {action_text}</p>
                <p><strong>เวลา:</strong> {to_buddhist_era(datetime.utcnow())}</p>
            </div>
            """
            results['email'] = send_email(
                config['smtp_host'], config.get('smtp_port', '587'),
                config['smtp_user'], config['smtp_pass'],
                target_email, subject, html_body
            )

    # Telegram
    if config.get('telegram_enabled') and config.get('telegram_token'):
        chat_id = config.get('telegram_chat_id') or ''
        if chat_id:
            tg_msg = (
                f"🔔 <b>แจ้งเตือน Helpdesk</b>\n"
                f"📋 {ticket.ticket_number}: {ticket.title}\n"
                f"📌 {action_text}\n"
                f"⏰ {to_buddhist_era(datetime.utcnow())}"
            )
            results['telegram'] = send_telegram_message(config['telegram_token'], chat_id, tg_msg)

    return results


# ====================================================
# Approval Workflow Logic
# ====================================================

# กำหนดว่าแต่ละ role สามารถเปลี่ยนสถานะอะไรได้บ้าง
WORKFLOW_RULES = {
    'Admin': {
        'Pending': ['Head_Approved', 'Manager_Approved', 'In_Progress', 'Rejected'],
        'Head_Approved': ['Manager_Approved', 'In_Progress', 'Rejected'],
        'Manager_Approved': ['In_Progress', 'Rejected'],
        'In_Progress': ['Resolved', 'Pending'],
        'Resolved': ['Closed', 'In_Progress'],
        'Rejected': ['Pending'],
        'Closed': [],
    },
    'Manager': {
        'Pending': ['Head_Approved', 'Rejected'],
        'Head_Approved': ['Manager_Approved', 'Rejected'],
        'Manager_Approved': ['In_Progress'],
        'In_Progress': ['Resolved'],
        'Resolved': ['Closed'],
        'Rejected': [],
        'Closed': [],
    },
    'Employee': {
        'Pending': [],
        'In_Progress': [],
        'Resolved': ['Closed'],
        'Rejected': [],
        'Closed': [],
    },
    'Vendor': {
        'In_Progress': ['Resolved'],
    },
    'Customer': {},
}


def get_allowed_statuses(current_status, user_role):
    """คืนค่ารายการสถานะที่ผู้ใช้สามารถเปลี่ยนไปได้"""
    role_rules = WORKFLOW_RULES.get(user_role, {})
    return role_rules.get(current_status, [])


STATUS_LABELS = {
    'Pending': 'รอดำเนินการ',
    'Head_Approved': 'หัวหน้าอนุมัติแล้ว',
    'Manager_Approved': 'ผู้จัดการอนุมัติแล้ว',
    'In_Progress': 'กำลังดำเนินการ',
    'Resolved': 'เสร็จสิ้น',
    'Rejected': 'ปฏิเสธ',
    'Closed': 'ปิดงาน',
}
