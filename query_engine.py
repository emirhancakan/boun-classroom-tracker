import sqlite3
import re
from typing import List, Dict, Optional
from building_mapper import get_building_name

DB_NAME = "buis_schedule.db"


def init_db():
    """Initialize database connection with row factory."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_days_string(days_str):
    """
    Parses a day string like "MMTh" into ['M', 'M', 'Th'].
    """
    if not days_str:
        return []
    tokens = re.findall(r'Th|St|Su|M|T|W|F', days_str)
    return tokens


def _parse_times_string(times_str):
    """
    Parses a time string like "345" into ['3', '4', '5'].
    """
    if not times_str:
        return []
    return list(times_str)


def _parse_rooms_string(rooms_str):
    """
    Parses a room string like "M 1100|M 1100" into ['M 1100', 'M 1100'].
    Also handles single rooms "M 1100".
    """
    if not rooms_str:
        return []
    return [r.strip() for r in rooms_str.split('|') if r.strip()]


def _get_expanded_schedule(day_str, time_str, room_str):
    """
    Zips days, times, and rooms into a list of (day, slot, room) tuples.
    Resolves 1-to-Many or Many-to-Many relationships.
    """
    days = _parse_days_string(day_str)
    times = _parse_times_string(time_str)
    rooms = _parse_rooms_string(room_str)
    
    if len(days) != len(times):
        # Mismatch fallback: can't place it properly
        return []
    
    count = len(days)
    result = []
    
    for i in range(count):
        d = days[i]
        t = times[i]
        
        # Room resolution
        r = None
        if len(rooms) == count:
            r = rooms[i]
        elif len(rooms) == 1:
            r = rooms[0]
        else:
            # Use index if within bounds, else last
            if i < len(rooms):
                r = rooms[i]
            elif rooms:
                r = rooms[-1]
            else:
                r = None  # No room specific info
                
        result.append((d, t, r))
        
    return result


# ============================================================================
# PHASE 3: Main Query Functions
# ============================================================================

def get_course_details(code: str, semester: str) -> Optional[Dict]:
    """
    Returns all schedule slots and building info for a specific course.
    
    This is one of the two main functions for Phase 3. It retrieves comprehensive
    information about a course including all its schedule slots and building details.
    
    Args:
        code (str): The course code (e.g., 'CE241.01' for exact match, 
                    or 'CE241' to get all sections)
        semester (str): The semester (e.g., '2025/2026-1')
        
    Returns:
        dict: A dictionary containing course information with schedule slots,
              or None if the course is not found.
              
    Example return for exact course code:
        {
            'course_code': 'CE241.01',
            'course_name': 'Statics',
            'semester': '2025/2026-1',
            'instructor': 'STAFF',
            'schedule_slots': [
                {
                    'day': 'Monday',          # or 'M' if stored as abbreviation
                    'time_slot': '09:00-11:00',  # or '345' if stored as slot numbers
                    'room': 'M2180',
                    'building_name': 'Mühendislik Binası'
                },
                ...
            ]
        }
        
    Example return for course prefix (e.g., 'CE241'):
        [
            {
                'course_code': 'CE241.01',
                'course_name': 'Statics',
                'instructor': 'STAFF',
                'schedule_slots': [...]
            },
            {
                'course_code': 'CE241.02',
                'course_name': 'Statics',
                'instructor': 'Dr. Smith',
                'schedule_slots': [...]
            }
        ]
    """
    conn = init_db()
    cursor = conn.cursor()
    
    query_code = code.strip()
    
    # Logic: if "." present -> match exact. If not -> match prefix.
    try:
        if "." in query_code:
            # Exact match for specific section
            sql = """
                SELECT c.id, c.course_code, c.course_name, c.instructor,
                       s.day, s.time_slot, s.room, s.building_name
                FROM courses c
                LEFT JOIN schedule_slots s ON c.id = s.course_id
                WHERE c.course_code = ? AND c.semester = ?
            """
            cursor.execute(sql, (query_code, semester))
        else:
            # Prefix match for all sections
            sql = """
                SELECT c.id, c.course_code, c.course_name, c.instructor,
                       s.day, s.time_slot, s.room, s.building_name
                FROM courses c
                LEFT JOIN schedule_slots s ON c.id = s.course_id
                WHERE c.course_code LIKE ? AND c.semester = ?
                ORDER BY c.course_code
            """
            cursor.execute(sql, (f"{query_code}.%", semester))
            
        rows = cursor.fetchall()
        
        if not rows:
            return None
            
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
            
            raw_days = row['day']
            raw_times = row['time_slot']
            raw_rooms = row['room']
            db_bname = row['building_name']
            
            # Expand composite schedule strings (handles "MMTh", "345", etc.)
            expanded = _get_expanded_schedule(raw_days, raw_times, raw_rooms)
            
            if not expanded:
                # If parsing failed but we have raw data, include it as-is
                if raw_days or raw_times or raw_rooms:
                    results[c_code]['schedule_slots'].append({
                        'day': raw_days,
                        'time_slot': raw_times,
                        'room': raw_rooms,
                        'building_name': db_bname,
                        'note': 'Raw data (not expanded)'
                    })
            else:
                # Add expanded slots with enriched building information
                for (d, t, r) in expanded:
                    # Enrich building name using mapping logic if not in DB
                    b_name = db_bname
                    if not b_name and r:
                        b_name = get_building_name(r)
                    
                    results[c_code]['schedule_slots'].append({
                        'day': d,
                        'time_slot': t,
                        'room': r,
                        'building_name': b_name
                    })
        
        # Return single dict if exact match, list if prefix match
        result_list = list(results.values())
        if "." in query_code:
            return result_list[0] if result_list else None
        else:
            return result_list
            
    finally:
        conn.close()


def get_available_rooms(building: str, day: str, time_slot: str, semester: str) -> List[Dict]:
    """
    Identifies which rooms in a given building are NOT occupied by any course
    during a specific time and semester.
    
    This is the CORE FEATURE for Phase 3 - finding available classrooms.
    
    The function works by:
    1. Finding all rooms that exist in the target building (from historical data)
    2. Finding all rooms currently occupied at the specified time/day/semester
    3. Returning the difference (available = all rooms - occupied rooms)
    
    Args:
        building (str): The building name or room prefix
                       Examples:
                       - Full name: 'Mühendislik Binası', 'New Hall'
                       - Prefix: 'M', 'NH', 'KB', 'HH'
                       - Special: 'VYKM' (Engineering 5th Floor)
        day (str): The day of the week (e.g., 'M', 'T', 'W', 'Th', 'F' 
                   or full names like 'Monday', 'Tuesday')
        time_slot (str): The time slot (e.g., '3', '4', '5' for individual slots,
                        or '09:00-11:00' for time ranges)
        semester (str): The semester (e.g., '2025/2026-1')
        
    Returns:
        list: A list of dictionaries containing available room information.
        
    Example return:
        [
            {
                'room': 'M2180',
                'building_name': 'Mühendislik Binası',
                'status': 'available'
            },
            {
                'room': 'M2181',
                'building_name': 'Mühendislik Binası',
                'status': 'available'
            },
            ...
        ]
    """
    conn = init_db()
    cursor = conn.cursor()
    
    try:
        # Normalize building input - convert prefix to full name
        target_building = building
        
        # Special case: VYKM
        if building.upper() == 'VYKM':
            target_building = 'Engineering Building, 5th Floor'
        elif len(building) <= 4:
            # Likely a prefix like 'M', 'NH', 'KB', 'HH'
            full_name = get_building_name(building)
            if full_name:
                target_building = full_name
        
        # Step 1: Get all rooms that exist in this building (from all semesters)
        # This gives us the complete inventory of rooms in the building
        cursor.execute("""
            SELECT DISTINCT room, building_name 
            FROM schedule_slots 
            WHERE room IS NOT NULL AND room != ''
        """)
        
        all_rows = cursor.fetchall()
        
        candidate_rooms = set()
        
        for row in all_rows:
            raw_rooms = row['room']
            db_bname = row['building_name']
            
            # Parse atomic rooms (handles "M 1100|M 1101" format)
            atomic_rooms = _parse_rooms_string(raw_rooms)
            
            for r_code in atomic_rooms:
                # Check if this room belongs to our target building
                
                # A) Database building name matches
                if db_bname and target_building.lower() in db_bname.lower():
                    candidate_rooms.add(r_code)
                    continue
                
                # B) Mapped building name matches (using building_mapper logic)
                mapped = get_building_name(r_code)
                if mapped and target_building.lower() in mapped.lower():
                    candidate_rooms.add(r_code)
        
        if not candidate_rooms:
            return []
        
        # Step 2: Find rooms that ARE occupied at this specific time
        cursor.execute("""
            SELECT s.room, s.day, s.time_slot 
            FROM schedule_slots s
            JOIN courses c ON s.course_id = c.id
            WHERE s.room IS NOT NULL 
              AND s.room != ''
              AND c.semester = ?
        """, (semester,))
        
        occupied_rows = cursor.fetchall()
        occupied_rooms = set()
        
        for row in occupied_rows:
            raw_d = row['day']
            raw_t = row['time_slot']
            raw_r = row['room']
            
            # Expand composite schedule (handles "MMTh", "345", etc.)
            expanded = _get_expanded_schedule(raw_d, raw_t, raw_r)
            
            for (d, t, r) in expanded:
                # Check if this slot matches our query
                if d == day and str(t) == str(time_slot):
                    if r and r in candidate_rooms:
                        occupied_rooms.add(r)
        
        # Step 3: Calculate available rooms
        available_rooms = candidate_rooms - occupied_rooms
        
        # Step 4: Build result list
        result = []
        for room in sorted(available_rooms):
            result.append({
                'room': room,
                'building_name': target_building,
                'status': 'available'
            })
        
        return result
        
    finally:
        conn.close()


def get_occupied_rooms(building: str, day: str, time_slot: str, semester: str) -> List[Dict]:
    """
    Helper function to identify which rooms ARE occupied in a building
    during a specific time and semester.
    
    This is useful for debugging and providing context alongside available rooms.
    
    Args:
        building (str): The building name or prefix
        day (str): The day of the week
        time_slot (str): The time slot
        semester (str): The semester
        
    Returns:
        list: A list of dictionaries containing occupied room information
              with the course that's occupying it.
              
    Example return:
        [
            {
                'room': 'M2180',
                'building_name': 'Mühendislik Binası',
                'status': 'occupied',
                'course_code': 'CE241.01',
                'course_name': 'Statics',
                'instructor': 'Dr. Smith'
            },
            ...
        ]
    """
    conn = init_db()
    cursor = conn.cursor()
    
    try:
        # Normalize building input
        target_building = building
        if building.upper() == 'VYKM':
            target_building = 'Engineering Building, 5th Floor'
        elif len(building) <= 4:
            full_name = get_building_name(building)
            if full_name:
                target_building = full_name
        
        # Get occupied rooms with course information
        cursor.execute("""
            SELECT s.room, s.day, s.time_slot, s.building_name,
                   c.course_code, c.course_name, c.instructor
            FROM schedule_slots s
            JOIN courses c ON s.course_id = c.id
            WHERE s.room IS NOT NULL 
              AND s.room != ''
              AND c.semester = ?
        """, (semester,))
        
        all_rows = cursor.fetchall()
        result = []
        
        for row in all_rows:
            raw_d = row['day']
            raw_t = row['time_slot']
            raw_r = row['room']
            db_bname = row['building_name']
            
            # Expand composite schedule
            expanded = _get_expanded_schedule(raw_d, raw_t, raw_r)
            
            for (d, t, r) in expanded:
                # Check if this slot matches our query
                if d == day and str(t) == str(time_slot):
                    # Check if room belongs to target building
                    b_name = db_bname
                    if not b_name and r:
                        b_name = get_building_name(r)
                    
                    if b_name and target_building.lower() in b_name.lower():
                        result.append({
                            'room': r,
                            'building_name': b_name,
                            'status': 'occupied',
                            'course_code': row['course_code'],
                            'course_name': row['course_name'],
                            'instructor': row['instructor']
                        })
        
        return sorted(result, key=lambda x: x['room'])
        
    finally:
        conn.close()


# ============================================================================
# Example Usage & Testing
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("PHASE 3: Search and Filtering Logic - Query Engine")
    print("=" * 70)
    
    # Test 1: get_course_details with exact course code
    print("\n[TEST 1] get_course_details() - Exact Match")
    print("-" * 70)
    
    # You'll need to replace with actual course codes from your database
    test_result = get_course_details("CE241.01", "2025/2026-1")
    if test_result:
        print(f"Course: {test_result['course_code']} - {test_result['course_name']}")
        print(f"Instructor: {test_result['instructor']}")
        print(f"Semester: {test_result['semester']}")
        print(f"Schedule Slots ({len(test_result['schedule_slots'])}):")
        for slot in test_result['schedule_slots']:
            print(f"  {slot.get('day', '?'):10} "
                  f"{slot.get('time_slot', '?'):15} "
                  f"{slot.get('room', '?'):10} "
                  f"({slot.get('building_name', 'Unknown')})")
    else:
        print("Course not found. Try with a different course code from your database.")
    
    # Test 2: get_course_details with course prefix
    print("\n[TEST 2] get_course_details() - Prefix Match (All Sections)")
    print("-" * 70)
    
    test_prefix = get_course_details("CE241", "2025/2026-1")
    if test_prefix:
        print(f"Found {len(test_prefix)} section(s):")
        for section in test_prefix[:3]:  # Show first 3
            print(f"  - {section['course_code']}: {section['course_name']} "
                  f"({section['instructor']}) - {len(section['schedule_slots'])} slots")
    else:
        print("No sections found.")
    
    # Test 3: get_available_rooms
    print("\n[TEST 3] get_available_rooms() - CORE FEATURE")
    print("-" * 70)
    
    available = get_available_rooms("M", "M", "3", "2025/2026-1")
    print(f"Available rooms in Engineering Building on Monday, Slot 3:")
    print(f"Total: {len(available)} rooms available")
    for room in available[:15]:  # Show first 15
        print(f"  [AVAIL] {room['room']:15} - {room['status']}")
    
    # Test 4: get_occupied_rooms (helper function)
    print("\n[TEST 4] get_occupied_rooms() - Helper Function")
    print("-" * 70)
    
    occupied = get_occupied_rooms("M", "M", "3", "2025/2026-1")
    print(f"Occupied rooms in Engineering Building on Monday, Slot 3:")
    print(f"Total: {len(occupied)} rooms occupied")
    for room in occupied[:10]:  # Show first 10
        print(f"  [OCCUP] {room['room']:15} - {room['course_code']:12} {room['course_name'][:30]}")
    
    # Test 5: Different buildings
    print("\n[TEST 5] Testing Different Buildings")
    print("-" * 70)
    
    buildings_to_test = [
        ("NH", "New Hall"),
        ("VYKM", "Engineering 5th Floor"),
        ("KB", "Kuzey Bina")
    ]
    
    for prefix, name in buildings_to_test:
        available = get_available_rooms(prefix, "T", "4", "2025/2026-1")
        print(f"{name:25} (prefix: {prefix:4}) - {len(available):3} rooms available on Tuesday, Slot 4")
    
    print("\n" + "=" * 70)
    print("Testing complete!")
    print("=" * 70)
