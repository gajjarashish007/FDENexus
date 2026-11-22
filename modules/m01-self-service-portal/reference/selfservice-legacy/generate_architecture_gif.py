"""
Generate SmartOps Portal architecture & workflow animated GIF.
Run: python generate_architecture_gif.py
Output: screenshots/smartops-architecture-flow.gif
"""
import os
import math
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = os.path.join(os.path.dirname(__file__), 'screenshots')
OUT_FILE = os.path.join(OUT_DIR, 'smartops-architecture-flow.gif')
W, H = 1280, 720
FPS_MS = 900  # milliseconds per frame

# SmartOps dark theme
C = {
    'bg': (12, 18, 32),
    'panel': (22, 30, 48),
    'box': (30, 41, 59),
    'border': (51, 65, 85),
    'accent': (99, 102, 241),
    'accent2': (129, 140, 248),
    'green': (34, 197, 94),
    'cyan': (34, 211, 238),
    'orange': (245, 158, 11),
    'pink': (236, 72, 153),
    'text': (241, 245, 249),
    'muted': (148, 163, 184),
    'arrow': (99, 102, 241),
}


def load_fonts():
    candidates = [
        ('bold', 'C:/Windows/Fonts/segoeuib.ttf', 28),
        ('bold', 'C:/Windows/Fonts/arialbd.ttf', 28),
        ('title', 'C:/Windows/Fonts/segoeuib.ttf', 36),
        ('title', 'C:/Windows/Fonts/arialbd.ttf', 36),
        ('med', 'C:/Windows/Fonts/segoeui.ttf', 20),
        ('med', 'C:/Windows/Fonts/arial.ttf', 20),
        ('sm', 'C:/Windows/Fonts/segoeui.ttf', 15),
        ('sm', 'C:/Windows/Fonts/arial.ttf', 15),
        ('xs', 'C:/Windows/Fonts/segoeui.ttf', 13),
        ('xs', 'C:/Windows/Fonts/arial.ttf', 13),
    ]
    fonts = {}
    for key, path, size in candidates:
        if key not in fonts and os.path.exists(path):
            fonts[key] = ImageFont.truetype(path, size)
    default = ImageFont.load_default()
    for k in ('title', 'bold', 'med', 'sm', 'xs'):
        fonts.setdefault(k, default)
    return fonts


FONTS = load_fonts()


def new_frame():
    img = Image.new('RGB', (W, H), C['bg'])
    return img, ImageDraw.Draw(img)


def draw_header(draw, title, subtitle=''):
    draw.rounded_rectangle([24, 20, W - 24, 88], radius=12, fill=C['panel'], outline=C['border'])
    draw.text((48, 32), title, fill=C['text'], font=FONTS['title'])
    if subtitle:
        draw.text((48, 62), subtitle, fill=C['muted'], font=FONTS['sm'])


