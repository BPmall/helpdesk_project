# FIBER RANGER MA-PM — วิเคราะห์และออกแบบระบบเพื่อใช้งานจริง

> ขอบเขต: แอปช่างภาคสนาม (มือถือ) + เชื่อม SAPKAT CRM + ข้อเสนอสำหรับ KAT CCTV CMS
> สถานะ: **Phase 1 implement แล้วใน repo นี้** (`/field`) — ส่วน CRM / CCTV เป็นข้อกำหนดให้ฝั่งระบบนั้นทำต่อ

---

## 1. ภาพรวมระบบจากหน้าจอที่ได้รับ

| # | หน้าจอ | บทบาท | เทคโนโลยีที่เห็น |
|---|--------|-------|------------------|
| 1 | Mockup แอปช่าง (FIBER RANGER MA-PM) | เป้าหมาย UX: รับงาน → เดินทาง → ถึงหน้างาน, กดพูด, ลงเวลา, กล้อง, แชททีม | ดีไซน์ |
| 2 | แอปช่างตัวจริง (22:32 น.) | เวอร์ชันที่ใช้อยู่ | WebView ห่อหน้า CRM + หน้าเว็บ WoTeam |
| 3 | KAT CCTV CMS V1 Live View | ดูกล้อง 25 ช่อง ไซต์ "บ้านช่างตู่" | เว็บ local `127.0.0.1:8766` |
| 4 | SAPKAT PILOT CRM Dashboard | ศูนย์ติดตามงานซ่อม KAT SERVICE + MA Fiber | PHP (`index.php?page=dashboard`) |

---

## 2. วิเคราะห์ปัญหา (Gap Analysis)

### 2.1 แอปช่าง: Mockup (ภาพ 1) เทียบกับของจริง (ภาพ 2)

| อาการในภาพ 2 | สาเหตุ | ผลต่อการใช้งานจริง |
|---|---|---|
| "ยังไม่ได้เลือกใบงาน / เชื่อมต่อ CRM แล้วเลือกงานของคุณ" | แอปไม่มีข้อมูลงานเป็นของตัวเอง ต้องให้ช่างไปเลือกงานในหน้า CRM เอง | ช่างไม่รู้ว่ามีงานอะไร ต้องกดหลายชั้น |
| "ยังไม่มีข้อความที่อ่านได้จาก WoTeam" + "WoTeam รุ่นนี้ต้องเปิดหน้าเว็บ" | พยายามอ่านแชทจากหน้าเว็บของบุคคลที่สามซึ่ง**ไม่มี API** (ติด cookie/CORS/X-Frame-Options) | แชทกับวอใช้ไม่ได้จริง **นี่คือจุดที่ระบบพังหลัก** |
| Toast "กำลังเชื่อมหน้า WoTeam…" **ทับปุ่มกดพูด** | toast อยู่ล่างจอทับ action หลัก | กดพูดไม่ได้ในช่วงที่สำคัญที่สุด |
| Badge งานค้างเป็น "–" | ไม่มีตัวเลขจริงจาก backend | ข้อมูลไม่น่าเชื่อถือ |
| ช่องพิมพ์มีข้อความ "Jdirjf" แต่ไม่มีที่ส่ง | composer ไม่ผูกกับ backend | ข้อความหาย |
| ปุ่ม "รับงาน" กดได้ทั้งที่ไม่มีงาน | ไม่มี state machine | ข้อมูลเวลาไม่ถูกต้อง |
| เริ่มเดินทาง / ถึงหน้างาน ไม่มีพิกัด | ไม่เก็บ GPS / ไม่ตรวจระยะ | ตรวจสอบย้อนหลังไม่ได้ว่าไปถึงจริง |

**ข้อสรุป:** ปัญหาไม่ได้อยู่ที่หน้าตา แต่อยู่ที่**ไม่มี backend ของแอปช่างเอง** และพึ่งพาหน้าเว็บของระบบอื่น (CRM, WoTeam) ผ่าน WebView ซึ่งควบคุมไม่ได้

### 2.2 SAPKAT CRM (ภาพ 4) ที่พบ

