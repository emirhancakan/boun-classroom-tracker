import requests
from bs4 import BeautifulSoup
import sqlite3
import re
import time
from building_mapper import get_building_name
from building_mapper import get_building_name
import sys
import urllib.parse

# Constants
BASE_URL = "https://registration.boun.edu.tr"
SCHEDULE_URL = "https://registration.boun.edu.tr/BUIS/General/schedule.aspx?p=semester"
SCH_SCRIPT_URL = "https://registration.boun.edu.tr/scripts/sch.asp"
DB_NAME = "buis_schedule.db"
SCHEMA_FILE = "schema.sql"

def init_db():
    print(f"Initializing database: {DB_NAME}")
    conn = sqlite3.connect(DB_NAME)
    try:
        with open(SCHEMA_FILE, 'r') as f:
            conn.executescript(f.read())
        conn.commit()
    except Exception as e:
        print(f"Error initializing DB (scheme file might be missing?): {e}")
        sys.exit(1)
    return conn

def get_semesters(session):
    print("Fetching semesters...")
    try:
        response = session.get(SCHEDULE_URL)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        semester_ddl = soup.find('select', {'id': 'ctl00_cphMainContent_ddlSemester'})
        if not semester_ddl:
            print("Error: Could not find semester dropdown.")
            return []
            
        semesters = []
        for option in semester_ddl.find_all('option'):
            if option['value']:
                semesters.append({
                    'name': option.text.strip(),
                    'slug': option['value']
                })
        return semesters
    except Exception as e:
        print(f"Error fetching semesters: {e}")
        return []

def get_departments(session, semester_slug):
    print(f"Fetching departments for semester: {semester_slug}...")
    
    # We need to simulate the form submission to get the list of departments
    try:
        # 1. Get initial page for ViewState
        r = session.get(SCHEDULE_URL)
        soup = BeautifulSoup(r.content, 'html.parser')
        
        viewstate = soup.find(id="__VIEWSTATE")['value']
        viewstate_gen = soup.find(id="__VIEWSTATEGENERATOR")['value'] if soup.find(id="__VIEWSTATEGENERATOR") else ""
        event_validation = soup.find(id="__EVENTVALIDATION")['value']
        
        data = {
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': viewstate,
            '__VIEWSTATEGENERATOR': viewstate_gen,
            '__EVENTVALIDATION': event_validation,
            'ctl00$cphMainContent$ddlSemester': semester_slug,
            'ctl00$cphMainContent$btnSearch': 'Go'
        }
        
        r_post = session.post(SCHEDULE_URL, data=data)
        soup_post = BeautifulSoup(r_post.content, 'html.parser')
        
        departments = []
        # Pattern: sch.asp?donem=...&kisaadi=...&bolum=...
        for link in soup_post.find_all('a', href=True):
            href = link['href']
            if 'kisaadi=' in href:
                match = re.search(r'kisaadi=([^&]+)&bolum=([^&]+)', href)
                if match:
                    code = match.group(1)
                    name_encoded = match.group(2)
                    name = name_encoded.replace('+', ' ')
                    departments.append({
                        'code': code,
                        'name': name
                    })
        
        # Deduplicate
        unique_depts = {d['code']: d for d in departments}.values()
        return list(unique_depts)
        
    except Exception as e:
        print(f"Error getting departments: {e}")
        return []

def parse_schedule_row(row_text, col_map):
    # This helper parses the row using the dynamic column map
    data = {}
    
    # helper
    def get_col(name):
        idx = col_map.get(name)
        if idx is not None and idx < len(row_text):
            return row_text[idx]
        return ""

    # 0: Code.Sec (Assume 0 is always Code.Sec as anchor)
    data['code_sec'] = row_text[0]
    
    # 2: Name (Assume 2 is Name)
    data['name'] = row_text[2]
    
    # 3: Cr
    # fallback specific indices if map fails for basics (unlikely if table structure holds, but let's trust map for D/H/R)
    # Actually, let's trust the standard columns 0-6 usually stable, but D/H/R shift.
    # To be safe, we can map all if found.
    
    # For now, stick to fixing D/H/R which are the problem.
    # Cr/ECTS/Instr are usually 3, 4, 6.
    # Let's verify mapping for them too?
    # Header: Code.Sec, Desc., Name, Cr., Ects, Quota, Instr., Days, Hours, ...
    
    cr_text = row_text[3] # specific
    try: data['cr'] = int(float(cr_text)) if cr_text else 0
    except: data['cr'] = 0
        
    ects_text = row_text[4] # specific
    try: data['ects'] = int(float(ects_text)) if ects_text else 0
    except: data['ects'] = 0
    
    # 6: Instr
    data['instr'] = row_text[6]
    
    # Dynamic cols
    data['days'] = get_col('Days')
    data['hours'] = get_col('Hours')
    data['rooms'] = get_col('Rooms')
    
    return data

