"""Small runtime helpers emitted into generated Python files."""

RUNTIME_HEADER = '''# Auto-generated from a Scratch/PenguinMod .sb3 project
import math
import time
import threading

answer = ""
sprite_x = 0
sprite_y = 0
sprite_direction = 90
current_costume = 1
current_backdrop = 1


def ask(question):
    return input(str(question) + " ")


def timer():
    return time.time()


def move_steps(steps):
    pass


def turn_right(degrees):
    pass


def turn_left(degrees):
    pass


def go_to_xy(x, y):
    pass


def glide_to_xy(secs, x, y):
    time.sleep(float(secs))


def point_in_direction(direction):
    pass


def change_x_by(dx):
    pass


def set_x(x):
    pass


def change_y_by(dy):
    pass


def set_y(y):
    pass


def set_costume(costume):
    pass


def set_backdrop(backdrop):
    pass


def broadcast(name):
    pass


def broadcast_and_wait(name):
    pass


class LocalStorage:
    def __init__(self):
        self.project_id = ""
        self.data = {}

    def setProjectId(self, project_id):
        self.project_id = str(project_id)

    def set(self, key, value):
        self.data[str(key)] = value

    def get(self, key, default=""):
        return self.data.get(str(key), default)


localstorage = LocalStorage()
'''
