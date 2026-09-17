# -*- coding: utf-8 -*-
"""CADian 2023 교량 실측자료 보조 입력기
- 5개 측량점 x 가변 줄 수 표 (기본 6줄, +/-로 변경)
- 사용자가 지정한 '실측영역' 안에서만 OCR
- EasyOCR 숫자 후보를 위치/크기 기준으로 측량점 x 줄 표에 배치
- 도면의 작은 인쇄 치수는 우선순위를 낮춤
- 사진 마우스휠 확대/축소, 드래그 이동, 더블클릭 전체보기
- 표 셀 선택 시 대응 위치 표시/확대
- 셀 더블클릭 직접 수정
- 기존 cadian_measure.lsp와 호환되는 2열 CSV(index,value) 저장

주의: OCR은 보조 기능입니다. 저장 전 반드시 사진과 값을 대조하세요.
"""

import csv
import math
import re
import sys
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

OCR_AVAILABLE = False
OCR_IMPORT_ERROR = ""
try:
    import cv2
    import numpy as np
    from PIL import Image, ImageTk
    import easyocr
    OCR_AVAILABLE = True
except Exception:
    OCR_IMPORT_ERROR = traceback.format_exc()


COLS = 5
DEFAULT_ROWS = 6
# 일반적인 거더 간격 실측값 후보 범위. 범위 밖 숫자는 자동배치에서 제외하지만 직접입력은 가능.
AUTO_MIN_VALUE = 1000
AUTO_MAX_VALUE = 4000


class BridgeMeasureApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("교량 실측 CAD 자동작성")
        self.geometry("1500x880")
        self.minsize(1150, 700)

        self.image_path = None
        self.original_cv = None
        self.working_cv = None
        self.reader = None
        self.preview_photo = None

        # 뷰 상태
        self.fit_scale = 1.0
        self.zoom = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.drag_start = None
        self.image_item = None
        self.highlight_item = None

        # 표/실측영역 상태
        self.rows = DEFAULT_ROWS
        self.total = COLS * self.rows
        self.roi = None                 # (x1,y1,x2,y2) - working_cv 원본 좌표
        self.roi_select_mode = False
        self.roi_adjust_mode = False
        self.roi_start_canvas = None
        self.roi_temp_item = None
        self.roi_drag_handle = None
        self.roi_drag_origin = None

        # 각 셀: value/conf/status/box/source
        self.cells = [self.empty_cell() for _ in range(self.total)]
        self.col_centers = None
        self.row_centers = None

        self.create_ui()
        self.reset_grid()

    @staticmethod
    def empty_cell():
        return {"value": "", "confidence": 0.0, "status": "확인 필요", "box": None, "source": ""}

    # --------------------------------------------------------- UI
    def create_ui(self):
        toolbar = ttk.Frame(self, padding=7)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="실측사진 불러오기", command=self.load_image).pack(side="left", padx=3)
        ttk.Button(toolbar, text="왼쪽 90°", command=lambda: self.rotate_image(90)).pack(side="left", padx=3)
        ttk.Button(toolbar, text="오른쪽 90°", command=lambda: self.rotate_image(-90)).pack(side="left", padx=3)
        ttk.Button(toolbar, text="180°", command=lambda: self.rotate_image(180)).pack(side="left", padx=3)
        ttk.Button(toolbar, text="전체보기", command=self.fit_image).pack(side="left", padx=(10, 3))
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)

        ttk.Button(toolbar, text="실측영역 지정", command=self.start_roi_selection).pack(side="left", padx=3)
        ttk.Button(toolbar, text="영역 조정", command=self.start_roi_adjustment).pack(side="left", padx=3)
        ttk.Button(toolbar, text="영역 해제", command=self.clear_roi).pack(side="left", padx=3)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(toolbar, text="줄 수").pack(side="left", padx=(2, 2))
        ttk.Button(toolbar, text="－", width=3, command=lambda: self.change_rows(-1)).pack(side="left", padx=1)
        self.rows_var = tk.StringVar(value=str(self.rows))
        ttk.Label(toolbar, textvariable=self.rows_var, width=3, anchor="center").pack(side="left", padx=1)
        ttk.Button(toolbar, text="＋", width=3, command=lambda: self.change_rows(1)).pack(side="left", padx=1)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(toolbar, text="숫자 자동인식(OCR)", command=self.run_ocr).pack(side="left", padx=3)
        ttk.Button(toolbar, text="표 비우기", command=self.clear_values).pack(side="left", padx=3)
        ttk.Button(toolbar, text="CSV 저장", command=self.save_csv).pack(side="right", padx=3)

        guide = ttk.LabelFrame(self, text="사용 순서", padding=6)
        guide.pack(fill="x", padx=8, pady=(0, 4))
        ttk.Label(
            guide,
            text=("1) 사진 불러오기 → 2) 방향 확인/회전 → 3) 줄 수 설정 → 4) 실측영역 지정 → "
                  "5) OCR → 6) 표와 사진 대조/수정 → 7) CSV 저장 → 8) CADian에서 MEASUREAUTO 실행")
        ).pack(anchor="w")

        self.status_var = tk.StringVar(value="실측사진을 불러오세요.  |  휠: 확대/축소  드래그: 이동  더블클릭: 전체보기")
        ttk.Label(self, textvariable=self.status_var, padding=(10, 4)).pack(fill="x")

        self.paned = ttk.Panedwindow(self, orient="horizontal")
        self.paned.pack(fill="both", expand=True, padx=8, pady=5)

        left = ttk.LabelFrame(self.paned, text="실측자료 사진  (휠 확대/축소 · 드래그 이동 · 더블클릭 전체보기)", padding=5)
        self.paned.add(left, weight=3)
        self.image_canvas = tk.Canvas(left, background="#303030", highlightthickness=0)
        self.image_canvas.pack(fill="both", expand=True)
        self.image_canvas.bind("<Configure>", self.on_canvas_configure)
        self.image_canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.image_canvas.bind("<ButtonPress-1>", self.on_canvas_left_down)
        self.image_canvas.bind("<B1-Motion>", self.on_canvas_left_drag)
        self.image_canvas.bind("<ButtonRelease-1>", self.on_canvas_left_up)
        self.image_canvas.bind("<Double-Button-1>", lambda e: self.fit_image())

        right = ttk.LabelFrame(self.paned, text="실측값 5개 측량점 × 가변 줄 수 - 반드시 검토", padding=5)
        self.paned.add(right, weight=2)

        tree_frame = ttk.Frame(right)
        tree_frame.pack(fill="both", expand=True)
        columns = ("row", "p1", "p2", "p3", "p4", "p5")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse", height=10)
        self.tree.heading("row", text="줄")
        self.tree.column("row", width=55, anchor="center", stretch=False)
        for c in range(1, 6):
            key = f"p{c}"
            self.tree.heading(key, text=f"측량점 {c}")
            self.tree.column(key, width=105, anchor="center")
        self.tree.pack(fill="x", padx=2, pady=2)
        self.tree.bind("<Double-1>", self.edit_cell)
        self.tree.bind("<ButtonRelease-1>", self.on_tree_click)

        self.detail_var = tk.StringVar(value="표의 칸을 클릭하면 해당 사진 위치를 표시합니다.")
        ttk.Label(right, textvariable=self.detail_var, padding=(5, 8), wraplength=470, justify="left").pack(fill="x")

        legend = ttk.LabelFrame(right, text="검토", padding=7)
        legend.pack(fill="both", expand=True, pady=(5, 0))
        ttk.Label(
            legend,
            text=("• 먼저 [실측영역 지정] 후, 필요하면 [영역 조정]으로 테두리/모서리를 드래그해 미세조정하세요.\n"
                  "• OCR은 지정한 사각형 바깥의 숫자를 완전히 무시합니다.\n"
                  "• 줄 수는 상단 +/- 버튼으로 3~15줄까지 바꿀 수 있습니다.\n"
                  "• 손글씨로 판단하기 어려운 값은 빈칸/확인 필요로 둡니다.\n"
                  "• 값을 수정하려면 원하는 칸을 더블클릭하세요.\n"
                  "• 표의 칸을 한 번 클릭하면 사진의 대응 위치가 확대 표시됩니다.\n"
                  "• CSV 저장 순서: 측량점1의 1~N줄 → 측량점2의 1~N줄 → ... → 측량점5의 1~N줄")
        ).pack(anchor="nw")

        self.progress = ttk.Progressbar(right, mode="indeterminate")
        self.progress.pack(fill="x", padx=5, pady=10)

    def reset_grid(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for r in range(self.rows):
            self.tree.insert("", "end", iid=f"r{r}", values=(f"{r+1}줄", "", "", "", "", ""))
        self.refresh_grid()

    def rebuild_grid(self):
        self.total = COLS * self.rows
        self.cells = [self.empty_cell() for _ in range(self.total)]
        self.col_centers = None
        self.row_centers = None
        self.rows_var.set(str(self.rows))
        self.reset_grid()
        self.redraw_image()

    def change_rows(self, delta):
        new_rows = max(3, min(15, self.rows + delta))
        if new_rows == self.rows:
            return
        if any(str(x["value"]).strip() for x in self.cells):
            if not messagebox.askyesno("줄 수 변경", "줄 수를 변경하면 현재 표의 값이 초기화됩니다.\n\n계속할까요?"):
                return
        self.rows = new_rows
        self.rebuild_grid()

    def refresh_grid(self):
        for r in range(self.rows):
            vals = [f"{r+1}줄"]
            for c in range(COLS):
                cell = self.cells[c * self.rows + r]
                vals.append(str(cell["value"]) if cell["value"] else "")
            self.tree.item(f"r{r}", values=vals)
        done = sum(1 for x in self.cells if str(x["value"]).strip())
        need = self.total - done
        if self.image_path:
            roi_text = "실측영역 지정됨" if self.roi else "실측영역 미지정"
            self.status_var.set(
                f"인식/입력 {done}/{self.total}개  |  확인할 빈칸 {need}개  |  {roi_text}  |  휠 확대/축소 · 드래그 이동"
            )

    def clear_values(self):
        self.cells = [self.empty_cell() for _ in range(self.total)]
        self.col_centers = None
        self.row_centers = None
        self.refresh_grid()
        self.redraw_image()

    # --------------------------------------------------------- 오류 로그
    def save_error_log(self, text):
        paths = []
        try:
            paths.append(Path.home() / "Desktop" / "ocr_error.txt")
        except Exception:
            pass
        try:
            base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
            paths.append(base / "ocr_error.txt")
        except Exception:
            pass
        try:
            paths.append(Path.home() / "ocr_error.txt")
        except Exception:
            pass
        for p in paths:
            try:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(text)
                return str(p)
            except Exception:
                pass
        return None

    # --------------------------------------------------------- 이미지
    def load_image(self):
        path = filedialog.askopenfilename(
            title="실측자료 사진 선택",
            filetypes=[("사진 파일", "*.jpg *.jpeg *.png *.bmp *.webp"), ("모든 파일", "*.*")]
        )
        if not path:
            return
        if not OCR_AVAILABLE:
            messagebox.showerror("모듈 오류", "이미지 모듈을 불러오지 못했습니다.\n\n" + OCR_IMPORT_ERROR[-1200:])
            return
        try:
            data = np.fromfile(path, dtype=np.uint8)
            image = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError("사진 파일을 읽지 못했습니다.")
            self.image_path = path
            self.original_cv = image.copy()
            self.working_cv = image.copy()
            self.cells = [self.empty_cell() for _ in range(self.total)]
            self.col_centers = None
            self.row_centers = None
            self.roi = None
            self.refresh_grid()
            self.after(50, self.fit_image)
        except Exception as e:
            p = self.save_error_log(traceback.format_exc())
            messagebox.showerror("사진 오류", f"사진을 불러오는 중 오류가 발생했습니다.\n\n{e}\n\n상세 오류: {p or '-'}")

    def rotate_image(self, angle):
        if self.working_cv is None:
            messagebox.showwarning("확인", "먼저 실측사진을 불러오세요.")
            return
        if angle == 90:
            self.working_cv = cv2.rotate(self.working_cv, cv2.ROTATE_90_COUNTERCLOCKWISE)
        elif angle == -90:
            self.working_cv = cv2.rotate(self.working_cv, cv2.ROTATE_90_CLOCKWISE)
        else:
            self.working_cv = cv2.rotate(self.working_cv, cv2.ROTATE_180)
        self.cells = [self.empty_cell() for _ in range(self.total)]
        self.col_centers = None
        self.row_centers = None
        self.roi = None
        self.refresh_grid()
        self.after(30, self.fit_image)

    def on_canvas_configure(self, event=None):
        if self.working_cv is not None and self.zoom == 1.0:
            self.fit_image()
        else:
            self.redraw_image()

    def fit_image(self):
        if self.working_cv is None:
            return
        cw = max(1, self.image_canvas.winfo_width())
        ch = max(1, self.image_canvas.winfo_height())
        h, w = self.working_cv.shape[:2]
        self.fit_scale = min(cw / w, ch / h)
        self.zoom = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.redraw_image()

    def current_scale(self):
        return max(0.01, self.fit_scale * self.zoom)

    def redraw_image(self, selected_index=None):
        if self.working_cv is None:
            return
        try:
            cw = max(1, self.image_canvas.winfo_width())
            ch = max(1, self.image_canvas.winfo_height())
            rgb = cv2.cvtColor(self.working_cv, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            scale = self.current_scale()
            nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
            interp = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
            resized = cv2.resize(rgb, (nw, nh), interpolation=interp)
            self.preview_photo = ImageTk.PhotoImage(Image.fromarray(resized))
            self.image_canvas.delete("all")
            cx = cw / 2 + self.offset_x
            cy = ch / 2 + self.offset_y
            self.image_item = self.image_canvas.create_image(cx, cy, image=self.preview_photo, anchor="center")

            # 지정된 실측영역 표시
            if self.roi:
                rx1, ry1, rx2, ry2 = self.roi
                self.draw_source_rect(rx1, ry1, rx2, ry2, cx, cy, w, h, scale, width=2)

            # OCR 박스 또는 추정 셀 위치 표시
            if selected_index is not None and 0 <= selected_index < self.total:
                cell = self.cells[selected_index]
                box = cell.get("box")
                if box:
                    xs = [p[0] for p in box]
                    ys = [p[1] for p in box]
                    x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
                    self.draw_source_rect(x1, y1, x2, y2, cx, cy, w, h, scale)
                else:
                    c = selected_index // self.rows
                    r = selected_index % self.rows
                    if self.col_centers is not None and self.row_centers is not None:
                        x = self.col_centers[c]
                        y = self.row_centers[r]
                        bw = w * 0.08
                        bh = h * 0.06
                        self.draw_source_rect(x-bw/2, y-bh/2, x+bw/2, y+bh/2, cx, cy, w, h, scale)
        except Exception:
            pass

    def draw_source_rect(self, x1, y1, x2, y2, cx, cy, iw, ih, scale, width=3):
        left = cx - iw * scale / 2
        top = cy - ih * scale / 2
        X1, Y1 = left + x1 * scale, top + y1 * scale
        X2, Y2 = left + x2 * scale, top + y2 * scale
        self.image_canvas.create_rectangle(X1, Y1, X2, Y2, outline="#ff00aa", width=width)

    def on_mousewheel(self, event):
        if self.working_cv is None:
            return
        old_scale = self.current_scale()
        factor = 1.15 if event.delta > 0 else 1 / 1.15
        new_zoom = min(12.0, max(0.5, self.zoom * factor))
        if abs(new_zoom - self.zoom) < 1e-9:
            return
        cw, ch = self.image_canvas.winfo_width(), self.image_canvas.winfo_height()
        old_cx, old_cy = cw/2 + self.offset_x, ch/2 + self.offset_y
        # 마우스 아래의 이미지 위치가 유지되도록 오프셋 조정
        ratio = (self.fit_scale * new_zoom) / old_scale
        self.offset_x = event.x - cw/2 - (event.x - old_cx) * ratio
        self.offset_y = event.y - ch/2 - (event.y - old_cy) * ratio
        self.zoom = new_zoom
        self.redraw_image()

    def canvas_to_image(self, x, y):
        if self.working_cv is None:
            return None
        cw, ch = self.image_canvas.winfo_width(), self.image_canvas.winfo_height()
        h, w = self.working_cv.shape[:2]
        scale = self.current_scale()
        cx, cy = cw/2 + self.offset_x, ch/2 + self.offset_y
        left, top = cx - w*scale/2, cy - h*scale/2
        ix = (x - left) / scale
        iy = (y - top) / scale
        return max(0.0, min(w-1.0, ix)), max(0.0, min(h-1.0, iy))

    def start_roi_selection(self):
        if self.working_cv is None:
            messagebox.showwarning("확인", "먼저 실측사진을 불러오세요.")
            return
        self.roi_select_mode = True
        self.roi_adjust_mode = False
        self.roi_start_canvas = None
        self.status_var.set("실측영역 지정 중: 거더 내측의 손글씨 실측값 전체가 들어가도록 사각형으로 드래그하세요.")

    def start_roi_adjustment(self):
        if self.working_cv is None:
            messagebox.showwarning("확인", "먼저 실측사진을 불러오세요.")
            return
        if not self.roi:
            messagebox.showwarning("확인", "먼저 [실측영역 지정]으로 영역을 지정하세요.")
            return
        self.roi_select_mode = False
        self.roi_adjust_mode = True
        self.roi_drag_handle = None
        self.status_var.set("실측영역 조정 중: 분홍색 테두리/모서리를 드래그하세요. 영역 안쪽을 드래그하면 전체 영역이 이동합니다.")
        self.redraw_image()

    def clear_roi(self):
        self.roi = None
        self.roi_select_mode = False
        self.roi_adjust_mode = False
        self.roi_start_canvas = None
        self.roi_drag_handle = None
        self.redraw_image()
        self.refresh_grid()

    def _roi_hit_test(self, ix, iy):
        if not self.roi:
            return None
        x1, y1, x2, y2 = self.roi
        h, w = self.working_cv.shape[:2]
        tol = max(8.0, min(w, h) * 0.012)

        near_l = abs(ix-x1) <= tol
        near_r = abs(ix-x2) <= tol
        near_t = abs(iy-y1) <= tol
        near_b = abs(iy-y2) <= tol
        inside_x = x1-tol <= ix <= x2+tol
        inside_y = y1-tol <= iy <= y2+tol

        if near_l and near_t: return "tl"
        if near_r and near_t: return "tr"
        if near_l and near_b: return "bl"
        if near_r and near_b: return "br"
        if near_l and inside_y: return "l"
        if near_r and inside_y: return "r"
        if near_t and inside_x: return "t"
        if near_b and inside_x: return "b"
        if x1 < ix < x2 and y1 < iy < y2: return "move"
        return None

    def on_canvas_left_down(self, event):
        if self.roi_select_mode:
            self.roi_start_canvas = (event.x, event.y)
            if self.roi_temp_item:
                self.image_canvas.delete(self.roi_temp_item)
                self.roi_temp_item = None
        elif self.roi_adjust_mode and self.roi:
            p = self.canvas_to_image(event.x, event.y)
            if p:
                self.roi_drag_handle = self._roi_hit_test(*p)
                self.roi_drag_origin = (p[0], p[1], self.roi)
        else:
            self.drag_start = (event.x, event.y, self.offset_x, self.offset_y)

    def on_canvas_left_drag(self, event):
        if self.roi_select_mode and self.roi_start_canvas:
            x0, y0 = self.roi_start_canvas
            if self.roi_temp_item:
                self.image_canvas.delete(self.roi_temp_item)
            self.roi_temp_item = self.image_canvas.create_rectangle(
                x0, y0, event.x, event.y, outline="#ff00aa", width=3
            )
        elif self.roi_adjust_mode and self.roi_drag_handle and self.roi_drag_origin:
            p = self.canvas_to_image(event.x, event.y)
            if not p:
                return
            ix, iy = p
            sx, sy, old = self.roi_drag_origin
            x1, y1, x2, y2 = old
            h, w = self.working_cv.shape[:2]
            dx, dy = ix-sx, iy-sy
            handle = self.roi_drag_handle

            if handle == "move":
                ww, hh = x2-x1, y2-y1
                nx1 = max(0.0, min(w-ww, x1+dx))
                ny1 = max(0.0, min(h-hh, y1+dy))
                self.roi = (nx1, ny1, nx1+ww, ny1+hh)
            else:
                if "l" in handle: x1 = max(0.0, min(x2-10.0, ix))
                if "r" in handle: x2 = min(float(w-1), max(x1+10.0, ix))
                if "t" in handle: y1 = max(0.0, min(y2-10.0, iy))
                if "b" in handle: y2 = min(float(h-1), max(y1+10.0, iy))
                self.roi = (x1, y1, x2, y2)
            self.redraw_image()
        elif self.drag_start:
            sx, sy, ox, oy = self.drag_start
            self.offset_x = ox + (event.x - sx)
            self.offset_y = oy + (event.y - sy)
            self.redraw_image()

    def on_canvas_left_up(self, event):
        if self.roi_select_mode and self.roi_start_canvas:
            p1 = self.canvas_to_image(*self.roi_start_canvas)
            p2 = self.canvas_to_image(event.x, event.y)
            self.roi_start_canvas = None
            self.roi_select_mode = False
            self.roi_temp_item = None
            if p1 and p2:
                x1, y1 = p1
                x2, y2 = p2
                x1, x2 = sorted((x1, x2))
                y1, y2 = sorted((y1, y2))
                h, w = self.working_cv.shape[:2]
                if (x2-x1) < w*0.08 or (y2-y1) < h*0.08:
                    messagebox.showwarning("영역 확인", "선택 영역이 너무 작습니다. 다시 지정해주세요.")
                    self.roi = None
                else:
                    self.roi = (x1, y1, x2, y2)
                    self.cells = [self.empty_cell() for _ in range(self.total)]
                    self.col_centers = None
                    self.row_centers = None
                    self.refresh_grid()
            self.redraw_image()

        elif self.roi_adjust_mode and self.roi_drag_handle:
            self.roi_drag_handle = None
            self.roi_drag_origin = None
            # 영역을 바꾸면 기존 OCR 배치는 더 이상 좌표가 맞지 않으므로 초기화
            self.cells = [self.empty_cell() for _ in range(self.total)]
            self.col_centers = None
            self.row_centers = None
            self.refresh_grid()
            self.redraw_image()
            self.status_var.set("실측영역 조정 완료. [숫자 자동인식(OCR)]을 다시 실행하세요.")

        self.drag_start = None

    # --------------------------------------------------------- OCR
    def get_reader(self):
        if self.reader is None:
            self.status_var.set("OCR 엔진을 준비하고 있습니다...")
            self.update_idletasks()
            self.reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        return self.reader

    @staticmethod
    def normalize_text(raw):
        s = str(raw).strip().replace(" ", "").replace(",", "")
        trans = str.maketrans({"O":"0", "o":"0", "I":"1", "l":"1", "|":"1", "S":"5"})
        return s.translate(trans)

    @staticmethod
    def box_info(box):
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
        return (x1+x2)/2, (y1+y2)/2, max(1.0, x2-x1), max(1.0, y2-y1)

    @staticmethod
    def cluster_1d(values, k):
        """외부 sklearn 없이 간단한 1D k-means."""
        if len(values) < k:
            return None
        vals = sorted(float(v) for v in values)
        # 분위수 초기값
        centers = [vals[min(len(vals)-1, round((i+0.5)*len(vals)/k-0.5))] for i in range(k)]
        for _ in range(40):
            groups = [[] for _ in range(k)]
            for v in vals:
                j = min(range(k), key=lambda z: abs(v-centers[z]))
                groups[j].append(v)
            new = []
            for j, g in enumerate(groups):
                new.append(sum(g)/len(g) if g else centers[j])
            if max(abs(a-b) for a,b in zip(new, centers)) < 0.5:
                centers = new
                break
            centers = new
        return sorted(centers)

    def prepare_ocr_images(self):
        if not self.roi:
            raise RuntimeError("먼저 [실측영역 지정] 버튼으로 거더 내측 실측영역을 지정하세요.")

        x1, y1, x2, y2 = self.roi
        x1i, y1i = max(0, int(x1)), max(0, int(y1))
        x2i, y2i = min(self.working_cv.shape[1], int(x2)), min(self.working_cv.shape[0], int(y2))
        image = self.working_cv[y1i:y2i, x1i:x2i].copy()
        if image.size == 0:
            raise RuntimeError("실측영역이 올바르지 않습니다. 영역을 다시 지정하세요.")

        h0, w0 = image.shape[:2]
        max_side = max(h0, w0)
        scale = 1.0
        if max_side > 3200:
            scale = 3200.0 / max_side
            image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)

        # ROI 내부 좌표를 원본 사진 좌표로 되돌리기 위한 offset
        return np.ascontiguousarray(image), np.ascontiguousarray(enhanced), scale, (x1i, y1i)

    def collect_candidates(self, reader, img, scale_back, pass_name, offset=(0, 0)):
        results = reader.readtext(img, detail=1, paragraph=False, decoder="greedy", allowlist="0123456789OoIlS")
        out = []
        for result in results:
            if len(result) < 3:
                continue
            box, raw, conf = result[0], str(result[1]), float(result[2])
            normalized = self.normalize_text(raw)
            nums = re.findall(r"\d{4}", normalized)
            if not nums:
                continue
            try:
                cx, cy, bw, bh = self.box_info(box)
            except Exception:
                continue
            # 원본 working_cv 좌표로 환산
            ox, oy = offset
            cx = cx / scale_back + ox
            cy = cy / scale_back + oy
            bw /= scale_back
            bh /= scale_back
            box_orig = [[float(p[0])/scale_back + ox, float(p[1])/scale_back + oy] for p in box]
            for n in nums:
                v = int(n)
                if not (AUTO_MIN_VALUE <= v <= AUTO_MAX_VALUE):
                    continue
                out.append({"value":v, "confidence":conf, "x":cx, "y":cy, "w":bw, "h":bh,
                            "box":box_orig, "raw":raw, "pass":pass_name})
        return out

    @staticmethod
    def dedupe_candidates(items):
        # 같은 숫자/거의 같은 위치의 두 OCR pass 중 더 좋은 것만 유지
        kept = []
        for it in sorted(items, key=lambda z: (z["confidence"], z["h"]), reverse=True):
            dup = False
            for k in kept:
                d = math.hypot(it["x"]-k["x"], it["y"]-k["y"])
                if d < max(12.0, min(it["h"], k["h"])*0.8) and it["value"] == k["value"]:
                    dup = True
                    break
            if not dup:
                kept.append(it)
        return kept

    def infer_grid_and_assign(self, candidates):
        """
        열(측량점)은 ROI를 정확히 5등분해서 고정한다.
        행(1~N줄)은 ROI를 균등분할하지 않고, 손글씨 OCR 후보들의 Y좌표를 군집화하여
        실제 실측 숫자가 놓인 가로 라인을 따라간다.
        """
        if not self.roi:
            raise RuntimeError("실측영역이 지정되지 않았습니다.")

        x1, y1, x2, y2 = self.roi
        rw, rh = x2-x1, y2-y1

        col_edges = [x1 + rw*i/COLS for i in range(COLS+1)]
        col_centers = [(col_edges[i]+col_edges[i+1])/2.0 for i in range(COLS)]

        core = [it for it in candidates if x1 <= it["x"] <= x2 and y1 <= it["y"] <= y2]
        heights = sorted(it["h"] for it in core if it["h"] > 0)
        med_h = heights[len(heights)//2] if heights else max(1.0, rh/self.rows*0.18)

        # 손글씨 후보: 4자리 실측값 + 상대적으로 큰 글자 위주.
        # 인쇄된 600/358 등의 작은 치수는 행 중심 계산에서 제외한다.
        handwriting = []
        for it in core:
            sval = str(it["value"]).strip()
            if len(sval) == 4 and it["h"] >= med_h*0.80:
                handwriting.append(it)

        # 충분한 손글씨 후보가 있으면 실제 Y 위치로 N개 행 중심을 계산한다.
        ys = [it["y"] for it in handwriting]
        detected_rows = self.cluster_1d(ys, self.rows) if len(ys) >= self.rows else None

        if detected_rows and len(detected_rows) == self.rows:
            row_centers = sorted(detected_rows)
        else:
            # OCR이 너무 부족한 경우에만 ROI 균등분할을 fallback으로 사용
            row_centers = [y1 + rh*(i+0.5)/self.rows for i in range(self.rows)]

        # 행 경계는 인접한 실제 행 중심의 중간점
        row_edges = [y1]
        for i in range(self.rows-1):
            row_edges.append((row_centers[i]+row_centers[i+1])/2.0)
        row_edges.append(y2)

        cells = [self.empty_cell() for _ in range(self.total)]
        best_scores = [-1e9]*self.total

        for it in core:
            sval = str(it["value"]).strip()

            # CAD에 쓸 실측값은 우선 4자리 숫자만 배치.
            # 3자리 인쇄 치수(600 등)와 5자리 오인식은 표 자동입력에서 제외.
            if len(sval) != 4:
                continue

            # X는 고정 5열 중 실제 포함된 열로 결정
            c = int((it["x"]-x1)/max(1e-9, rw)*COLS)
            c = max(0, min(COLS-1, c))

            # Y는 '균등 칸'이 아니라 가장 가까운 실제 실측 행 중심으로 결정
            r = min(range(self.rows), key=lambda k: abs(it["y"]-row_centers[k]))

            left, right = col_edges[c], col_edges[c+1]
            cell_w = max(1.0, right-left)

            # 인접 행 간격의 약 42%를 넘게 벗어나면 억지 배치하지 않음
            if self.rows > 1:
                neighbor_gaps = []
                if r > 0:
                    neighbor_gaps.append(row_centers[r]-row_centers[r-1])
                if r < self.rows-1:
                    neighbor_gaps.append(row_centers[r+1]-row_centers[r])
                row_tol = max(12.0, min(neighbor_gaps)*0.42) if neighbor_gaps else rh/self.rows*0.42
            else:
                row_tol = rh*0.42

            dy_abs = abs(it["y"]-row_centers[r])
            if dy_abs > row_tol:
                continue

            dx = abs(it["x"]-col_centers[c])/(cell_w/2.0)
            dy = dy_abs/max(1.0, row_tol)
            size_score = min(1.8, it["h"]/max(1.0, med_h))
            conf_score = max(0.0, min(1.0, it["confidence"]))
            pos_score = max(0.0, 1.0 - 0.35*dx*dx - 0.85*dy*dy)
            score = 1.45*pos_score + 1.00*size_score + 0.55*conf_score

            idx = c*self.rows+r
            if score > best_scores[idx]:
                best_scores[idx] = score
                status = "자동 인식" if conf_score >= 0.55 and score >= 2.10 else "확인 필요"
                cells[idx] = {
                    "value": sval,
                    "confidence": it["confidence"],
                    "status": status,
                    "box": it["box"],       # 실제 OCR 숫자의 박스를 그대로 보존
                    "source": it["raw"]
                }

        return cells, col_centers, row_centers

    def run_ocr(self):
        if self.working_cv is None:
            messagebox.showwarning("확인", "먼저 실측사진을 불러오세요.")
            return
        if not OCR_AVAILABLE:
            p = self.save_error_log(OCR_IMPORT_ERROR)
            messagebox.showerror("OCR 오류", f"OCR 엔진을 불러오지 못했습니다.\n\n상세 오류: {p or '-'}")
            return
        try:
            self.title("교량 실측 CAD 자동작성 - 숫자 인식 중...")
            if not self.roi:
                messagebox.showwarning("실측영역 필요", "먼저 [실측영역 지정]을 눌러 거더 내측의 손글씨 실측부만 사각형으로 지정하세요.")
                return
            self.status_var.set(f"지정한 실측영역 안에서 손글씨 후보를 찾아 5×{self.rows} 표에 배치하고 있습니다...")
            self.progress.start(10)
            self.update_idletasks()
            reader = self.get_reader()
            color, enhanced, scale, offset = self.prepare_ocr_images()
            candidates = []
            candidates += self.collect_candidates(reader, color, scale, "원본", offset)
            candidates += self.collect_candidates(reader, enhanced, scale, "강조", offset)
            candidates = self.dedupe_candidates(candidates)
            self.cells, self.col_centers, self.row_centers = self.infer_grid_and_assign(candidates)
            self.refresh_grid()
            self.redraw_image()
            done = sum(1 for x in self.cells if x["value"])
            messagebox.showinfo(
                "OCR 완료",
                f"5개 측량점 × {self.rows}줄 = 총 {self.total}칸 중 {done}칸에 숫자 후보를 배치했습니다.\n\n"
                "빈칸은 사진을 보고 직접 입력하세요.\n"
                "자동 입력된 값도 반드시 원본과 대조하세요.\n\n"
                "표의 칸을 클릭하면 사진의 해당 위치를 확대해서 볼 수 있습니다."
            )
        except Exception as e:
            p = self.save_error_log(traceback.format_exc())
            messagebox.showerror("OCR 실행 오류", f"OCR 처리 중 오류가 발생했습니다.\n\n{e}\n\n상세 오류: {p or '-'}")
        finally:
            self.progress.stop()
            self.title("교량 실측 CAD 자동작성")

    # --------------------------------------------------------- 표 선택/편집
    def tree_cell_from_event(self, event):
        row_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)
        if not row_id or not col_id:
            return None
        try:
            r = int(row_id[1:])
            col_num = int(col_id[1:])
        except Exception:
            return None
        if col_num < 2 or col_num > 6:
            return None
        c = col_num - 2
        return r, c, c*self.rows+r, col_id

    def on_tree_click(self, event):
        info = self.tree_cell_from_event(event)
        if not info:
            return
        r, c, idx, _ = info
        cell = self.cells[idx]
        conf = f"{cell['confidence']*100:.0f}%" if cell["confidence"] else "-"
        self.detail_var.set(f"측량점 {c+1} / {r+1}줄  |  값: {cell['value'] or '(빈칸)'}  |  인식률: {conf}  |  상태: {cell['status']}")
        self.focus_cell(idx)

    def focus_cell(self, idx):
        if self.working_cv is None:
            return
        cell = self.cells[idx]
        if cell.get("box"):
            xs = [p[0] for p in cell["box"]]; ys = [p[1] for p in cell["box"]]
            tx, ty = sum(xs)/len(xs), sum(ys)/len(ys)
        elif self.col_centers is not None and self.row_centers is not None:
            c, r = idx//self.rows, idx%self.rows
            tx, ty = self.col_centers[c], self.row_centers[r]
        else:
            self.redraw_image(idx)
            return
        self.zoom = max(self.zoom, 2.2)
        scale = self.current_scale()
        cw, ch = self.image_canvas.winfo_width(), self.image_canvas.winfo_height()
        h, w = self.working_cv.shape[:2]
        # 원본 좌표 tx,ty가 캔버스 중앙에 오도록 이동
        self.offset_x = -(tx - w/2) * scale
        self.offset_y = -(ty - h/2) * scale
        self.redraw_image(idx)

    def edit_cell(self, event):
        info = self.tree_cell_from_event(event)
        if not info:
            return
        r, c, idx, col_id = info
        row_id = f"r{r}"
        bbox = self.tree.bbox(row_id, col_id)
        if not bbox:
            return
        x, y, width, height = bbox
        old = str(self.cells[idx]["value"])
        entry = ttk.Entry(self.tree)
        entry.place(x=x, y=y, width=width, height=height)
        entry.insert(0, old)
        entry.focus_set(); entry.select_range(0, "end")
        state = {"done": False}

        def save(_=None):
            if state["done"]:
                return
            value = entry.get().strip()
            if value and not re.fullmatch(r"\d+(?:\.\d+)?", value):
                messagebox.showwarning("입력 오류", "실측값은 숫자로 입력하세요.")
                entry.focus_set(); return
            state["done"] = True
            self.cells[idx]["value"] = value
            self.cells[idx]["confidence"] = 0.0
            self.cells[idx]["status"] = "사용자 확인" if value else "확인 필요"
            entry.destroy()
            self.refresh_grid()
            self.focus_cell(idx)

        entry.bind("<Return>", save)
        entry.bind("<FocusOut>", save)
        entry.bind("<Escape>", lambda e: entry.destroy())
        self.focus_cell(idx)

    # --------------------------------------------------------- CSV
    def save_csv(self):
        values = []
        # CADian 입력 순서: 측량점 1의 1~6줄, 측량점2의 1~6줄 ...
        for c in range(COLS):
            for r in range(self.rows):
                idx = c*self.rows+r
                value = str(self.cells[idx]["value"]).strip()
                if not value:
                    messagebox.showwarning("빈칸 확인", f"측량점 {c+1} / {r+1}줄이 비어 있습니다.\n\n사진과 대조하여 {self.total}개 값을 모두 확인한 후 저장해주세요.")
                    self.focus_cell(idx)
                    return
                try:
                    if float(value) <= 0:
                        raise ValueError
                except Exception:
                    messagebox.showwarning("실측값 오류", f"측량점 {c+1} / {r+1}줄 값이 올바르지 않습니다: {value}")
                    return
                values.append(value)

        path = filedialog.asksaveasfilename(
            title="CADian용 실측값 CSV 저장", defaultextension=".csv", initialfile="실측값.csv",
            filetypes=[("CSV 파일", "*.csv")]
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="ascii") as f:
                writer = csv.writer(f)
                for i, value in enumerate(values, 1):
                    writer.writerow([i, value])
        except Exception as e:
            messagebox.showerror("CSV 저장 오류", str(e)); return
        messagebox.showinfo("저장 완료", f"{self.total}개 실측값을 CADian용 CSV로 저장했습니다.\n\n{path}\n\nCADian에서 MEASUREAUTO를 실행하세요.")


if __name__ == "__main__":
    app = BridgeMeasureApp()
    app.mainloop()
