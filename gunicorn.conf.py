import os

port = os.environ.get("PORT", "8000")
bind = f"0.0.0.0:{port}"
# แอปช่างภาคสนาม poll แชททุก 4 วิ + อัปโหลดรูป/เสียง → ใช้ thread worker
# ไม่ให้ request ที่อัปโหลดช้า (เน็ตมือถือ) บล็อกคนอื่นทั้งระบบ
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", "8"))
# สร้างตาราง/seed ข้อมูลครั้งเดียวใน master ก่อน fork (กัน 2 workers seed ชนกัน)
preload_app = True
timeout = 120
accesslog = "-"
loglevel = "info"