1. **ปฏิทินวันในสัปดาห์เลื่อนไป 1 คอลัมน์** — พ.ย. 2569 วันที่ 1 คือ**วันอาทิตย์** แต่ปฏิทินแสดงใต้ "ส" และวันที่ 24 (วันนี้) คือ**วันอังคาร** แต่แสดงใต้ "จ" (หน้า CCTV แสดง "วันอังคารที่ 24" ถูกต้อง) → นัดหมายที่ช่างดูจากปฏิทินจะผิดวัน ต้องแก้ใน CRM (น่าจะใช้ `date('N')` (จันทร์=1) กับหัวตารางที่เริ่มอาทิตย์ หรือ `date('w')` สลับกัน)
2. ใช้ปีปนกัน: หัว dashboard "24/11/2026" (ค.ศ.) แต่ปฏิทิน "2569" (พ.ศ.) → ควรเลือกแบบเดียวทั้งระบบ
3. การ์ด "ส่งงานแล้ว/รอตรวจ 0" ทั้งที่ "ความเคลื่อนไหวล่าสุด" มี JOB-2611-00066 ปิดงานแล้ว → สถานะ "ส่งงาน" กับ "ปิดงาน" ไม่ได้แยกขั้นจริง หรือไม่มีขั้นตรวจรับ
4. ตัวเลขสอดคล้องกัน: ยังไม่ปิด 9 = KAT 6 + MA 3 ✓ (เป็นจุดอ้างอิงที่ดีสำหรับ reconciliation)

### 2.3 KAT CCTV CMS (ภาพ 3) ที่พบ

1. หัวบอก "ออนไลน์ 16 · ออฟไลน์ 9" แต่แถบซ้ายแสดง "ออนไลน์" ทุกช่อง → สถานะ 2 ที่ไม่ตรงกัน
2. CH15, CH17–CH24 "ยังไม่ได้เฟรมภาพ" — ไม่แยก "ช่องไม่ได้ต่อกล้อง" ออกจาก "กล้องเสีย" → แจ้งเตือนผิด
3. เปิด 25 ช่องพร้อมกันด้วย main stream → กินแบนด์วิดท์/CPU ของ NVR
4. รันที่ `127.0.0.1` → ดูได้เฉพาะเครื่องนั้น ช่าง/ลูกค้าดูจากมือถือไม่ได้

---

## 3. สถาปัตยกรรมเป้าหมาย

```
                ┌───────────────────────────┐
                │ SAPKAT CRM (PHP)          │  เจ้าของข้อมูลลูกค้า / Job Order / SLA
                │ pilot.pm.sapkat.com       │
                └──────┬──────────▲─────────┘
     POST /field/api/crm/jobs     │  POST crm_callback_url
     (X-API-Key, upsert ใบงาน)    │  (accept/depart/arrive/finish + GPS)
                ┌──────▼──────────┴─────────┐
                │ Field Service (Flask)     │  repo นี้
                │  • tickets / approval     │  ← ออฟฟิศ: มอบหมาย + ตั้งข้อมูลหน้างาน
                │  • field_jobs  (state)    │
                │  • field_events (หลักฐาน) │  GPS, เวลา, รูป, ลงเวลา
                │  • team_messages          │  แชท + เสียงวอ
                │  • แจ้ง LINE/Telegram/Email│
                └──────▲────────────────────┘
                       │ HTTPS (JSON, session+CSRF)
                ┌──────┴────────────────────┐
                │ แอปช่าง /field (PWA)      │  มือถือ Android/iOS ไม่ต้องลงแอป
                └───────────────────────────┘

   CCTV: NVR ──RTSP──► go2rtc / MediaMTX ──WebRTC/HLS──► CMS (+ ลิงก์จากใบงานตามไซต์)
```

**หลักการ**
- CRM = แหล่งความจริงของ "งานอะไร ของใคร ที่ไหน" / Field Service = แหล่งความจริงของ "ช่างทำอะไร เมื่อไหร่ ที่ไหน"
- เชื่อมกันด้วย **API แบบ server-to-server** เท่านั้น ห้ามใช้ WebView ขูดหน้าเว็บ
- แอปช่างเป็น **PWA**: เปิดผ่าน Chrome/Safari แล้ว "เพิ่มลงหน้าจอหลัก" ได้ทันที ไม่ต้องผ่าน Store