def scrape_department(session, dept, semester_slug, conn):
    # Construct URL
    # Note: 'bolum' param needs + for spaces if we construct manually, 
    # Note: 'bolum' param needs to be URL encoded properly (especially &)
    # dept['name'].replace(' ', '+') is not enough for '&'
    
    safe_name = urllib.parse.quote_plus(dept['name'])
    url = f"{SCH_SCRIPT_URL}?donem={semester_slug}&kisaadi={dept['code']}&bolum={safe_name}"
    
    
    try:
        r = session.get(url)
        # BUIS uses windows-1254 (Turkish ISO)
        r.encoding = 'windows-1254'
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Verify Semester from Page Content
        # Usually looking for a header like "2025/2026-2 Computer Engineering" or similar.
        # It's often in a <span id="lblTitle"> or just text at top.
        # Let's simple search for the text pattern YYYY/YYYY-[123]
        page_text = soup.get_text()
        found_sem_match = re.search(r'(\d{4}/\d{4}-\d)', page_text)
        
        actual_semester_name = semester_slug # Default fallback
        
        if found_sem_match:
            actual_semester_name = found_sem_match.group(1)
            if actual_semester_name != semester_slug:
                print(f"Warning: Page says {actual_semester_name}, but we requested {semester_slug}. Using page content.")
        
        cursor = conn.cursor()
        
        # Old schema logic removed.
        # We just need actual_semester_name for the 'courses' table.
        
        
        rows = soup.find_all('tr')
        
        current_course_code = None
        current_course_title = None
        current_cr = 0
        current_ects = 0
        
        # Default Map (will be updated by header)
        col_map = {'Days': 7, 'Hours': 8, 'Rooms': 9} 
        
        start_parsing = False
        processed_course_ids = set()
        
        for row in rows:
            cells = row.find_all('td')
            if not cells: continue
            
            # Clean text
            row_text = [c.get_text(strip=True) for c in cells]
            
            # Detect header
            if len(row_text) > 0 and "Code.Sec" in row_text[0]:
                start_parsing = True
                col_map = {}
                for idx, txt in enumerate(row_text):
                    if "Days" in txt: col_map['Days'] = idx
                    elif "Hours" in txt: col_map['Hours'] = idx
                    elif "Rooms" in txt: col_map['Rooms'] = idx
                continue
            
            if not start_parsing: continue
            if len(cells) < 8: continue
            
            row_data = parse_schedule_row(row_text, col_map)
            
            # Extract Code and Section
            raw_code_sec = row_data['code_sec']
            section = "01"
            course_code_only = ""
            
            if raw_code_sec:
                 if "." in raw_code_sec:
                    parts = raw_code_sec.split('.')
                    course_code_only = parts[0].strip()
                    if len(parts) > 1: section = parts[1].strip()
                 else:
                    course_code_only = raw_code_sec.strip()
            
                 current_course_code = course_code_only
                 current_course_title = row_data['name']
                 # Instructor
                 current_instr = row_data['instr']
            else:
                 # Check previous context
                 if current_course_code is None: continue
                 course_code_only = current_course_code
                 pass

            full_code = f"{course_code_only}.{section}"
            
            # 1. Insert/Get Course and UPDATE it (Upsert)
            cursor.execute("SELECT id FROM courses WHERE course_code=? AND semester=?", 
                          (full_code, actual_semester_name))
            res = cursor.fetchone()
            
            if res:
                c_id = res[0]
                # UPDATE course details (Instructor, Name might have changed)
                cursor.execute("""
                    UPDATE courses 
                    SET course_name = ?, instructor = ?
                    WHERE id = ?
                """, (current_course_title, row_data['instr'], c_id))
                
                # LAZY DELETE: Only delete slots once per run if not fresh
                if c_id not in processed_course_ids:
                    cursor.execute("DELETE FROM schedule_slots WHERE course_id = ?", (c_id,))
                    processed_course_ids.add(c_id)
            else:
                cursor.execute("""
                    INSERT INTO courses (course_code, semester, course_name, instructor)
                    VALUES (?, ?, ?, ?)
                """, (full_code, actual_semester_name, current_course_title, row_data['instr']))
                c_id = cursor.lastrowid
                processed_course_ids.add(c_id)
            
            # 2. Insert Slots (Freshly)
            if row_data['days'] or row_data['hours'] or row_data['rooms']:
                 b_name = get_building_name(row_data['rooms'])
                 cursor.execute("""
                     INSERT INTO schedule_slots (course_id, day, time_slot, room, building_name)
                     VALUES (?, ?, ?, ?, ?)
                 """, (c_id, row_data['days'], row_data['hours'], row_data['rooms'], b_name))
                 
            conn.commit()

    except Exception as e:
        print(f"Failed to scrape {dept['code']}: {e}")
        return 0, 0
    
    # Return (success_flag, count_of_courses)
    # We need to count distinct courses found.
    # Let's parse the rows and set a counter?
    # Retrofitting the counter into the loop is cleaner.
    # BUT I can't easily edit the whole function loop in one go without big replace.
    # Alternative: In main(), just query DB count before/after for that dept?
    # That's easier and robust.
    return 1, 0 # Placeholder signature change


