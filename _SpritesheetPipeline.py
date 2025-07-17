import pygame
import sys
import os
import copy
from PIL import Image
from lupa import LuaRuntime

# --- Constants ---
WINDOW_WIDTH, WINDOW_HEIGHT = 1000, 600
PALETTE_HEIGHT = 50
PIXEL_SIZE = 20
DEFAULT_GRID_WIDTH = 32
DEFAULT_GRID_HEIGHT = 32
ZOOM_MIN, ZOOM_MAX = 0.01, 20
SIDEBAR_WIDTH = 100
FONT_SIZE = 18

# --- Palette ---
PALETTE = {}           # Maps index → RGBA
PALETTE_REVERSE = {}   # Maps RGBA → index

pygame.init()
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption("Pixel Art Editor with Projects")
font = pygame.font.SysFont(None, FONT_SIZE)
clock = pygame.time.Clock()

# --- Grid State ---
GRID_WIDTH, GRID_HEIGHT = DEFAULT_GRID_WIDTH, DEFAULT_GRID_HEIGHT
canvas = [[0 for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
current_color = 1
zoom = 1.0
offset_x = SIDEBAR_WIDTH
offset_y = 0
drawing = False
erasing = False
is_panning = False
pan_start = (0, 0)
undo_stack = []
redo_stack = []

# --- Lua Parser Setup ---
lua = LuaRuntime(unpack_returned_tuples=True)
with open("nxml.lua", "r") as f:
    lua_code = "nxml = dofile( \"nxml.lua\" )"
lua.execute(lua_code)
nxml = lua.eval("nxml")
parse_xml = nxml["parse"]

# --- Project Data ---
project_folders = []
selected_project_index = None
project_scroll = 0

# --- Functions ---
def find_folders_with_pngs_and_xmls(base_dir='.'):
    folders = []
    for entry in os.listdir(base_dir):
        full_path = os.path.join(base_dir, entry)
        if os.path.isdir(full_path):
            pngs = [f for f in os.listdir(full_path) if f.lower().endswith('.png')]
            xmls = [f for f in os.listdir(full_path) if f.lower().endswith('.xml')]
            if pngs or xmls:
                folders.append((entry, full_path, pngs, xmls))
    return folders

def load_image_from_path(path):
    global canvas, GRID_WIDTH, GRID_HEIGHT, PALETTE, PALETTE_REVERSE
    try:
        img = Image.open(path).convert("RGBA")
        w, h = img.size
        GRID_WIDTH, GRID_HEIGHT = w, h
        canvas = [[0 for _ in range(w)] for _ in range(h)]

        # --- Generate palette from unique RGBA values ---
        unique_colors = list({img.getpixel((x, y)) for y in range(h) for x in range(w)})
        PALETTE.clear()
        PALETTE_REVERSE.clear()

        if (0, 0, 0, 0) in unique_colors:
            PALETTE[0] = (0, 0, 0, 0)
            unique_colors.remove((0, 0, 0, 0))
            start_index = 1
        else:
            start_index = 0

        for idx, color in enumerate(unique_colors, start=start_index):
            PALETTE[idx] = color

        for i, color in PALETTE.items():
            PALETTE_REVERSE[color] = i

        # --- Fill canvas using new palette ---
        for y in range(h):
            for x in range(w):
                rgba = img.getpixel((x, y))
                canvas[y][x] = PALETTE_REVERSE.get(rgba, 0)

    except Exception as e:
        print(f"[Image Load Error] {e}")

def save_state():
    undo_stack.append(copy.deepcopy(canvas))
    if len(undo_stack) > 100:
        undo_stack.pop(0)
    redo_stack.clear()

def screen_to_grid(x, y):
    gx = int((x - offset_x) / (PIXEL_SIZE * zoom))
    gy = int((y - offset_y) / (PIXEL_SIZE * zoom))
    return gx, gy

def grid_to_screen(gx, gy):
    x = gx * PIXEL_SIZE * zoom + offset_x
    y = gy * PIXEL_SIZE * zoom + offset_y
    return int(x), int(y)

def draw_canvas():
    for y in range(GRID_HEIGHT):
        for x in range(GRID_WIDTH):
            val = canvas[y][x]
            if val != 0:
                color = PALETTE.get(val, (0, 0, 0))
                sx, sy = grid_to_screen(x, y)
                size = int(PIXEL_SIZE * zoom)
                pygame.draw.rect(screen, color[:3], (sx, sy, size, size))
    for x in range(GRID_WIDTH + 1):
        sx, _ = grid_to_screen(x, 0)
        _, sy2 = grid_to_screen(x, GRID_HEIGHT)
        pygame.draw.line(screen, (40, 40, 40), (sx, 0), (sx, WINDOW_HEIGHT))
    for y in range(GRID_HEIGHT + 1):
        _, sy = grid_to_screen(0, y)
        sx2, _ = grid_to_screen(GRID_WIDTH, y)
        pygame.draw.line(screen, (40, 40, 40), (SIDEBAR_WIDTH, sy), (WINDOW_WIDTH, sy))

def draw_palette():
    pygame.draw.rect(screen, (30, 30, 30), (0, WINDOW_HEIGHT - PALETTE_HEIGHT, WINDOW_WIDTH, PALETTE_HEIGHT))
    for idx, color in PALETTE.items():
        pygame.draw.rect(screen, color[:3], (SIDEBAR_WIDTH + 10 + idx * 40, WINDOW_HEIGHT - 40, 30, 30))
        if idx == current_color:
            pygame.draw.rect(screen, (255, 255, 255), (SIDEBAR_WIDTH + 10 + idx * 40, WINDOW_HEIGHT - 40, 30, 30), 2)

def draw_sidebar():
    pygame.draw.rect(screen, (50, 50, 50), (0, 0, SIDEBAR_WIDTH, WINDOW_HEIGHT))
    y_offset = 10 - project_scroll
    for i, (name, _, _, _) in enumerate(project_folders):
        text = font.render(name, True, (255, 255, 255))
        rect = text.get_rect(topleft=(10, y_offset))
        screen.blit(text, rect)
        if i == selected_project_index:
            pygame.draw.rect(screen, (255, 255, 0), rect.inflate(4, 4), 2)
        y_offset += FONT_SIZE + 10

def handle_sidebar_click(mx, my):
    global selected_project_index, offset_x, offset_y, zoom
    y_offset = 10 - project_scroll
    for i, (_, path, pngs, xmls) in enumerate(project_folders):
        if y_offset <= my <= y_offset + FONT_SIZE:
            selected_project_index = i
            if pngs:
                load_image_from_path(os.path.join(path, pngs[0]))
                offset_x = SIDEBAR_WIDTH
                offset_y = 0
                zoom = 1.0
            if xmls:
                xml_path = os.path.join(path, xmls[0])
                with open(xml_path, 'r') as f:
                    xml_content = f.read()
                anim_data = parse_xml(xml_content)
        y_offset += FONT_SIZE + 10

# --- Load Projects Once ---
project_folders = find_folders_with_pngs_and_xmls()

# --- Main Loop ---
running = True
while running:
    screen.fill((20, 20, 20))
    draw_sidebar()
    draw_canvas()
    draw_palette()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = pygame.mouse.get_pos()
            if mx < SIDEBAR_WIDTH:
                handle_sidebar_click(mx, my)
            elif my > WINDOW_HEIGHT - PALETTE_HEIGHT:
                if event.button == 1:
                    palette_idx = (mx - SIDEBAR_WIDTH - 10) // 40
                    if palette_idx in PALETTE:
                        current_color = palette_idx
            else:
                gx, gy = screen_to_grid(mx, my)
                if 0 <= gx < GRID_WIDTH and 0 <= gy < GRID_HEIGHT:
                    if event.button == 1:
                        drawing = True
                        if canvas[gy][gx] != current_color:
                            save_state()
                            canvas[gy][gx] = current_color
                    elif event.button == 3:
                        erasing = True
                        if canvas[gy][gx] != 0:
                            save_state()
                            canvas[gy][gx] = 0
                    elif event.button == 2:
                        is_panning = True
                        pan_start = (mx, my)
                if event.button in (4, 5):
                    old_zoom = zoom
                    zoom_factor = 1.1 if event.button == 4 else 1 / 1.1
                    zoom = max(ZOOM_MIN, min(ZOOM_MAX, zoom * zoom_factor))
                    rel_x = (mx - offset_x) / old_zoom
                    rel_y = (my - offset_y) / old_zoom
                    offset_x = mx - rel_x * zoom
                    offset_y = my - rel_y * zoom

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                drawing = False
            elif event.button == 3:
                erasing = False
            elif event.button == 2:
                is_panning = False

        elif event.type == pygame.MOUSEMOTION:
            mx, my = event.pos
            if drawing:
                gx, gy = screen_to_grid(mx, my)
                if 0 <= gx < GRID_WIDTH and 0 <= gy < GRID_HEIGHT:
                    if canvas[gy][gx] != current_color:
                        save_state()
                        canvas[gy][gx] = current_color
            elif erasing:
                gx, gy = screen_to_grid(mx, my)
                if 0 <= gx < GRID_WIDTH and 0 <= gy < GRID_HEIGHT:
                    if canvas[gy][gx] != 0:
                        save_state()
                        canvas[gy][gx] = 0
            elif is_panning:
                dx = mx - pan_start[0]
                dy = my - pan_start[1]
                offset_x += dx
                offset_y += dy
                pan_start = (mx, my)

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_z and pygame.key.get_mods() & pygame.KMOD_CTRL:
                if undo_stack:
                    redo_stack.append(copy.deepcopy(canvas))
                    canvas = undo_stack.pop()
            elif event.key == pygame.K_y and pygame.key.get_mods() & pygame.KMOD_CTRL:
                if redo_stack:
                    undo_stack.append(copy.deepcopy(canvas))
                    canvas = redo_stack.pop()

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
sys.exit()
