from flask import Flask, render_template, request, jsonify
import sqlite3
import os
import re
from query_engine import init_db

app = Flask(__name__)

# PHASE 4.6: Consolidated Building Inventory with Canonical Names
BUILDINGS = [
    {"code": "M", "name": "Mühendislik Binası - Perkins Hall", "prefixes": ["M", "VYKM"]},
    {"code": "İB", "name": "Washburn Hall - İİBF", "prefixes": ["İB", "IB"]},
    {"code": "KB", "name": "Kare Blok", "prefixes": ["KB", "MAXWELL", "MULTI"]},
    {"code": "TB", "name": "Anderson Hall - Fen-Edebiyat Fakültesi", "prefixes": ["TB"]},
    {"code": "NH", "name": "New Hall", "prefixes": ["NH"]},
    {"code": "EF", "name": "Eğitim Fakültesi", "prefixes": ["EF"]},
    {"code": "BM", "name": "Bilgisayar Müh. Binası", "prefixes": ["BM"]},
    {"code": "JF", "name": "John Freely Hall", "prefixes": ["JF"]},
    {"code": "NB", "name": "Natuk Birkan", "prefixes": ["NB"]},
    {"code": "SH", "name": "Sloane Hall", "prefixes": ["SH"]},
    {"code": "ET", "name": "ETA-B Blok", "prefixes": ["ET"]},
    {"code": "KP", "name": "Kuzey Park", "prefixes": ["KP"]},
    {"code": "HISAR", "name": "Hisar Kampüsü", "prefixes": ["HA", "HB", "HC", "HD", "HE"]},
    {"code": "GKM", "name": "Garanti Kültür Merkezi", "prefixes": ["GKM"]},
    {"code": "BME", "name": "Biyomedikal Müh. Enstitüsü", "prefixes": ["BME"]},
    {"code": "HH", "name": "Hamlin Hall", "prefixes": ["HH"]},
]


def super_normalize_room(room):
    """
    PHASE 4.7: Super-normalizer - removes ALL spaces for deep matching
    Used for comparison only, not for display
    """
    if not room:
        return ""
    return room.replace(' ', '').upper().strip()


def normalize_room_name(room):
    """
    PHASE 4.6: Robust room normalization - NEVER strip prefix
    Examples:
        M1100 -> M 1100
        VYKM3 -> VYKM 3
        M 1100 -> M 1100 (already normalized)
        1100 -> 1100 (invalid, no prefix - return as-is to be filtered later)
    """
    if not room:
        return None
    
    room = room.strip()
    
    # PHASE 4.6 FIX: Capture prefix (letters) followed by number
    # Pattern ensures we ONLY match rooms with a prefix
    pattern = r'^([A-Za-zİıĞğÜüŞşÖöÇç]+)(\d+.*)$'
    match = re.match(pattern, room)
    
    if match:
        prefix = match.group(1)
        number = match.group(2)
        normalized = f"{prefix} {number}"
        return normalized
    
    # Already has space or no number - return as is
    return room


def is_valid_room(room):
    """
    PHASE 4.6: Strict validation - room must have prefix AND number
    """
    if not room:
        return False
    
    room = room.strip()
    
    # PHASE 4.6: Must have at least one letter followed by a digit
    # This rejects: 'M', 'KB', '1100', '2200'
    # This accepts: 'M 1100', 'VYKM 3', 'NH205'
    pattern = r'^[A-Za-zİıĞğÜüŞşÖöÇç]+\s*\d+'
    if re.match(pattern, room):
        return True
    
    return False


def get_building_name_for_room(room):
    """
    PHASE 4.7: Return CANONICAL building name (exact string from BUILDINGS list)
    Also remove spaces for more flexible matching
    """
    if not room:
        return None
    
    # PHASE 4.7: Remove spaces for matching flexibility
    room_upper = room.replace(' ', '').upper().strip()
    
    # STRICT MATCHING: Check MAXWELL and MULTI first (Kare Blok only)
    if room_upper.startswith("MAXWELL") or room_upper.startswith("MULTI"):
        return "Kare Blok"
    
    # Then check all other buildings using canonical names
    for building in BUILDINGS:
        for prefix in building['prefixes']:
            prefix_no_space = prefix.replace(' ', '').upper()
            if room_upper.startswith(prefix_no_space):
                # PHASE 4.7: Return canonical name from BUILDINGS list
                return building['name']
    
    return None


@app.route('/')
def index():
    """Serve the main HTML page"""
    return render_template('index.html')