def draw_box(draw, x, y, w, h, label, sub='', color=C['accent'], alpha=1.0, icon=''):
    fill = color if alpha >= 1 else tuple(int(c * alpha + C['box'][i] * (1 - alpha)) for i, c in enumerate(color[:3]))
    draw.rounded_rectangle([x, y, x + w, y + h], radius=10, fill=C['box'], outline=fill, width=2)
    tx = x + w // 2
    title = f"{icon} {label}".strip() if icon else label
    bbox = draw.textbbox((0, 0), title, font=FONTS['med'])
    draw.text((tx - (bbox[2] - bbox[0]) // 2, y + 14), title, fill=C['text'], font=FONTS['med'])
    if sub:
        lines = sub.split('\n')
        sy = y + 42
        for line in lines:
            bb = draw.textbbox((0, 0), line, font=FONTS['xs'])
            draw.text((tx - (bb[2] - bb[0]) // 2, sy), line, fill=C['muted'], font=FONTS['xs'])
            sy += 16


def draw_arrow(draw, x1, y1, x2, y2, color=C['arrow'], width=3, progress=1.0):
    """Draw arrow with animated progress 0..1."""
    if progress <= 0:
        return
    ex = x1 + (x2 - x1) * progress
    ey = y1 + (y2 - y1) * progress
    draw.line([x1, y1, ex, ey], fill=color, width=width)
    if progress >= 0.85:
        angle = math.atan2(y2 - y1, x2 - x1)
        sz = 10
        for da in (2.6, -2.6):
            ax = x2 - sz * math.cos(angle - da)
            ay = y2 - sz * math.sin(angle - da)
            draw.line([x2, y2, ax, ay], fill=color, width=width)


def draw_layer_label(draw, x, y, text):
    draw.text((x, y), text, fill=C['accent2'], font=FONTS['bold'])


def frame_title():
    img, draw = new_frame()
    draw_header(draw, 'SmartOps Portal', 'Architecture & Workflow Overview')
    cx, cy = W // 2, H // 2 + 20
    draw.text((cx - 180, cy - 60), '☁️  Self-Service AWS Platform', fill=C['text'], font=FONTS['bold'])
    items = [
        'Infrastructure Chat  ·  Resource Dashboard  ·  App Deploy',
        'JWT Auth  ·  Audit Logs  ·  Real-time Plan/Apply',
    ]
    for i, t in enumerate(items):
        bb = draw.textbbox((0, 0), t, font=FONTS['sm'])
        draw.text((cx - (bb[2] - bb[0]) // 2, cy + i * 28), t, fill=C['muted'], font=FONTS['sm'])
    draw.text((cx - 120, H - 60), 'Animated architecture diagram →', fill=C['accent'], font=FONTS['sm'])
    return img


def frame_architecture(step):
    """step 0..4: layers appear progressively."""
    img, draw = new_frame()
    draw_header(draw, 'System Architecture', 'Three-tier: Browser UI → Flask API → AWS Cloud')

    layers = [
        (100, 'LAYER 1 — FRONTEND (Browser)', [
            (80, 155, 200, 95, 'portal.html', 'Login · Chat · Logs\nDeployments · Guide', C['accent'], '🔐'),
            (300, 155, 200, 95, 'Dashboard', 'index.html\nEC2 · S3 · DynamoDB', C['cyan'], '📊'),
            (520, 155, 200, 95, 'Services', 'dashboard.html\nDeploy modals', C['cyan'], '🚀'),
            (740, 155, 200, 95, 'portal-*.js', 'Auth · WS · SSP\nValidation', C['pink'], '⚡'),
            (960, 155, 200, 95, 'app-*.js', 'EC2 · ASG · Deploy\nDiagrams', C['pink'], '📦'),
        ]),
        (290, 'LAYER 2 — BACKEND (Python Flask :5000)', [
            (120, 345, 220, 100, 'backend-api.py', 'AWS boto3 CRUD\nHealth · Region', C['green'], '☁️'),
            (370, 345, 220, 100, 'ssp_api.py', 'Auth · Chat · Plan\nWebSocket · Logs', C['accent'], '🤖'),
            (620, 345, 220, 100, 'deploy_api.py', 'Static · Code ZIP\nDocker BYOI', C['orange'], '🐳'),
            (870, 345, 220, 100, 'ssp_store.py', 'SQLite users\nAudit · PRs', C['pink'], '💾'),
        ]),
        (490, 'LAYER 3 — AWS CLOUD', [
            (100, 535, 160, 85, 'EC2', 'Instances\nASG', C['green']),
            (280, 535, 160, 85, 'S3', 'Buckets\nStatic sites', C['green']),
            (460, 535, 160, 85, 'DynamoDB', 'Tables\nKeys', C['green']),
            (640, 535, 160, 85, 'ELB/ACM', 'Load balancers\nSSL certs', C['green']),
            (820, 535, 160, 85, 'ECR/ECS', 'Containers\nFargate', C['green']),
            (1000, 535, 160, 85, 'VPC', 'Network\nSubnets', C['green']),
        ]),
    ]

    for li, (ly, label, boxes) in enumerate(layers):
        if step > li:
            draw_layer_label(draw, 48, ly, label)
            for box in boxes:
                x, y, w, h, lbl, sub, col = box[:7]
                icon = box[7] if len(box) > 7 else ''
                draw_box(draw, x, y, w, h, lbl, sub, col, icon=icon)

    # Vertical flow arrows between layers
    if step >= 2:
        draw_arrow(draw, W // 2, 260, W // 2, 330, C['accent'], progress=min(1, (step - 1) * 0.5))
    if step >= 3:
        draw_arrow(draw, W // 2, 455, W // 2, 525, C['green'], progress=min(1, (step - 2) * 0.5))
    if step >= 4:
        draw.text((48, H - 44), 'REST + WebSocket + SSE  ·  JWT on SSP routes  ·  boto3 on AWS routes', fill=C['muted'], font=FONTS['xs'])

    return img


def frame_workflow(step):
    """Chat workflow flow - step 0..7."""
    img, draw = new_frame()
    draw_header(draw, 'Infrastructure Chat Workflow', '5-step governed path from request to AWS apply')

    nodes = [
        (60, 280, 150, 80, '1 Select\nService &\nAccount', C['accent']),
        (240, 280, 150, 80, '2 Chat\nMessage', C['accent']),
        (420, 280, 150, 80, '3 Review\nYAML Diff', C['orange']),
        (600, 280, 150, 80, '4 Terraform\nPlan', C['cyan']),
        (780, 280, 150, 80, '5 Approve\nPull Request', C['pink']),
        (960, 280, 150, 80, '6 Apply\nChanges', C['green']),
        (1080, 430, 150, 80, '7 Audit\nLog', C['muted']),
    ]

    for i, (x, y, w, h, lbl, col) in enumerate(nodes):
        active = i <= step
        alpha = 1.0 if active else 0.35
        fill = col if active else C['border']
        draw.rounded_rectangle([x, y, x + w, y + h], radius=10, fill=C['box'], outline=fill, width=3 if active else 1)
        lines = lbl.split('\n')
        sy = y + 16
        for line in lines:
            bb = draw.textbbox((0, 0), line, font=FONTS['sm'])
            draw.text((x + w // 2 - (bb[2] - bb[0]) // 2, sy), line,
                      fill=C['text'] if active else C['muted'], font=FONTS['sm'])
            sy += 18

    # Horizontal arrows
    arrow_pairs = [(210, 320, 240, 320), (390, 320, 420, 320), (570, 320, 600, 320),
                     (750, 320, 780, 320), (930, 320, 960, 320)]
    for i, (x1, y1, x2, y2) in enumerate(arrow_pairs):
        if step > i:
            prog = min(1.0, step - i)
            draw_arrow(draw, x1, y1, x2, y2, C['green'] if step > i else C['border'], progress=prog)

    # Down arrow to audit log
    if step >= 6:
        draw_arrow(draw, 1035, 360, 1155, 430, C['green'], progress=min(1, step - 5.5))

    # API labels below
    apis = [
        (60, 420, 'GET /middleware/services'),
        (240, 420, 'POST /chat/stream'),
        (420, 420, 'POST /plan/yaml-diff'),
        (600, 420, 'WS generate_plan'),
        (780, 420, 'POST /pr/approve'),
        (960, 420, 'WS apply_plan'),
        (1080, 530, 'GET /logs'),
    ]
    for i, (x, y, api) in enumerate(apis):
        if i <= step:
            draw.text((x, y), api, fill=C['accent2'], font=FONTS['xs'])

    # Example message
    if step >= 1:
        draw.rounded_rectangle([240, 155, 520, 230], radius=8, fill=C['panel'], outline=C['border'])
        draw.text((260, 168), 'User: "create vpc"', fill=C['green'], font=FONTS['sm'])
        draw.text((260, 192), '→ YAML diff → Plan → PR → Apply', fill=C['muted'], font=FONTS['xs'])

    return img


def frame_deploy_flow(step):
    """App deployment paths."""
    img, draw = new_frame()
    draw_header(draw, 'Application Deployment Flow', 'Three paths: Static Website · Code ZIP · Custom Docker')

    paths = [
        (80, 160, 340, 380, '🌐 Static Website', C['cyan'], [
            'Upload HTML/CSS/JS folder',
            'Validate index.html',
            'POST /deploy/static-website',
            '→ S3 bucket + CloudFront',
        ]),
        (470, 160, 340, 380, '📦 Code Upload', C['accent'], [
            'Upload project ZIP',
            'Auto-detect language',
            'POST /deploy/code-upload',
            '→ Docker build → ECR → ECS',
        ]),
        (860, 160, 340, 380, '🐳 Custom Docker', C['orange'], [
            'docker build + docker save',
            'Upload .tar image',
            'POST /deploy/byoi',
            '→ ECR push → ECS deploy',
        ]),
    ]

    for pi, (x, y, w, h, title, col, steps) in enumerate(paths):
        active = step >= pi
        outline = col if active else C['border']
        draw.rounded_rectangle([x, y, x + w, y + h], radius=12, fill=C['box'], outline=outline, width=3 if active else 1)
        draw.text((x + 20, y + 16), title, fill=C['text'] if active else C['muted'], font=FONTS['bold'])
        for si, st in enumerate(steps):
            if step >= pi or (pi == step and si <= step):
                show = si <= max(0, step - pi + 1) if step >= pi else False
                if show or (step == pi and si == 0):
                    color = C['green'] if show else C['muted']
                    draw.text((x + 24, y + 60 + si * 32), f'{"✓" if show else "○"} {st}', fill=color, font=FONTS['sm'])

    if step >= 2:
        draw.rounded_rectangle([80, 580, W - 80, 660], radius=10, fill=C['panel'], outline=C['green'])
        draw.text((100, 600), 'Manage Deployments  →  Table view: Rerun · Edit · Destroy  →  Log History', fill=C['text'], font=FONTS['med'])

    return img


def frame_data_flow(step):
    """End-to-end data flow single diagram."""
    img, draw = new_frame()
    draw_header(draw, 'End-to-End Data Flow', 'How a request travels through SmartOps Portal')

    boxes = [
        (80, 200, '👤 User', 'Browser'),
        (280, 200, '🔐 Auth', 'JWT login\nssp_store'),
        (480, 200, '🤖 Chat/SSP', 'Plan & Apply\nWebSocket'),
        (680, 200, '📊 Dashboard', 'boto3 CRUD'),
        (880, 200, '🚀 Deploy', 'Upload & build'),
        (1080, 200, '☁️ AWS', 'Live resources'),
        (580, 420, '📜 Audit Log', 'Every action\nrecorded'),
    ]

    for i, (x, y, title, sub) in enumerate(boxes):
        visible = i <= step
        col = [C['accent'], C['pink'], C['accent'], C['cyan'], C['orange'], C['green'], C['muted']][i]
        draw_box(draw, x, y, 150, 90, title, sub, col if visible else C['border'], alpha=1 if visible else 0.4)

    pairs = [(230, 245, 280, 245), (430, 245, 480, 245), (630, 245, 680, 245),
             (830, 245, 880, 245), (1030, 245, 1080, 245)]
    for i, (x1, y1, x2, y2) in enumerate(pairs):
        if step > i + 1:
            draw_arrow(draw, x1, y1, x2, y2, C['green'], progress=1)

    if step >= 6:
        for x in (555, 755, 955):
            draw_arrow(draw, x, 290, 655, 420, C['orange'], progress=min(1, step - 5))

    return img


def build_frames():
    frames = []
    durations = []

    # Title (hold)
    t = frame_title()
    for _ in range(2):
        frames.append(t.copy())
        durations.append(1200)

    # Architecture layers build up
    for s in range(5):
        frames.append(frame_architecture(s))
        durations.append(FPS_MS)

    # Hold full architecture
    full = frame_architecture(4)
    frames.append(full.copy())
    durations.append(1500)

    # Workflow steps
    for s in range(8):
        frames.append(frame_workflow(s))
        durations.append(700)

    # Deploy flow
    for s in range(4):
        frames.append(frame_deploy_flow(s))
        durations.append(FPS_MS)

    # Data flow
    for s in range(7):
        frames.append(frame_data_flow(s))
        durations.append(700)

    # Closing title
    for _ in range(2):
        frames.append(frame_title().copy())
        durations.append(1000)

    return frames, durations


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print('Generating SmartOps Portal architecture GIF...')
    frames, durations = build_frames()
    frames[0].save(
        OUT_FILE,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    size_kb = os.path.getsize(OUT_FILE) / 1024
    print(f'✓ Saved: {OUT_FILE}')
    print(f'  Frames: {len(frames)}  ·  Size: {size_kb:.0f} KB  ·  Resolution: {W}x{H}')


if __name__ == '__main__':
    main()
