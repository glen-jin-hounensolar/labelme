import tkinter as tk
from tkinter import ttk
from pathlib import Path
import json
import time
import requests
import os
import json
from pathlib import Path

import threading
from PIL import Image

APP_DIR = Path(__file__).resolve().parent
CONFIG_FILE = APP_DIR / "configs.json"
print(CONFIG_FILE)
STATE_FILE = Path("labelme_current.json")

# -----------------------------
# Load config file
# -----------------------------
def load_configs():
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"configs.json not found at {CONFIG_FILE}")

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    return cfg["system"], cfg["runtime"]

SYSTEM, RUNTIME = load_configs()
AI_CONFIG = SYSTEM["AI_CONFIG"]
INFER_SIZE = SYSTEM["DEFAULT"]["infer_size"]
url = RUNTIME["url"]
model = RUNTIME["model"]
threshold = RUNTIME["threshold"]

# -----------------------------
# Labelme state
# -----------------------------
def get_current_image():
    if not STATE_FILE.exists():
        return None

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("current_image")
    except Exception:
        return None

# -----------------------------
# Get image size
# -----------------------------
def get_image_size(image_path):
    with Image.open(image_path) as img:
        return img.size 

# -----------------------------
# Scale the detection boxes to fit original image
# -----------------------------
INFER_W = INFER_SIZE["width"]
INFER_H = INFER_SIZE["height"]

def scale_box_to_original(box, orig_w, orig_h):
    """
    box: [x1, y1, x2, y2] in inference resolution
    return scaled box in original image resolution
    """
    sx = orig_w / INFER_W
    sy = orig_h / INFER_H

    x1, y1, x2, y2 = box

    return [
        int(x1 * sx),
        int(y1 * sy),
        int(x2 * sx),
        int(y2 * sy),
    ]

# -----------------------------
# AI stub
# -----------------------------
def call_ai(
    image_file_path: str,
    url: str,
    model: str,
    threshold: tuple[float, float, float] | None = None,
):
    filename = os.path.basename(image_file_path)

    data = {"model": model}

    if threshold is not None:
        data["threshold"] = ",".join(str(x) for x in threshold)

    with open(image_file_path, "rb") as f:
        resp = requests.post(
            url,
            files={"image": (filename, f, "image/jpeg")},
            data=data,
            timeout=(5, 30),
        )

    resp.raise_for_status()
    return resp.json()

# -----------------------------
# parse AI response
# -----------------------------
def parse_ai_response(resp_json, image_path, min_confidence=0.0):
    detections = []

    with Image.open(image_path) as img:
        orig_w, orig_h = img.size

    for det in resp_json.get("detections", []):
        try:
            label = det["type"]
            conf = float(det["confidence"].strip("%")) / 100.0
            if conf < min_confidence:
                continue

            box_infer = det["box"]  # [x1,y1,x2,y2] in 2048x1049

            x1, y1, x2, y2 = scale_box_to_original(
                box_infer, orig_w, orig_h
            )

            detections.append(
                {
                    "label": label,
                    "confidence": conf,
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                }
            )

        except Exception as e:
            print("[WARN] parse failed:", det, e)

    return detections


# -----------------------------
# Labelme json writer
# -----------------------------
def write_labelme_json(image_path, detections):
    image_path = Path(image_path)
    json_path = image_path.with_suffix(".json")

    out = {
        "version": "5.3.0",
        "flags": {},
        "shapes": [],
        "imagePath": image_path.name,
        "imageData": None,
    }

    for det in detections:
        out["shapes"].append(
            {
                "label": det["label"],
                "points": [
                    [det["x1"], det["y1"]],
                    [det["x2"], det["y2"]],
                ],
                "group_id": None,
                "shape_type": "rectangle",
                "flags": {},  
            }
        )

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