def main():
    conn = init_db()
    session = requests.Session()
    # Add headers to mimic browser
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    
    # 1. Semesters
    semesters = get_semesters(session)
    if not semesters: return

    # Filter Semesters: Target recent years (2024+)
    # We want to find the first semester that actually has data.
    candidate_semesters = []
    for s in semesters:
        # Targeting 2025/2026-1 and 2025/2026-2 as requested
        if "2025/2026-1" in s['name'] or "2025/2026-2" in s['name']: 
             candidate_semesters.append(s)
    
    if not candidate_semesters:
        print("No matches for 2025/2026-1 or 2025/2026-2. Checking all...")
        candidate_semesters = semesters

    # Load known departments once
    KNOWN_DEPARTMENTS = []
    import json, os
    json_path = "departments_list.json"
    
    if os.path.exists(json_path):
         try:
             with open(json_path, 'r') as f:
                 KNOWN_DEPARTMENTS = json.load(f)
             print(f"Loaded {len(KNOWN_DEPARTMENTS)} departments from {json_path}")
         except Exception as e:
             print(f"Failed to load json: {e}")
    
    if not KNOWN_DEPARTMENTS:
        KNOWN_DEPARTMENTS = [
            {'code': 'CMPE', 'name': 'COMPUTER ENGINEERING'},
            {'code': 'EE', 'name': 'ELECTRICAL & ELECTRONICS ENGINEERING'},
            {'code': 'IE', 'name': 'INDUSTRIAL ENGINEERING'},
            {'code': 'MATH', 'name': 'MATHEMATICS'},
            {'code': 'PHYS', 'name': 'PHYSICS'},
            {'code': 'CE', 'name': 'CIVIL ENGINEERING'},
        ]
        print(f"Using hardcoded fallback list ({len(KNOWN_DEPARTMENTS)} depts).")

    # Scrape EACH candidate semester
    for sem in candidate_semesters:
        print(f"\n=== Processing Semester: {sem['name']} ===")
        
        # 1. Get Departments
        current_depts = get_departments(session, sem['slug'])
        
        if not current_depts:
            print(f"  Dynamic department fetch failed for {sem['name']}. Using fallback list.")
            current_depts = KNOWN_DEPARTMENTS
            
        print(f"  Targeting {len(current_depts)} departments.")
        
        # 2. Scrape All Departments
        total_courses_scraped = 0
        count = 0
        
        for d in current_depts:
            # Pre-check count
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM courses WHERE semester = ?", (sem['name'],))
            pre_c = cursor.fetchone()[0]
            
            scrape_department(session, d, sem['slug'], conn)
            
            # Post-check count
            cursor.execute("SELECT COUNT(*) FROM courses WHERE semester = ?", (sem['name'],))
            post_c = cursor.fetchone()[0]
            diff = post_c - pre_c
            total_courses_scraped += diff
            
            count += 1
            sys.stdout.write(f"\r  Scraped {count}/{len(current_depts)}: {d['code']} (+{diff} courses) Total: {total_courses_scraped}")
            sys.stdout.flush()
            
        print(f"\n  Done with {sem['name']}! Total added/found: {total_courses_scraped}")

    # Final DB Total
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM courses")
    final_total = cursor.fetchone()[0]
    print(f"\nGrand Total in Database: {final_total}")
    
    conn.close()

if __name__ == "__main__":
    main()