---

## 4. Flow การทำงานของช่าง (State Machine)

```
 ออฟฟิศมอบหมาย / CRM ส่งใบงาน
            │
       [Assigned] ──accept──► [Accepted] ──depart──► [Traveling] ──arrive──► [OnSite] ──finish──► [Done]
                                   └──────────── arrive (ไม่กดเดินทางก็ได้) ─────┘
```

| Action | เงื่อนไขที่ระบบบังคับ | ผลกับ Ticket เดิม |
|---|---|---|
| accept | ต้องเป็นงานที่มอบหมายให้ตัวเอง | → `In_Progress` |
| depart | สถานะ Accepted | log |
| arrive | **ต้องมี GPS**; ถ้าห่างจากพิกัดหน้างานเกินรัศมี (ค่าเริ่มต้น 300 ม. + ความคลาดเคลื่อน GPS ไม่เกิน 200 ม.) **ต้องใส่เหตุผล**; ถ้ายังไม่มีพิกัดหน้างาน ระบบจำพิกัดครั้งแรกไว้ใช้ครั้งต่อไป | log + ระยะห่าง |
| finish | **ต้องมีรูปหน้างานอย่างน้อย 1 รูป** + กดยืนยัน | → `Resolved` + `resolved_at` |

ทุก action: บันทึก `field_events` (append-only), เขียน `ticket_logs`, โพสต์ข้อความระบบในแชททีม, แจ้ง LINE/Telegram/Email ตามที่เปิดในหน้าตั้งค่า, callback กลับ CRM (ถ้าตั้ง `crm_callback_url`)

**ลงเวลา**: ต้องมี GPS, กดสลับเข้า/ออกอัตโนมัติ, นับวันตามเวลาไทย

---

## 5. การสื่อสาร: แทน WoTeam ด้วยอะไร

| ทางเลือก | ข้อดี | ข้อเสีย | ใช้เมื่อ |
|---|---|---|---|
| A. ฝัง/ขูดหน้าเว็บ WoTeam (แบบเดิม) | ไม่ต้องทำอะไร | **ใช้ไม่ได้จริง** (ภาพ 2), ไม่มีประวัติ ไม่ผูกกับใบงาน | ไม่แนะนำ |
| **B. ข้อความเสียงแบบกดค้าง–ปล่อยส่ง (ทำแล้ว)** | ทำงานได้บนเน็ต 4G อ่อน, มีประวัติย้อนฟัง, เป็นหลักฐาน, เครื่องอื่นเล่นอัตโนมัติเหมือนวอ, ไม่มีค่าบริการ | หน่วง 1–3 วินาที (ไม่ใช่ full-duplex) | **Phase 1 — แนะนำ** |
| C. Real-time PTT (WebRTC ผ่าน LiveKit self-host หรือ Zello Work) | หน่วงต่ำ < 300 ms | ต้องมี server/ค่าบริการ, ซับซ้อน, ต้องรักษา connection บนมือถือ | ถ้าทีมใช้ PTT ต่อเนื่องเป็นหลัก |
| D. ใช้ WoTeam ต่อ แต่ผ่าน **API ทางการ** | ไม่เปลี่ยนพฤติกรรมทีม | ต้องให้ผู้ให้บริการเปิด API | ถ้า WoTeam มี API |

UX ที่ทำในแอป: กดค้างปุ่ม "กดพูด" → สั่น + วงแดง → ปล่อยเพื่อส่ง (ยาวสุด 60 วิ, สั้นกว่า 0.6 วิ ไม่ส่ง) → เครื่องอื่นเล่นอัตโนมัติทีละคลิป (ปิดได้ที่ปุ่มลำโพงซ้าย)

---

## 6. ข้อมูล (Data Model ที่เพิ่ม)

ไม่แก้ตารางเดิม → `db.create_all()` สร้างตารางใหม่ให้อัตโนมัติ ไม่ต้อง migrate

