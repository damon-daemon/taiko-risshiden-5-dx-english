"""Send input to the game through XTest on Xwayland (Wine is an X client there).

usage: xinput.py key NAME [NAME...]     # X keysym names: Return, Escape, Up, Down, z ...
       xinput.py click X Y [BUTTON]     # click at game-window pixel (screenshot coords);
                                        # button 1 left, 3 right, 4/5 wheel up/down
       xinput.py move X Y
       xinput.py drag X1 Y1 X2 Y2 [STEPS]  # left button held from 1 to 2 (map panning)

Raises and focuses the game's X window first. Screenshot coordinates (tools/emu/shot.sh,
physical pixels) are scaled to the X window size.
"""
import sys, time
from Xlib import X, XK, display
from Xlib.ext import xtest

d = display.Display()
root = d.screen().root

def find(w, name=b'Taiko Risshiden V DX'):
    try:
        if w.get_wm_name() in (name, name.decode()):
            return w
    except Exception:
        pass
    for c in w.query_tree().children:
        r = find(c, name)
        if r:
            return r

def game():
    w = find(root)
    if not w:
        raise SystemExit('game window not found')
    return w

def focus(w):
    w.set_input_focus(X.RevertToParent, X.CurrentTime)
    d.sync()

def key(names):
    focus(game())
    for n in names:
        code = d.keysym_to_keycode(XK.string_to_keysym(n))
        xtest.fake_input(d, X.KeyPress, code); d.sync(); time.sleep(0.15)
        xtest.fake_input(d, X.KeyRelease, code); d.sync(); time.sleep(0.35)

def pos(x, y, shot=(1920, 1080)):
    w = game()
    g = w.get_geometry()
    t = w.translate_coords(root, 0, 0)
    return w, -t.x + int(x * g.width / shot[0]), -t.y + int(y * g.height / shot[1])

def move(x, y):
    w, rx, ry = pos(x, y)
    xtest.fake_input(d, X.MotionNotify, x=rx, y=ry); d.sync()
    return w

def click(x, y, button=1):
    w = move(x, y)
    focus(w)
    time.sleep(0.1)
    xtest.fake_input(d, X.ButtonPress, button); d.sync(); time.sleep(0.1)
    xtest.fake_input(d, X.ButtonRelease, button); d.sync()

def drag(x1, y1, x2, y2, steps=20):
    w = move(x1, y1)
    focus(w)
    time.sleep(0.1)
    xtest.fake_input(d, X.ButtonPress, 1); d.sync(); time.sleep(0.1)
    for i in range(1, steps + 1):
        move(x1 + (x2 - x1) * i // steps, y1 + (y2 - y1) * i // steps)
        time.sleep(0.03)
    time.sleep(0.1)
    xtest.fake_input(d, X.ButtonRelease, 1); d.sync()

if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'key':
        key(sys.argv[2:])
    elif cmd == 'click':
        click(*(int(a) for a in sys.argv[2:5]))
    elif cmd == 'drag':
        drag(*(int(a) for a in sys.argv[2:7]))
    elif cmd == 'move':
        move(int(sys.argv[2]), int(sys.argv[3]))