@app.route('/api/semesters', methods=['GET'])
def get_semesters():
    """Return list of available semesters from database"""
    try:
        conn = init_db()
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT semester FROM courses ORDER BY semester DESC')
        rows = cursor.fetchall()
        semesters = [row['semester'] for row in rows]
        return jsonify({'success': True, 'semesters': semesters})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/buildings', methods=['GET'])
def get_buildings():
    """Return list of buildings with canonical names"""
    return jsonify({'success': True, 'buildings': BUILDINGS})


@app.route('/api/rooms/<building_code>', methods=['GET'])
def get_rooms(building_code):
    """
    PHASE 4.6: Robust dynamic room discovery - PRESERVE PREFIXES
    """
    try:
        building = next((b for b in BUILDINGS if b['code'] == building_code), None)
        if not building:
            return jsonify({'success': False, 'error': 'Invalid building code'}), 404
        
        prefixes = building['prefixes']
        
        conn = init_db()
        cursor = conn.cursor()
        
        # Dynamic discovery - get ALL rooms from database
        cursor.execute("SELECT DISTINCT TRIM(room) as room FROM schedule_slots WHERE room IS NOT NULL AND room != ''")
        all_raw_rooms = [r['room'] for r in cursor.fetchall()]

        matching_rooms = set()
        
        for raw_room in all_raw_rooms:
            # PHASE 4.6 FIX: Split ONLY on pipe, not on spaces
            # Before: "M 1100|M 2200".replace('|', ' ').split() -> ['M', '1100', 'M', '2200'] BAD!
            # After: "M 1100|M 2200".split('|') -> ['M 1100', 'M 2200'] GOOD!
            parts = raw_room.split('|')
            
            for part in parts:
                part = part.strip()
                
                # Skip empty parts
                if not part:
                    continue
                
                # PHASE 4.6: Normalize room name (adds space if needed)
                normalized_room = normalize_room_name(part)
                if not normalized_room:
                    continue
                
                # PHASE 4.6: Validate - must have prefix AND number
                if not is_valid_room(normalized_room):
                    continue
                
                normalized_upper = normalized_room.upper()
                
                # Building-specific matching
                if building_code == 'KB':
                    # Kare Blok: KB, MAXWELL, MULTI
                    if (normalized_upper.startswith("MAXWELL") or 
                        normalized_upper.startswith("MULTI") or
                        normalized_upper.startswith("KB ")):
                        matching_rooms.add(normalized_room.upper())
                        
                elif building_code == 'M':
                    # PHASE 4.6: Mühendislik - M and VYKM (but NOT MAXWELL/MULTI)
                    if not (normalized_upper.startswith("MAXWELL") or normalized_upper.startswith("MULTI")):
                        if normalized_upper.startswith("M ") or normalized_upper.startswith("VYKM "):
                            matching_rooms.add(normalized_room.upper())
                            
                else:
                    # All other buildings: check prefixes
                    for prefix in prefixes:
                        prefix_with_space = prefix.upper() + " "
                        if normalized_upper.startswith(prefix_with_space) or normalized_upper == prefix.upper():
                            matching_rooms.add(normalized_room.upper())
                            break
        
        sorted_rooms = sorted(list(matching_rooms))
        
        return jsonify({'success': True, 'rooms': sorted_rooms})
        
    except Exception as e:
        with open("error.log", "a", encoding="utf-8") as f:
            f.write(f"ERROR in get_rooms: {str(e)}\n")
            import traceback
            f.write(traceback.format_exc())
            f.write("\n" + "="*30 + "\n")
        
        return jsonify({'success': False, 'error': str(e)}), 500