**`field_jobs`** (1:1 กับ `tickets`)
`ticket_id` (unique), `external_ref` (เลขใบงาน CRM, unique), `job_type` (KAT / MA_FIBER), `site_name`, `address`, `lat`, `lng`, `geofence_m`, `coordinator_name`, `coordinator_phone`, `appointment_at`, `field_status`, `accepted_at`, `depart_at`, `arrive_at`, `finished_at`

**`field_events`** (append-only, เป็นหลักฐาน/timesheet)
`user_id`, `job_id`, `event_type` (accept/depart/arrive/finish/clock_in/clock_out/photo), `lat`, `lng`, `accuracy_m`, `distance_m`, `photo`, `note`, `client_uuid` (unique, กันส่งซ้ำ), `client_time` (เวลาที่กดจริงตอน offline), `created_at`

**`team_messages`**
`channel` (team / job:<id>), `user_id`, `kind` (text/voice/image/system), `body`, `file`, `duration_s`, `client_uuid`, `created_at`

**Role ใหม่** `Technician` — login แล้วเข้า `/field` ทันที, ถูกมอบหมายงานได้, เปลี่ยน In_Progress → Resolved ได้

---

## 7. API

ฝั่งแอป (session cookie + header `X-CSRFToken`)

| Method | Path | หน้าที่ |
|---|---|---|
| GET | `/field/api/state[?job=<id>]` | user, งานที่กำลังทำ, รายการงานค้าง, สถานะลงเวลา |
| POST | `/field/api/jobs/<id>/{accept,depart,arrive,finish}` | `{lat,lng,accuracy,note,client_uuid,client_time}` |
| POST | `/field/api/clock` | `{lat,lng,accuracy,client_uuid}` |
| POST | `/field/api/photo` | multipart `photo`, `job_id`, `lat`, `lng` (≤10 MB, jpg/png/webp/heic) |
| GET | `/field/api/messages?after=<id>` | polling ทุก 4 วิ |
| POST | `/field/api/messages` | `{body}` ≤ 1000 ตัวอักษร |
| POST | `/field/api/voice` | multipart `audio`, `duration` (≤ 60 วิ, ≤ 3 MB) |
| GET | `/field/media/<file>` | รูป/เสียง (**ต้องล็อกอิน**) |

รหัสผิดพลาดที่แอปจัดการ: `403` ไม่ใช่งานของคุณ, `409` ผิดลำดับ / `outside_geofence`, `422` `gps_required` / `photo_required`

ฝั่ง CRM → ระบบนี้

```http
POST /field/api/crm/jobs
X-API-Key: <FIELD_CRM_API_KEY>
Content-Type: application/json

{
  "external_ref": "JOB-2611-00052",
  "title": "ไฟเบอร์ขาด ชั้น 3",
  "job_type": "MA_FIBER",
  "site_name": "บริษัท ซินโฟนี่ คอมมูนิเคชั่น",
  "address": "อ.เมือง จ.นนทบุรี",
  "lat": 13.8621, "lng": 100.5144,
  "coordinator_name": "คุณเอ", "coordinator_phone": "0812345678",
  "appointment_at": "2026-11-28T09:30:00",   // ไม่มี timezone = เวลาไทย
  "priority": "High",
  "assignee_username": "tu",
  "cancelled": false
}
```
upsert ตาม `external_ref` (ส่งซ้ำได้), ตอบ `201` สร้างใหม่ / `200` อัปเดต

ระบบนี้ → CRM: ตั้ง `crm_callback_url` ในตาราง `system_config` แล้วระบบจะ POST
`{external_ref, action, field_status, at, lat, lng, technician}` พร้อม header `X-API-Key` ทุกครั้งที่ช่างกด

---

## 8. การใช้งานในพื้นที่จริง (สัญญาณไม่ดี)

