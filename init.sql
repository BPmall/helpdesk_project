-- สร้างตารางผู้ใช้งาน
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    role ENUM('Admin', 'Employee', 'Manager', 'Vendor', 'Customer') NOT NULL,
    department VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- สร้างตารางใบแจ้งซ่อม (Tickets)
CREATE TABLE tickets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    status ENUM('Pending', 'Head_Approved', 'Manager_Approved', 'Resolved', 'Rejected') DEFAULT 'Pending',
    priority ENUM('Low', 'Medium', 'High', 'Critical') DEFAULT 'Low',
    requester_id INT,
    assignee_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (requester_id) REFERENCES users(id),
    FOREIGN KEY (assignee_id) REFERENCES users(id)
);

-- สร้างตารางเก็บประวัติการอนุมัติ (Audit Log / Workflow)
CREATE TABLE ticket_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ticket_id INT,
    actor_id INT,
    action VARCHAR(255) NOT NULL, -- เช่น "Manager Approved"
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id),
    FOREIGN KEY (actor_id) REFERENCES users(id)
);