def get_building_name(room_code):
    """
    Maps a room code to a building name based on specific prefixes/rules.
    
    Args:
        room_code (str): The room code (e.g., 'M 1100', 'NH 101', 'VYKM').
        
    Returns:
        str: The building name, or None if no mapping is found.
    """
    if not room_code:
        return None
        
    room_code = room_code.strip()
    
    # VYKM is on the 5th floor of Mühendislik Binası (Engineering Building)
    if room_code == 'VYKM' or room_code.startswith('VYKM'):
        return 'Mühendislik Binası'
    
    if room_code.startswith('M'):
        return 'Mühendislik Binası'
        
    if room_code.startswith('NH'):
        return 'New Hall'
        
    if room_code.startswith('KB'):
        return 'Kuzey Bina'

    if room_code.startswith('HH'):
        return 'Hamlin Hall'
        
    return None
