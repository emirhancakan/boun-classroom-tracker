CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_code TEXT,        -- Örn: CE241.01
    semester TEXT,           -- Örn: 2025/2026-1
    course_name TEXT,        -- Örn: Statics
    instructor TEXT,         -- Örn: STAFF
    UNIQUE(course_code, semester)
);

-- 2. Tablo: Ders saatleri ve mekanları (Bir dersin birden fazla satırı olabilir)
CREATE TABLE IF NOT EXISTS schedule_slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER,       -- 'courses' tablosundaki id'ye bağlanır
    day TEXT,                -- Monday, Tuesday vb.
    time_slot TEXT,          -- 09:00-11:00 or raw "345"
    room TEXT,               -- M2180, VYKM vb.
    building_name TEXT,      -- Mühendislik Binası, New Hall vb.
    FOREIGN KEY (course_id) REFERENCES courses(id)
);