- **คิว offline**: กดรับงาน/ถึงหน้างาน/ลงเวลา/ส่งข้อความตอนไม่มีเน็ต → เก็บในเครื่องพร้อมเวลาที่กดจริง แล้วส่งอัตโนมัติเมื่อกลับมาออนไลน์ (server ใช้ `client_uuid` กันบันทึกซ้ำ, รับ `client_time` ย้อนหลังได้ไม่เกิน 48 ชม.)
- ชิปสถานะ "พร้อมเชื่อมต่อ / รอส่ง n รายการ / ออฟไลน์" แสดงจริงจากผลเรียก API ไม่ใช่ตกแต่ง
- ย่อรูปในเครื่องเหลือด้านยาว 1600 px ก่อนส่ง (ราว 200–400 KB แทน 3–5 MB)
- เสียงอัดที่ 32 kbps (≈ 240 KB/นาที)
- Toast อยู่บนสุดของจอ ไม่ทับปุ่มกดพูด

---

## 9. ความพร้อมขึ้นระบบจริง (Production Checklist)

**ระบบจัดการให้อัตโนมัติแล้วเมื่อเป็น production** (`APP_ENV=production` หรือรันบน Railway)
- [x] บังคับ HTTPS (redirect 301 ตาม `X-Forwarded-Proto`, ยกเว้น `/health`) + HSTS + cookie `Secure` + `ProxyFix`
- [x] ไม่ใช้ `SECRET_KEY` ที่อยู่ใน code — ถ้าไม่ตั้ง จะสุ่มให้และเขียน ERROR ลง log
- [x] ฐานข้อมูลใหม่ไม่ใช้รหัส `1234` — ใช้ `INITIAL_ADMIN_PASSWORD` หรือสุ่มแล้วพิมพ์ลง log ครั้งเดียว
- [x] ไฟล์อัปโหลดทั้งหมดเปิดผ่าน `/uploads/<file>` ที่ต้องล็อกอิน (ยกเว้นรูปอุปกรณ์สำหรับหน้า QR สาธารณะ) และย้ายที่เก็บได้ด้วย `UPLOAD_FOLDER` (ไฟล์เก่าใน `static/uploads` ยังเปิดได้)

**ต้องตั้งค่าบน Railway ก่อน merge/deploy**
- [ ] `SECRET_KEY` = ค่าสุ่มยาว ≥ 32 ตัว (`python -c "import secrets;print(secrets.token_hex(32))"`)
- [ ] เพิ่ม **Volume** mount ที่ `/data` แล้วตั้ง `UPLOAD_FOLDER=/data/uploads` — ไม่งั้นรูปหลักฐาน/เสียงหายทุก deploy
- [ ] เพิ่ม PostgreSQL plugin (`DATABASE_URL` ถูกตั้งให้อัตโนมัติ) — SQLite บน Railway หายทุก deploy เช่นกัน
- [ ] `FIELD_CRM_API_KEY` เมื่อพร้อมเชื่อม CRM และตั้ง `crm_callback_url` ในตาราง `system_config`
- [ ] เปลี่ยนรหัสผ่านบัญชีตัวอย่างเดิม (ฐานข้อมูลที่ seed ไปแล้วยังเป็น `1234`)
- [ ] Backup ฐานข้อมูลรายวัน

**PDPA** — พิกัดและเวลาของพนักงานเป็นข้อมูลส่วนบุคคล
- เก็บ GPS **เฉพาะตอนกดปุ่ม** (ไม่ track ตลอด) ✓ ออกแบบไว้แล้ว
- แจ้งวัตถุประสงค์ในประกาศความเป็นส่วนตัวพนักงาน และกำหนดระยะเวลาเก็บ (เช่น 1 ปี)

**ปัญหาความปลอดภัยใน code เดิมที่ยังไม่ได้แก้ (แนะนำแก้ต่อ)**
- `api_bp` (`/api/v1`) ปิด CSRF แต่ใช้ session cookie → เสี่ยง CSRF ควรเปลี่ยนเป็น token auth
- `generate_ticket_number()` ใช้ `last.id + 1` → ชนกันได้เมื่อสร้างพร้อมกัน
- `psycopg2-binary==2.9.9` ไม่มี wheel สำหรับ Python 3.13 (production ใช้ 3.12 ตาม `runtime.txt` จึงยังไม่กระทบ)
- ไม่มีระบบ migration (`Flask-Migrate`) — ทุกการเพิ่มคอลัมน์ต้องเขียนสคริปต์เอง