# -----------------------------
# Tkinter UI
# -----------------------------
class MiddlewareUI(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("AI Annotation Middleware")
        self.geometry("500x500")
        self.resizable(True, True)

        # floating
        self.attributes("-topmost", True)

        # ===== Variables =====
        self.status = tk.StringVar(value="")
        
        self.url_var = tk.StringVar(value=RUNTIME["url"])
        self.model_var = tk.StringVar(value=RUNTIME["model"])

        self.th1_var = tk.DoubleVar(value=RUNTIME["threshold"][0])
        self.th2_var = tk.DoubleVar(value=RUNTIME["threshold"][1])
        self.th3_var = tk.DoubleVar(value=RUNTIME["threshold"][2])

        # ===== UI =====
        tk.Label(
            self,
            text="AI 标注中间件",
            font=("Arial", 12, "bold"),
        ).pack(pady=8)

        # Button
        self.btn = tk.Button(
            self,
            text="开始标注",
            height=2,
            width=28,
            command=self.on_ai_assist,
        )
        self.btn.pack(pady=10)

        # Threshold
        frm_th = tk.LabelFrame(self, text="Threshold (0 ~ 1)")
        frm_th.pack(pady=6, padx=10, fill="x")

        # Model
        frm_model = tk.Frame(self)
        frm_model.pack(pady=4)
        tk.Label(frm_model, text="Model:").pack(side=tk.LEFT)
        ttk.Combobox(
            frm_model,
            textvariable=self.model_var,
            values=AI_CONFIG["MODEL"],
            state="readonly",
            width=10,
        ).pack(side=tk.LEFT, padx=6)

        # URL
        frm_url = tk.Frame(self)
        frm_url.pack(pady=4)
        tk.Label(frm_url, text="Endpoint:").pack(side=tk.LEFT)
        ttk.Combobox(
            frm_url,
            textvariable=self.url_var,
            values=AI_CONFIG["URL"],
            state="readonly",
            width=30,
        ).pack(side=tk.LEFT, padx=6)

        # Status
        tk.Label(self, textvariable=self.status).pack(pady=5)
    
    
        def make_slider(parent, text, var):
            row = tk.Frame(parent)
            row.pack(fill="x", pady=2)

            tk.Label(row, text=text, width=8).pack(side=tk.LEFT)

            tk.Scale(
                row,
                from_=0.0,
                to=1.0,
                resolution=0.01,
                orient=tk.HORIZONTAL,
                variable=var,
                length=220,
            ).pack(side=tk.LEFT, padx=4)

            tk.Label(
                row,
                textvariable=var,
                width=5,
            ).pack(side=tk.LEFT)

        make_slider(frm_th, "T1", self.th1_var)
        make_slider(frm_th, "T2", self.th2_var)
        make_slider(frm_th, "T3", self.th3_var)

    # ===============================
    # UI thread: start worker thread
    # ===============================
    def on_ai_assist(self):
        self.save_runtime({
            "url": self.url_var.get(),
            "model": self.model_var.get(),
            "threshold": [
                round(self.th1_var.get(), 2),
                round(self.th2_var.get(), 2),
                round(self.th3_var.get(), 2),
            ],
        })
        self.btn.config(state="disabled")
        self.status.set("正在调用 AI …")
        self.update_idletasks()

        threading.Thread(
            target=self._run_ai_task,
            daemon=True,
        ).start()
    
    # ===============================
    # Load configs when start up
    # ===============================
    def load_runtime_defaults(config_default: dict):
        """
        config_default: DEFAULT from config.json
        returns merged default
        """
        result = config_default.copy()

        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)

                for k in ["url", "model", "threshold"]:
                    if k in saved:
                        result[k] = saved[k]

            except Exception as e:
                print("[WARN] Failed to load defaults.json:", e)

        return result

    # ===============================
    # Save configs while pressing button
    # ===============================

    def save_runtime(self, new_runtime: dict):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        cfg["runtime"] = new_runtime

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

    # ===============================
    # Worker thread
    # ===============================
    def _run_ai_task(self):
        try:
            img = get_current_image()
            if not img:
                self._ui_error("❌ 未获取到当前图片")
                return

            threshold = (
                round(self.th1_var.get(), 2),
                round(self.th2_var.get(), 2),
                round(self.th3_var.get(), 2),
            )

            resp = call_ai(
                image_file_path=img,
                url=self.url_var.get(),
                model=self.model_var.get(),
                threshold=threshold,
            )

            detections = parse_ai_response(
                resp_json=resp,
                image_path=img,
                min_confidence=0.0,
            )
            if not detections:
                self._ui_done("⚠️ AI 未返回任何缺陷")
                return

            write_labelme_json(img, detections)

            self._ui_done(f"✅ AI 标注完成（{len(detections)} 个缺陷）")

        except Exception as e:
            self._ui_error(f"❌ AI 调用失败: {e}")

    # ===============================
    # UI callbacks (main thread)
    # ===============================
    def _ui_done(self, msg):
        self.after(0, lambda: self._finish_ui(msg))

    def _ui_error(self, msg):
        self.after(0, lambda: self._finish_ui(msg))

    def _finish_ui(self, msg):
        self.status.set(msg)
        self.btn.config(state="normal")


if __name__ == "__main__":
    app = MiddlewareUI()
    app.mainloop()