def get_formatted_room_schedule(room_name, semester):
    """
    PHASE 5.1 - STRICT DATA CONTRACT
    PRE-PROCESSOR FUNCTION: Flatten concatenated slots on backend
    Converts '12' into separate entries for slot 1 and slot 2
    Returns: [{day: 'M', time_slot: 1, course_code: 'CE214'}, ...]
    Day standardization: EXACTLY one of ['M', 'T', 'W', 'Th', 'F']
    """
    print(f"\n=== PHASE 5.1 PRE-PROCESSOR: Formatting schedule for '{room_name}' ===")
    
    # Super-normalize for matching
    super_norm_room = super_normalize_room(room_name)
    print(f"Super-normalized room for matching: '{super_norm_room}'")
    
    conn = init_db()
    cursor = conn.cursor()
    
    # Fetch all slots for this semester
    cursor.execute("""
        SELECT s.day, s.time_slot, TRIM(s.room) as room, c.course_code
        FROM schedule_slots s
        JOIN courses c ON s.course_id = c.id
        WHERE c.semester = ?
          AND s.room IS NOT NULL
    """, (semester,))
    
    rows = cursor.fetchall()
    print(f"Total DB rows fetched: {len(rows)}")
    
    # Match and flatten
    flattened_schedule = []
    raw_matches = 0
    
    # PHASE 5.1: STRICT DAY STANDARDIZATION MAP
    DAY_STANDARDIZATION = {
        'Monday': 'M', 'M': 'M', 'monday': 'M',
        'Tuesday': 'T', 'T': 'T', 'tuesday': 'T',
        'Wednesday': 'W', 'W': 'W', 'wednesday': 'W',
        'Thursday': 'Th', 'Th': 'Th', 'thursday': 'Th',
        'Friday': 'F', 'F': 'F', 'friday': 'F'
    }
    
    for row in rows:
        # Split on pipe
        slot_rooms = row['room'].split('|')
        
        for slot_room in slot_rooms:
            slot_room = slot_room.strip()
            if not slot_room:
                continue
            
            # Super-normalize DB room
            super_norm_slot = super_normalize_room(slot_room)
            
            # Zero-space-tolerance matching
            if super_norm_slot == super_norm_room:
                raw_matches += 1
                
                # FLATTEN: Expand concatenated slots (e.g., '12' -> [1, 2])
                time_slot_str = str(row['time_slot'])
                
                # PHASE 5.2 FIX: Parse concatenated day string (e.g., 'TTW', 'ThTh')
                # The 'day' column is NOT a single day, but a sequence matching the slots!
                raw_day_str = row['day'].strip()
                individual_days = []
                j = 0
                while j < len(raw_day_str):
                    # Check for 'Th' (Thursday) - the only 2-letter day code
                    if j < len(raw_day_str) - 1 and raw_day_str[j:j+2] == 'Th':
                        individual_days.append('Th')
                        j += 2
                    else:
                        individual_days.append(raw_day_str[j])
                        j += 1
                
                # PHASE 5.3: Context-Aware Slot Parsing
                # We use the number of days to resolve ambiguities like '112' -> [1, 1, 2] vs [11, 2] vs [1, 12]
                target_count = len(individual_days)
                time_slot_str = str(row['time_slot'])
                
                def smart_parse_slots(s, target, current_slots):
                    # Base cases
                    if target == 0:
                        return current_slots if not s else None
                    if not s:
                        return None
                    
                    # Option A: Try taking 1 digit
                    digit1 = int(s[0])
                    res1 = smart_parse_slots(s[1:], target - 1, current_slots + [digit1])
                    if res1: return res1
                    
                    # Option B: Try taking 2 digits (must be 10, 11, 12, 13)
                    if len(s) >= 2:
                        val2 = int(s[:2])
                        if 10 <= val2 <= 13:
                            res2 = smart_parse_slots(s[2:], target - 1, current_slots + [val2])
                            if res2: return res2
                    
                    return None

                # Try smart parse first
                individual_slots = smart_parse_slots(time_slot_str, target_count, [])
                
                # Fallback to greedy if smart parse fails (or if target_count was 0 somehow)
                if not individual_slots:
                    individual_slots = []
                    i = 0
                    while i < len(time_slot_str):
                        if i < len(time_slot_str) - 1:
                            two_digit = time_slot_str[i:i+2]
                            if two_digit in ['10', '11', '12', '13']:
                                individual_slots.append(int(two_digit))
                                i += 2
                                continue
                        if time_slot_str[i].isdigit():
                            individual_slots.append(int(time_slot_str[i]))
                        i += 1
                    if len(individual_slots) != target_count:
                         print(f"  [WARNING] Slot logic failure for {row['course_code']} (Day: {raw_day_str}, Slot: {time_slot_str}). Smart parse failed. Greedy yielded {len(individual_slots)} slots, expected {target_count}.")

                # Loop is safe now
                loop_count = min(len(individual_slots), len(individual_days))

                for k in range(loop_count):
                    slot_num = individual_slots[k]
                    day_code = individual_days[k]
                    
                    # STRICT DAY STANDARDIZATION
                    standardized_day = DAY_STANDARDIZATION.get(day_code)
                    
                    if standardized_day is None:
                        # Try mapping common variations if not in strict map
                        # But for now, strict map has 'M','T','W','Th','F'
                        continue
                    
                    # Strip section numbers for display - DISABLED (Phase 6 User Request)
                    course_code = row['course_code']
                    # if '.' in course_code:
                    #     course_code = course_code.split('.')[0]
                    
                    flattened_schedule.append({
                        'day': standardized_day,
                        'time_slot': slot_num,
                        'course_code': course_code
                    })
    
    print(f"Raw matches found: {raw_matches}")
    print(f"Flattened entries: {len(flattened_schedule)}")
    
    if len(flattened_schedule) > 0:
        print(f"PHASE 5.1 - Sample flattened entries:")
        for entry in flattened_schedule[:10]:
            print(f"  day='{entry['day']}', slot={entry['time_slot']}, course='{entry['course_code']}'")
    else:
        print(f"[CRITICAL] Room '{room_name}' has NO entries in the processed list!")
    
    return flattened_schedule