**ที่แก้แล้วใน commit นี้**
- หน้า "สร้างใบแจ้งซ่อม" **ส่งฟอร์มไม่ได้เลย** — dropdown สาขาเป็น required แต่ route ไม่ส่ง `branch_options` ไปหน้าเว็บ (ว่างตลอด) และโค้ดตรวจสาขาหายไป → แก้แล้ว + มีค่าเริ่มต้นเมื่อยังไม่ตั้งค่า
- Login มี open redirect ผ่าน `?next=` → รับเฉพาะ path ภายใน
- ผู้ใช้ที่ถูกปิด (`is_active_user=False`) ยัง login ได้ → ปิดแล้ว
- ใครก็ POST มอบหมายงานได้ → จำกัด Admin/Manager
- รายชื่อผู้รับมอบหมายมีแค่ Admin/Manager (มอบงานให้ช่างไม่ได้) → เพิ่ม Technician/Vendor
- ไฟล์แนบ Ticket / หลักฐานยืม-คืน เปิดได้โดยไม่ต้องล็อกอิน → ต้องล็อกอินแล้ว
- gunicorn 1 sync worker → `gthread` 2×8 + `preload_app` (อัปโหลดช้าไม่บล็อกทั้งระบบ)

---

## 10. แผนดำเนินงาน

| Phase | งาน | เกณฑ์ผ่าน |
|---|---|---|
| **1 (เสร็จใน repo)** | แอปช่าง `/field`, state machine + GPS + geofence, ลงเวลา, รูป, แชท + เสียงวอ, หน้า dispatch, webhook CRM, production hardening, tests 15 ชุด | ช่าง 3 คนใช้ 1 สัปดาห์: ทุกงานมีเวลา รับ/ถึง/ปิด + พิกัด + รูป ครบ ≥ 95% |
| 2 | ฝั่ง CRM: เรียก `POST /field/api/crm/jobs` ตอนมอบหมาย + รับ callback ไปอัปเดต Job Order + แก้ปฏิทินเลื่อนวัน | Job Order ที่ยังไม่ปิดตรงกันทั้ง 2 ระบบทุกวัน |
| 3 | ย้ายไฟล์ไป S3/R2, Postgres, Web Push แจ้งงานใหม่, ห้องแชทแยกต่อใบงาน (`job:<id>`) | ไม่มีไฟล์หายหลัง deploy |
| 4 | CCTV: go2rtc/MediaMTX (RTSP → WebRTC), grid ใช้ sub-stream, แยก "ไม่ได้ใช้ช่อง" กับ "ออฟไลน์", health check แจ้งเตือน, ผูกกล้องกับไซต์เพื่อเปิดจากใบงาน | สถานะหัว/แถบซ้ายตรงกัน, ดูผ่านมือถือได้ |
| 5 (ถ้าต้องการ) | Real-time PTT (LiveKit) | หน่วง < 300 ms |

---

## 11. วิธีใช้งาน / ทดสอบ

```bash
pip install -r requirements.txt pytest
python -m pytest            # 15 tests
python run.py               # http://127.0.0.1:5000
```

1. Login `admin / 1234` → เมนู "จัดการผู้ใช้" → เปลี่ยน role ช่างเป็น **Technician**
2. เปิด Ticket → กล่อง "มอบหมายงาน" เลือกช่าง → กล่อง "งานภาคสนาม" ใส่ชื่อไซต์ / พิกัด (คัดลอกจาก Google Maps) / ผู้ประสานงาน
3. ช่าง login บนมือถือ (ต้องเป็น **https**) → เข้า `/field` อัตโนมัติ → "เพิ่มลงหน้าจอหลัก"
4. ทดสอบ CRM webhook:
   ```bash
   export FIELD_CRM_API_KEY=change-me
   curl -X POST https://<host>/field/api/crm/jobs -H "X-API-Key: change-me" \
        -H "Content-Type: application/json" \
        -d '{"external_ref":"JOB-TEST-1","title":"ทดสอบ","assignee_username":"tu"}'
   ```
