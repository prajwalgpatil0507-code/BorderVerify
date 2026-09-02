import sys, os, numpy as np, cv2
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from PIL import Image, ImageDraw, ImageFont
from app.services.mrz import compute_check_digit
from app.services.ocr import run_ocr
from itertools import cycle

def pad(v, w): return v.ljust(w, '<')[:w]

def build_td3(doc_num, country, surname, given, dob, sex, expiry):
    dc = str(compute_check_digit(doc_num))
    dob_c = str(compute_check_digit(dob))
    exp_c = str(compute_check_digit(expiry))
    personal = "0" + "<" * 13
    per_c = str(compute_check_digit(personal))
    name = pad(f"{surname}<<{given}", 39)
    l1 = f"P<{country}{name}".ljust(44, "<")[:44]
    core = pad(doc_num,9)+dc+country+dob+dob_c+sex+expiry+exp_c+personal+per_c
    l2 = (core + str(compute_check_digit(core))).ljust(44,"<")[:44]
    return [l1, l2]

mrz = build_td3("P12345678","UTO","RAIJILO","MARK THOMAS","000504","M","250912")
print("L1:", mrz[0], len(mrz[0]))
print("L2:", mrz[1], len(mrz[1]))

fonts = ["consola.ttf","cour.ttf","lucida-console.ttf","Courier New.ttf","arialbd.ttf","cambriaz.ttf"]
sizes = [42, 56, 68]

for fontname in fonts:
    for size in sizes:
        try:
            font = ImageFont.truetype(os.path.join(r"C:\Windows\Fonts", fontname), size)
        except Exception:
            continue
        # measure width
        w_max = 0
        for line in mrz:
            bbox = font.getbbox(line)
            w_max = max(w_max, bbox[2]-bbox[0])
        W = w_max + 200
        H = size*3 + 100
        img = Image.new("L", (W, H), 255)
        draw = ImageDraw.Draw(img)
        for i, line in enumerate(mrz):
            draw.text((100, 40 + i*size*1.3), line, font=font, fill=0)
        arr = np.array(img)
        try:
            res = run_ocr(arr)
            got_l1 = "NO"
            got_l2 = "NO"
            for l in res.lines:
                t = l['text'].replace(" ","")
                if t and t[0]=='P':
                    if len(t)==44 and t.count('<'):
                        pass
                    got_l1 = t
                    break
            # Try to parse
            import re
            texts = [l['text'].replace(" ","") for l in res.lines]
            if len(texts)>=2:
                got_l1 = texts[0]
                got_l2 = texts[1]
            ok = got_l1==mrz[0] and got_l2==mrz[1]
            print(f"{fontname} {size}: w={W} matched={ok}")
            if ok:
                print("   MATCH!", got_l1, "|", got_l2)
            else:
                print("   got:", got_l1, "| |", got_l2)
        except Exception as e:
            print(f"{fontname} {size}: OCR ERR {e}")
