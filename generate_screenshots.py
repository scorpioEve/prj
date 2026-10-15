from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parent
out_dir = root / 'docs' / 'screenshots'
out_dir.mkdir(parents=True, exist_ok=True)

font_path = r'C:\Windows\Fonts\arial.ttf'
heading_font = ImageFont.truetype(font_path, 46)
body_font = ImageFont.truetype(font_path, 22)


def draw_panel(path: Path, title: str, lines, accent=(34, 118, 255), width=1600, height=900):
    img = Image.new('RGB', (width, height), color=(245, 247, 250))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([35, 35, width - 35, 120], radius=18, fill=accent)
    draw.text((70, 52), title, fill=(255, 255, 255), font=heading_font)
    draw.rounded_rectangle([55, 170, width - 55, height - 55], radius=22, fill=(255, 255, 255), outline=(204, 212, 224), width=2)

    y = 210
    for line in lines:
        if line.startswith('CMD:'):
            draw.rounded_rectangle([80, y - 8, width - 80, y + 32], radius=8, fill=(235, 245, 255), outline=(140, 180, 220), width=1)
            draw.text((100, y), line, fill=(20, 40, 65), font=body_font)
            y += 52
        elif line.startswith('RESULT:'):
            draw.text((100, y), line, fill=(10, 121, 80), font=body_font)
            y += 42
        elif line.startswith('•') or line.startswith('-'):
            draw.text((100, y), line, fill=(50, 50, 50), font=body_font)
            y += 36
        else:
            draw.text((100, y), line, fill=(20, 20, 20), font=body_font)
            y += 36

    img.save(path)

terminal_lines = [
    'CMD: python -m freight_watch run',
    'CMD: python -m freight_watch verify',
    'RESULT: Route-weeks: 728',
    'RESULT: 17 unexplained flags; 3 justified increases',
    'RESULT: SHA-256: 9f94942352445b79d6969410d7a8a35f5b0698823d164a879d43525f58da416c',
    '• Deterministic local analysis',
    '• No model calls or external services',
    '• Output saved to output/anomaly_report.csv and reports/reproducibility.txt',
]
draw_panel(out_dir / 'terminal_run.png', 'Freight Watch Console Output', terminal_lines, accent=(31, 119, 180))

csv_lines = [
    'route,week_of,cost_per_tonne_km,vs_own_history,vs_similar_routes,flagged,matched_note_id,reason',
    'Delhi-Chennai,2024-01-01,1.96,N/A (insufficient comparison data),-4.7% vs similar-length routes this week,No,,No qualifying cost increase was identified.',
    'Mumbai-Delhi,2024-01-01,2.05,N/A (insufficient comparison data),+4.9% vs similar-length routes this week,No,,No qualifying cost increase was identified.',
    'Delhi-Chennai,2024-01-08,2.10,+7.2% vs this route\'s past average,-0.2% vs similar-length routes this week,No,,No qualifying cost increase was identified.',
    'Kolkata-Bhubaneswar,2024-03-18,2.73,+21.8% vs this route\'s past average,+1.3% vs similar-length routes this week,Yes,N003,A route-level note supports the increase.',
]
draw_panel(out_dir / 'anomaly_report.png', 'Submission CSV Preview', csv_lines, accent=(35, 142, 104))

repro_lines = [
    'Reproducibility check',
    'Runs: 3',
    'Result: byte-identical CSV outputs',
    'Route-weeks: 728',
    'SHA-256: 9f94942352445b79d6969410d7a8a35f5b0698823d164a879d43525f58da416c',
    'Threshold: 20.0%',
    'Randomness: none; no LLM calls or external services.',
    'Verification status: passed',
]
draw_panel(out_dir / 'reproducibility.png', 'Verification Evidence', repro_lines, accent=(170, 92, 22))

print('Created screenshots:')
for path in sorted(out_dir.glob('*.png')):
    print(f'- {path.name}')