@app.route('/api/schedule/room', methods=['POST'])
def get_room_schedule():
    """
    PRE-PROCESSED SCHEDULE VIEW: Returns flattened, clean data
    """
    try:
        data = request.get_json()
        semester = data.get('semester')
        room = data.get('room')
        
        if not semester or not room:
            return jsonify({'success': False, 'error': 'Missing semester or room'}), 400
        
        # Use pre-processor function
        schedule = get_formatted_room_schedule(room, semester)
        
        return jsonify({'success': True, 'schedule': schedule})
        
    except Exception as e:
        print(f"ERROR in get_room_schedule: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/search/course', methods=['POST'])
def search_course():
    """
    PHASE 4.6: Strict course code matching with canonical building names
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        semester = data.get('semester')
        query = data.get('query')
        
        if not semester or not query:
            return jsonify({'success': False, 'error': 'Missing required parameters'}), 400
        
        conn = init_db()
        cursor = conn.cursor()
        
        # MAPPING FIX: 'Search Anywhere' - match query anywhere in code, ignore dots/spaces
        # Makes 'CE214', 'CE 214', 'CE214.01' all match
        sql = """
            SELECT c.id, c.course_code, c.course_name, c.instructor,
                   s.day, s.time_slot, TRIM(s.room) as room, s.building_name
            FROM courses c
            LEFT JOIN schedule_slots s ON c.id = s.course_id
            WHERE c.semester = ? 
              AND REPLACE(REPLACE(UPPER(c.course_code), ' ', ''), '.', '') 
                  LIKE '%' || REPLACE(REPLACE(UPPER(?), ' ', ''), '.', '') || '%'
            ORDER BY c.course_code
        """
        
        print(f"\n=== SEARCH ANYWHERE: Course Search ===")
        print(f"Original query: '{query}'")
        print(f"Searching for: {query.replace(' ', '').replace('.', '').upper()} (anywhere in course code)")
        
        cursor.execute(sql, (semester, query))
        rows = cursor.fetchall()
        
        if not rows:
            return jsonify({'success': True, 'courses': []})
        
        # Group results by course code
        results = {}
        
        for row in rows:
            c_code = row['course_code']
            if c_code not in results:
                results[c_code] = {
                    'course_code': c_code,
                    'course_name': row['course_name'],
                    'semester': semester,
                    'instructor': row['instructor'],
                    'schedule_slots': []
                }
            
            if row['day'] or row['time_slot'] or row['room']:
                # PHASE 4.6: Split ONLY on pipe, normalize, deduplicate
                raw_room = row['room']
                
                # Parse delimited rooms (split on pipe only)
                room_parts = raw_room.split('|') if raw_room else []
                unique_rooms = set()
                
                for part in room_parts:
                    part = part.strip()
                    if part and is_valid_room(part):
                        normalized = normalize_room_name(part)
                        if normalized:
                            unique_rooms.add(normalized)
                
                # Join unique normalized rooms
                clean_room = ' | '.join(sorted(unique_rooms)) if unique_rooms else raw_room
                
                # PHASE 4.6: Get CANONICAL building name
                building_name = get_building_name_for_room(list(unique_rooms)[0] if unique_rooms else raw_room) or row['building_name'] or 'N/A'
                
                results[c_code]['schedule_slots'].append({
                    'day': row['day'],
                    'time_slot': row['time_slot'],
                    'room': clean_room,
                    'building_name': building_name
                })
        
        courses = list(results.values())
        return jsonify({'success': True, 'courses': courses})
        
    except Exception as e:
        print(f"ERROR in search_course: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=port)
