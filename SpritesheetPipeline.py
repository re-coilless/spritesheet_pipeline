import pygame
import sys
import os
import copy
from PIL import Image
from lupa import LuaRuntime
import time

# --- Constants ---
WINDOW_WIDTH, WINDOW_HEIGHT = 1200, 700
PALETTE_HEIGHT = 50
PIXEL_SIZE = 20
DEFAULT_GRID_WIDTH = 32
DEFAULT_GRID_HEIGHT = 32
ZOOM_MIN, ZOOM_MAX = 0.01, 20
SIDEBAR_WIDTH = 150
ANIMATION_PANEL_WIDTH = 200
FONT_SIZE = 16
SMALL_FONT_SIZE = 12

# --- Palette ---
PALETTE = {}           # Maps index → RGBA
PALETTE_REVERSE = {}   # Maps RGBA → index

pygame.init()
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption("Pixel Art Editor with Animation Controls")
font = pygame.font.SysFont(None, FONT_SIZE)
small_font = pygame.font.SysFont(None, SMALL_FONT_SIZE)
clock = pygame.time.Clock()

# --- Grid State ---
GRID_WIDTH, GRID_HEIGHT = DEFAULT_GRID_WIDTH, DEFAULT_GRID_HEIGHT
canvas = [[0 for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
full_spritesheet = [[0 for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
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

# --- Animation State ---
animations = []
current_animation_index = 0
current_frame_index = 0
is_playing = False
last_frame_time = 0
frame_duration = 0.2  # Default frame duration
current_image_path = None
current_xml_path = None

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

# --- Animation Data Structure ---
class Animation:
    def __init__(self, name, pos_x, pos_y, frame_width, frame_height, frame_count, frame_wait=0.2):
        self.name = name
        self.pos_x = pos_x
        self.pos_y = pos_y
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.frame_count = frame_count
        self.frame_wait = frame_wait

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

def parse_animations(anim_data):
    global animations
    animations = []
    
    print(f"[DEBUG] Parsing animations from XML data: {anim_data}")
    
    if not anim_data:
        print("[DEBUG] No animation data provided")
        return
    
    # Check if anim_data has children attribute
    if not hasattr(anim_data, 'children'):
        print("[DEBUG] Animation data has no children attribute")
        return
    
    print(f"[DEBUG] Found {len(anim_data.children)} children in XML")
    
    default_animation = None
    if hasattr(anim_data, 'attr') and hasattr(anim_data.attr, 'default_animation'):
        default_animation = anim_data.attr.default_animation
    
    print(f"[DEBUG] Default animation: {default_animation}")
    
    default_anim_data = None
    
    # Find default animation data first
    for i, child in enumerate(anim_data.children):
        print(f"[DEBUG] Child {i}: {child}")
        if hasattr(child, 'name'):
            print(f"[DEBUG] Child {i} name: {child.name}")
            if child.name == "RectAnimation":
                if hasattr(child, 'attr') and hasattr(child.attr, 'name'):
                    print(f"[DEBUG] RectAnimation name: {child.attr.name}")
                    if child.attr.name == default_animation:
                        default_anim_data = child
                        print(f"[DEBUG] Found default animation data")
                        break
    
    if not default_anim_data:
        print("[DEBUG] No default animation found, using first RectAnimation")
        # If no default found, use first RectAnimation
        for child in anim_data.children:
            if hasattr(child, 'name') and child.name == "RectAnimation":
                if hasattr(child, 'attr') and hasattr(child.attr, 'frame_width') and hasattr(child.attr, 'frame_height'):
                    default_anim_data = child
                    break
    
    if not default_anim_data:
        print("[DEBUG] No suitable default animation found")
        return
    
    # Get default frame dimensions
    default_frame_width = int(default_anim_data.attr.frame_width)
    default_frame_height = int(default_anim_data.attr.frame_height)
    
    print(f"[DEBUG] Default frame dimensions: {default_frame_width}x{default_frame_height}")
    
    # Parse all animations
    for child in anim_data.children:
        if hasattr(child, 'name') and child.name == "RectAnimation":
            if not hasattr(child, 'attr'):
                continue
                
            # Skip if it has a parent (child animation) or if it's metadata
            if hasattr(child.attr, 'parent') or hasattr(child.attr, 'state'):
                print(f"[DEBUG] Skipping child animation or metadata: {child.attr.name if hasattr(child.attr, 'name') else 'unknown'}")
                continue
            
            if not hasattr(child.attr, 'name'):
                print("[DEBUG] Skipping RectAnimation without name")
                continue
            
            name = child.attr.name
            pos_x = int(child.attr.pos_x) if hasattr(child.attr, 'pos_x') else 0
            pos_y = int(child.attr.pos_y) if hasattr(child.attr, 'pos_y') else 0
            frame_width = int(child.attr.frame_width) if hasattr(child.attr, 'frame_width') else default_frame_width
            frame_height = int(child.attr.frame_height) if hasattr(child.attr, 'frame_height') else default_frame_height
            frame_count = int(child.attr.frame_count) if hasattr(child.attr, 'frame_count') else 1
            frame_wait = float(child.attr.frame_wait) if hasattr(child.attr, 'frame_wait') else 0.2
            
            print(f"[DEBUG] Adding animation: {name} at ({pos_x}, {pos_y}) {frame_width}x{frame_height} with {frame_count} frames")
            animations.append(Animation(name, pos_x, pos_y, frame_width, frame_height, frame_count, frame_wait))
    
    print(f"[DEBUG] Total animations loaded: {len(animations)}")

def load_image_from_path(path):
    global canvas, full_spritesheet, GRID_WIDTH, GRID_HEIGHT, PALETTE, PALETTE_REVERSE, current_image_path
    try:
        current_image_path = path
        img = Image.open(path).convert("RGBA")
        w, h = img.size
        GRID_WIDTH, GRID_HEIGHT = w, h
        
        # Store full spritesheet
        full_spritesheet = [[0 for _ in range(w)] for _ in range(h)]
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

        # --- Fill full spritesheet using new palette ---
        for y in range(h):
            for x in range(w):
                rgba = img.getpixel((x, y))
                full_spritesheet[y][x] = PALETTE_REVERSE.get(rgba, 0)

        # Load current frame
        load_current_frame()

    except Exception as e:
        print(f"[Image Load Error] {e}")

def load_current_frame():
    global canvas
    if not animations or current_animation_index >= len(animations):
        return
    
    anim = animations[current_animation_index]
    frame_x = anim.pos_x + (current_frame_index * anim.frame_width)
    frame_y = anim.pos_y
    
    # Clear canvas
    canvas = [[0 for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
    
    # Copy current frame to canvas
    for y in range(min(anim.frame_height, GRID_HEIGHT - frame_y)):
        for x in range(min(anim.frame_width, GRID_WIDTH - frame_x)):
            if frame_y + y < GRID_HEIGHT and frame_x + x < GRID_WIDTH:
                canvas[y][x] = full_spritesheet[frame_y + y][frame_x + x]

def save_current_frame():
    if not animations or current_animation_index >= len(animations):
        return
    
    anim = animations[current_animation_index]
    frame_x = anim.pos_x + (current_frame_index * anim.frame_width)
    frame_y = anim.pos_y
    
    # Save current frame back to full spritesheet
    for y in range(min(anim.frame_height, len(canvas))):
        for x in range(min(anim.frame_width, len(canvas[0]))):
            if frame_y + y < GRID_HEIGHT and frame_x + x < GRID_WIDTH:
                full_spritesheet[frame_y + y][frame_x + x] = canvas[y][x]

def save_image():
    if not current_image_path:
        return
    
    try:
        # Create PIL image from full spritesheet
        img = Image.new("RGBA", (GRID_WIDTH, GRID_HEIGHT), (0, 0, 0, 0))
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                val = full_spritesheet[y][x]
                color = PALETTE.get(val, (0, 0, 0, 0))
                img.putpixel((x, y), color)
        
        img.save(current_image_path)
        print(f"Saved image to {current_image_path}")
    except Exception as e:
        print(f"[Image Save Error] {e}")

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
    # Draw the full spritesheet if no animations are loaded
    if not animations:
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                val = canvas[y][x]
                if val != 0:
                    color = PALETTE.get(val, (0, 0, 0))
                    sx, sy = grid_to_screen(x, y)
                    size = int(PIXEL_SIZE * zoom)
                    pygame.draw.rect(screen, color[:3], (sx, sy, size, size))
        
        # Draw full grid
        for x in range(GRID_WIDTH + 1):
            sx, _ = grid_to_screen(x, 0)
            pygame.draw.line(screen, (40, 40, 40), (sx, 0), (sx, WINDOW_HEIGHT))
        for y in range(GRID_HEIGHT + 1):
            _, sy = grid_to_screen(0, y)
            pygame.draw.line(screen, (40, 40, 40), (SIDEBAR_WIDTH, sy), (WINDOW_WIDTH, sy))
        return
    
    # Draw current frame if animations are loaded
    if current_animation_index >= len(animations):
        return
    
    anim = animations[current_animation_index]
    
    for y in range(min(anim.frame_height, len(canvas))):
        for x in range(min(anim.frame_width, len(canvas[0]))):
            val = canvas[y][x]
            if val != 0:
                color = PALETTE.get(val, (0, 0, 0))
                sx, sy = grid_to_screen(x, y)
                size = int(PIXEL_SIZE * zoom)
                pygame.draw.rect(screen, color[:3], (sx, sy, size, size))
    
    # Draw grid
    for x in range(anim.frame_width + 1):
        sx, _ = grid_to_screen(x, 0)
        pygame.draw.line(screen, (40, 40, 40), (sx, offset_y), (sx, offset_y + anim.frame_height * PIXEL_SIZE * zoom))
    
    for y in range(anim.frame_height + 1):
        _, sy = grid_to_screen(0, y)
        pygame.draw.line(screen, (40, 40, 40), (offset_x, sy), (offset_x + anim.frame_width * PIXEL_SIZE * zoom, sy))

def draw_palette():
    pygame.draw.rect(screen, (30, 30, 30), (0, WINDOW_HEIGHT - PALETTE_HEIGHT, WINDOW_WIDTH, PALETTE_HEIGHT))
    for idx, color in PALETTE.items():
        x_pos = SIDEBAR_WIDTH + 10 + idx * 30
        if x_pos < WINDOW_WIDTH - ANIMATION_PANEL_WIDTH - 30:
            pygame.draw.rect(screen, color[:3], (x_pos, WINDOW_HEIGHT - 40, 25, 25))
            if idx == current_color:
                pygame.draw.rect(screen, (255, 255, 255), (x_pos, WINDOW_HEIGHT - 40, 25, 25), 2)

def draw_sidebar():
    pygame.draw.rect(screen, (50, 50, 50), (0, 0, SIDEBAR_WIDTH, WINDOW_HEIGHT))
    y_offset = 10 - project_scroll
    for i, (name, _, _, _) in enumerate(project_folders):
        text = small_font.render(name, True, (255, 255, 255))
        rect = text.get_rect(topleft=(10, y_offset))
        screen.blit(text, rect)
        if i == selected_project_index:
            pygame.draw.rect(screen, (255, 255, 0), rect.inflate(4, 4), 2)
        y_offset += SMALL_FONT_SIZE + 5

def draw_animation_panel():
    panel_x = WINDOW_WIDTH - ANIMATION_PANEL_WIDTH
    pygame.draw.rect(screen, (40, 40, 40), (panel_x, 0, ANIMATION_PANEL_WIDTH, WINDOW_HEIGHT))
    
    y_offset = 10
    
    # Animation selector
    text = font.render("Animations:", True, (255, 255, 255))
    screen.blit(text, (panel_x + 10, y_offset))
    y_offset += 25
    
    if not animations:
        text = small_font.render("No animations loaded", True, (255, 100, 100))
        screen.blit(text, (panel_x + 10, y_offset))
        return
    
    for i, anim in enumerate(animations):
        color = (255, 255, 0) if i == current_animation_index else (200, 200, 200)
        text = small_font.render(f"{i}: {anim.name}", True, color)
        screen.blit(text, (panel_x + 10, y_offset))
        y_offset += 18
    
    y_offset += 20
    
    # Frame controls
    if animations and current_animation_index < len(animations):
        anim = animations[current_animation_index]
        text = font.render("Frame Controls:", True, (255, 255, 255))
        screen.blit(text, (panel_x + 10, y_offset))
        y_offset += 25
        
        # Frame counter
        text = small_font.render(f"Frame: {current_frame_index + 1}/{anim.frame_count}", True, (255, 255, 255))
        screen.blit(text, (panel_x + 10, y_offset))
        y_offset += 20
        
        # Frame navigation buttons
        prev_btn = pygame.Rect(panel_x + 10, y_offset, 30, 20)
        next_btn = pygame.Rect(panel_x + 50, y_offset, 30, 20)
        
        pygame.draw.rect(screen, (60, 60, 60), prev_btn)
        pygame.draw.rect(screen, (60, 60, 60), next_btn)
        
        prev_text = small_font.render("<", True, (255, 255, 255))
        next_text = small_font.render(">", True, (255, 255, 255))
        
        screen.blit(prev_text, (prev_btn.x + 10, prev_btn.y + 3))
        screen.blit(next_text, (next_btn.x + 10, next_btn.y + 3))
        
        y_offset += 30
        
        # Play/Pause button
        play_btn = pygame.Rect(panel_x + 10, y_offset, 70, 25)
        pygame.draw.rect(screen, (60, 60, 60), play_btn)
        play_text = small_font.render("Pause" if is_playing else "Play", True, (255, 255, 255))
        screen.blit(play_text, (play_btn.x + 20, play_btn.y + 5))
        
        y_offset += 35
        
        # Animation info
        info_text = small_font.render(f"Speed: {anim.frame_wait:.3f}s", True, (180, 180, 180))
        screen.blit(info_text, (panel_x + 10, y_offset))
        y_offset += 15
        
        info_text = small_font.render(f"Size: {anim.frame_width}x{anim.frame_height}", True, (180, 180, 180))
        screen.blit(info_text, (panel_x + 10, y_offset))
        y_offset += 15
        
        info_text = small_font.render(f"Pos: ({anim.pos_x}, {anim.pos_y})", True, (180, 180, 180))
        screen.blit(info_text, (panel_x + 10, y_offset))

def handle_sidebar_click(mx, my):
    global selected_project_index, offset_x, offset_y, zoom, current_xml_path
    y_offset = 10 - project_scroll
    for i, (_, path, pngs, xmls) in enumerate(project_folders):
        if y_offset <= my <= y_offset + SMALL_FONT_SIZE + 5:
            selected_project_index = i
            print(f"[DEBUG] Selected project: {path}")
            if pngs:
                print(f"[DEBUG] Loading image: {pngs[0]}")
                load_image_from_path(os.path.join(path, pngs[0]))
                offset_x = SIDEBAR_WIDTH
                offset_y = 0
                zoom = 1.0
            if xmls:
                current_xml_path = os.path.join(path, xmls[0])
                print(f"[DEBUG] Loading XML: {current_xml_path}")
                try:
                    with open(current_xml_path, 'r') as f:
                        xml_content = f.read()
                    print(f"[DEBUG] XML content preview: {xml_content[:200]}...")
                    anim_data = parse_xml(xml_content)
                    print(f"[DEBUG] Parsed XML data: {anim_data}")
                    parse_animations(anim_data)
                    global current_animation_index, current_frame_index
                    current_animation_index = 0
                    current_frame_index = 0
                    if animations:
                        print(f"[DEBUG] Loading first animation: {animations[0].name}")
                        load_current_frame()
                    else:
                        print("[DEBUG] No animations loaded!")
                except Exception as e:
                    print(f"[DEBUG] Error loading XML: {e}")
                    import traceback
                    traceback.print_exc()
        y_offset += SMALL_FONT_SIZE + 5

def handle_animation_panel_click(mx, my):
    global current_animation_index, current_frame_index, is_playing
    panel_x = WINDOW_WIDTH - ANIMATION_PANEL_WIDTH
    
    if mx < panel_x:
        return
    
    # Check animation selection
    y_offset = 35
    for i, anim in enumerate(animations):
        if y_offset <= my <= y_offset + 18:
            if i != current_animation_index:
                save_current_frame()
                current_animation_index = i
                current_frame_index = 0
                load_current_frame()
                save_image()
            return
        y_offset += 18
    
    # Check frame controls
    if animations and current_animation_index < len(animations):
        anim = animations[current_animation_index]
        
        # Frame navigation buttons
        y_offset = 35 + len(animations) * 18 + 65
        prev_btn = pygame.Rect(panel_x + 10, y_offset, 30, 20)
        next_btn = pygame.Rect(panel_x + 50, y_offset, 30, 20)
        
        if prev_btn.collidepoint(mx, my):
            if current_frame_index > 0:
                save_current_frame()
                current_frame_index -= 1
                load_current_frame()
                save_image()
        elif next_btn.collidepoint(mx, my):
            if current_frame_index < anim.frame_count - 1:
                save_current_frame()
                current_frame_index += 1
                load_current_frame()
                save_image()
        
        # Play/Pause button
        y_offset += 30
        play_btn = pygame.Rect(panel_x + 10, y_offset, 70, 25)
        if play_btn.collidepoint(mx, my):
            is_playing = not is_playing

def update_animation():
    global current_frame_index, last_frame_time
    if not is_playing or not animations or current_animation_index >= len(animations):
        return
    
    anim = animations[current_animation_index]
    current_time = time.time()
    
    if current_time - last_frame_time >= anim.frame_wait:
        save_current_frame()
        current_frame_index = (current_frame_index + 1) % anim.frame_count
        load_current_frame()
        last_frame_time = current_time

# --- Load Projects Once ---
project_folders = find_folders_with_pngs_and_xmls()

# --- Main Loop ---
running = True
while running:
    screen.fill((20, 20, 20))
    
    # Update animation playback
    update_animation()
    
    draw_sidebar()
    draw_canvas()
    draw_palette()
    draw_animation_panel()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = pygame.mouse.get_pos()
            
            if mx < SIDEBAR_WIDTH:
                handle_sidebar_click(mx, my)
            elif mx > WINDOW_WIDTH - ANIMATION_PANEL_WIDTH:
                handle_animation_panel_click(mx, my)
            elif my > WINDOW_HEIGHT - PALETTE_HEIGHT:
                if event.button == 1:
                    palette_idx = (mx - SIDEBAR_WIDTH - 10) // 30
                    if palette_idx in PALETTE:
                        current_color = palette_idx
            else:
                gx, gy = screen_to_grid(mx, my)
                if animations and current_animation_index < len(animations):
                    anim = animations[current_animation_index]
                    if 0 <= gx < anim.frame_width and 0 <= gy < anim.frame_height:
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
                if drawing:
                    save_current_frame()
                    save_image()
            elif event.button == 3:
                erasing = False
                if erasing:
                    save_current_frame()
                    save_image()
            elif event.button == 2:
                is_panning = False

        elif event.type == pygame.MOUSEMOTION:
            mx, my = event.pos
            if drawing and animations and current_animation_index < len(animations):
                anim = animations[current_animation_index]
                gx, gy = screen_to_grid(mx, my)
                if 0 <= gx < anim.frame_width and 0 <= gy < anim.frame_height:
                    if canvas[gy][gx] != current_color:
                        canvas[gy][gx] = current_color
            elif erasing and animations and current_animation_index < len(animations):
                anim = animations[current_animation_index]
                gx, gy = screen_to_grid(mx, my)
                if 0 <= gx < anim.frame_width and 0 <= gy < anim.frame_height:
                    if canvas[gy][gx] != 0:
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
                    save_current_frame()
                    save_image()
            elif event.key == pygame.K_y and pygame.key.get_mods() & pygame.KMOD_CTRL:
                if redo_stack:
                    undo_stack.append(copy.deepcopy(canvas))
                    canvas = redo_stack.pop()
                    save_current_frame()
                    save_image()
            elif event.key == pygame.K_SPACE:
                is_playing = not is_playing
            elif event.key == pygame.K_LEFT:
                if animations and current_animation_index < len(animations):
                    anim = animations[current_animation_index]
                    if current_frame_index > 0:
                        save_current_frame()
                        current_frame_index -= 1
                        load_current_frame()
                        save_image()
            elif event.key == pygame.K_RIGHT:
                if animations and current_animation_index < len(animations):
                    anim = animations[current_animation_index]
                    if current_frame_index < anim.frame_count - 1:
                        save_current_frame()
                        current_frame_index += 1
                        load_current_frame()
                        save_image()

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
sys.exit()