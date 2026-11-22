"""ACTION_SEND: the action-menu request (kind 1) goes to every member + self link instead of the absent server
member (first word of flame_live.py ACTION_SHARE). KIN_PRESS (built in) stays: only the presser's own game grants;
the assist's type 12 "taken state" tells the other games. (offset_from_main, orig_hex, new_hex, is_code)"""

ACTION_SEND = [
    (0x11A3334, "042540F9", "042140F9", True),
]
ORDER = [ACTION_SEND]
