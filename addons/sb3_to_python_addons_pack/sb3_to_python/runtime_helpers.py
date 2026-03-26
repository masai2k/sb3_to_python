
import time

def move_steps(v): pass
def turn_right(v): pass
def turn_left(v): pass
def go_to_xy(x, y): pass
def glide_to_xy(secs, x, y): time.sleep(float(secs) if str(secs).replace('.','',1).isdigit() else 0)
def point_in_direction(v): pass
def point_towards(v): pass
def change_x_by(v): pass
def set_x_to(v): pass
def change_y_by(v): pass
def set_y_to(v): pass
def if_on_edge_bounce(): pass
def set_rotation_style(v): pass
def say(v): print(v)
def think(v): print(v)
def switch_costume_to(v): pass
def next_costume(): pass
def switch_backdrop_to(v): pass
def switch_backdrop_and_wait(v): pass
def next_backdrop(): pass
def change_effect_by(name, value): pass
def set_effect_to(name, value): pass
def clear_graphic_effects(): pass
def change_size_by(v): pass
def set_size_to(v): pass
def show(): pass
def hide(): pass
def go_to_front_back(v): pass
def go_forward_backward_layers(dir_name, num): pass
def play_sound_until_done(v): pass
def start_sound(v): pass
def stop_all_sounds(): pass
def change_sound_effect_by(name, value): pass
def set_sound_effect_to(name, value): pass
def clear_sound_effects(): pass
def change_volume_by(v): pass
def set_volume_to(v): pass
def ask(question):
    return input(str(question) + " ")
def delete_list_item(lst, index_1_based):
    try:
        i = int(index_1_based) - 1
        if 0 <= i < len(lst):
            del lst[i]
    except Exception:
        pass
def insert_list_item(lst, index_1_based, value):
    try:
        i = max(0, int(index_1_based) - 1)
        if i > len(lst):
            i = len(lst)
        lst.insert(i, value)
    except Exception:
        lst.append(value)
def replace_list_item(lst, index_1_based, value):
    try:
        i = int(index_1_based) - 1
        if 0 <= i < len(lst):
            lst[i] = value
    except Exception:
        pass
def list_item(lst, index_1_based):
    try:
        i = int(index_1_based) - 1
        return lst[i]
    except Exception:
        return None
def list_length(lst): return len(lst)
def list_contains(lst, value): return value in lst
def broadcast(name): pass
def broadcast_and_wait(name): pass
def create_clone_of(target): pass
def delete_this_clone(): pass
