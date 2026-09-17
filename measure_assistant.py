# -*- coding: utf-8 -*-

import csv
import os
import re
import sys
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ============================================================
# 외부 모듈
# ============================================================

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


# ============================================================
# 프로그램
# ============================================================

class BridgeMeasureApp(tk.Tk):

    def __init__(self):

        super().__init__()

        self.title("교량 실측 CAD 자동작성")
        self.geometry("1400x820")
        self.minsize(1100, 650)

        self.image_path = None

        self.original_cv = None
        self.working_cv = None

        self.preview_photo = None

        self.reader = None

        self.ocr_items = []

        self.create_ui()


    # ========================================================
    # UI
    # ========================================================

    def create_ui(self):

        # ----------------------------------------------------
        # 상단 버튼
        # ----------------------------------------------------

        toolbar = ttk.Frame(
            self,
            padding=8
        )

        toolbar.pack(
            fill="x"
        )


        ttk.Button(
            toolbar,
            text="실측사진 불러오기",
            command=self.load_image
        ).pack(
            side="left",
            padx=3
        )


        ttk.Button(
            toolbar,
            text="왼쪽 90°",
            command=lambda: self.rotate_image(90)
        ).pack(
            side="left",
            padx=3
        )


        ttk.Button(
            toolbar,
            text="오른쪽 90°",
            command=lambda: self.rotate_image(-90)
        ).pack(
            side="left",
            padx=3
        )


        ttk.Button(
            toolbar,
            text="180°",
            command=lambda: self.rotate_image(180)
        ).pack(
            side="left",
            padx=3
        )


        ttk.Separator(
            toolbar,
            orient="vertical"
        ).pack(
            side="left",
            fill="y",
            padx=8
        )


        ttk.Button(
            toolbar,
            text="숫자 자동인식(OCR)",
            command=self.run_ocr
        ).pack(
            side="left",
            padx=3
        )


        ttk.Button(
            toolbar,
            text="행 추가",
            command=self.add_row
        ).pack(
            side="left",
            padx=3
        )


        ttk.Button(
            toolbar,
            text="선택 행 삭제",
            command=self.delete_selected_rows
        ).pack(
            side="left",
            padx=3
        )


        ttk.Button(
            toolbar,
            text="CSV 저장",
            command=self.save_csv
        ).pack(
            side="right",
            padx=3
        )


        # ----------------------------------------------------
        # 안내
        # ----------------------------------------------------

        guide = ttk.LabelFrame(
            self,
            text="사용 순서",
            padding=7
        )

        guide.pack(
            fill="x",
            padx=8,
            pady=(0, 5)
        )


        ttk.Label(
            guide,
            text=(
                "1) 실측사진 불러오기  →  "
                "2) 사진 방향 확인/회전  →  "
                "3) 숫자 자동인식  →  "
                "4) 사진과 표 대조  →  "
                "5) 오류/빈칸 수정  →  "
                "6) CSV 저장  →  "
                "7) CADian에서 MEASUREAUTO 실행"
            )
        ).pack(
            anchor="w"
        )


        self.status_var = tk.StringVar(
            value="실측사진을 불러오세요."
        )


        ttk.Label(
            self,
            textvariable=self.status_var,
            padding=(10, 4)
        ).pack(
            fill="x"
        )


        # ----------------------------------------------------
        # 좌/우 분할
        # ----------------------------------------------------

        self.paned = ttk.Panedwindow(
            self,
            orient="horizontal"
        )

        self.paned.pack(
            fill="both",
            expand=True,
            padx=8,
            pady=5
        )


        # ====================================================
        # 왼쪽 : 실측사진
        # ====================================================

        left = ttk.LabelFrame(
            self.paned,
            text="실측자료 사진",
            padding=5
        )


        self.paned.add(
            left,
            weight=3
        )


        self.image_canvas = tk.Canvas(
            left,
            background="#333333",
            highlightthickness=0
        )


        self.image_canvas.pack(
            fill="both",
            expand=True
        )


        self.image_canvas.bind(
            "<Configure>",
            lambda event: self.show_preview()
        )


        # ====================================================
        # 오른쪽 : OCR 결과
        # ====================================================

        right = ttk.LabelFrame(
            self.paned,
            text="자동 인식 실측값 - 반드시 검토",
            padding=5
        )


        self.paned.add(
            right,
            weight=2
        )


        tree_frame = ttk.Frame(
            right
        )

        tree_frame.pack(
            fill="both",
            expand=True
        )


        self.tree = ttk.Treeview(

            tree_frame,

            columns=(
                "no",
                "value",
                "confidence",
                "status"
            ),

            show="headings",

            selectmode="extended"

        )


        self.tree.heading(
            "no",
            text="순서"
        )

        self.tree.heading(
            "value",
            text="실측값"
        )

        self.tree.heading(
            "confidence",
            text="인식률"
        )

        self.tree.heading(
            "status",
            text="상태"
        )


        self.tree.column(
            "no",
            width=60,
            anchor="center"
        )

        self.tree.column(
            "value",
            width=120,
            anchor="center"
        )

        self.tree.column(
            "confidence",
            width=80,
            anchor="center"
        )

        self.tree.column(
            "status",
            width=120,
            anchor="center"
        )


        self.tree.pack(
            side="left",
            fill="both",
            expand=True
        )


        scrollbar = ttk.Scrollbar(

            tree_frame,

            orient="vertical",

            command=self.tree.yview

        )


        scrollbar.pack(
            side="right",
            fill="y"
        )


        self.tree.configure(
            yscrollcommand=scrollbar.set
        )


        self.tree.bind(
            "<Double-1>",
            self.edit_cell
        )


        # ----------------------------------------------------
        # 하단 설명
        # ----------------------------------------------------

        bottom = ttk.LabelFrame(
            self,
            text="검토 안내",
            padding=7
        )

        bottom.pack(
            fill="x",
            padx=8,
            pady=(0, 8)
        )


        ttk.Label(
            bottom,
            text=(
                "OCR 결과는 자동 확정하지 않습니다. "
                "손글씨와 인쇄 치수가 함께 있는 경우 잘못 인식될 수 있습니다. "
                "실측값 셀을 더블클릭하면 직접 수정할 수 있습니다. "
                "확실하지 않은 값은 '확인 필요'로 표시됩니다."
            )
        ).pack(
            anchor="w"
        )


    # ========================================================
    # 오류 로그
    # ========================================================

    def save_error_log(self, text):

        paths = []


        try:

            paths.append(
                Path.home() / "Desktop" / "ocr_error.txt"
            )

        except Exception:
            pass


        try:

            if getattr(sys, "frozen", False):

                base = Path(
                    sys.executable
                ).parent

            else:

                base = Path(
                    __file__
                ).resolve().parent


            paths.append(
                base / "ocr_error.txt"
            )

        except Exception:
            pass


        try:

            paths.append(
                Path.home() / "ocr_error.txt"
            )

        except Exception:
            pass


        for path in paths:

            try:

                with open(
                    path,
                    "w",
                    encoding="utf-8"
                ) as f:

                    f.write(text)


                return str(path)

            except Exception:
                pass


        return None


    # ========================================================
    # 이미지 로드
    # ========================================================

    def load_image(self):

        path = filedialog.askopenfilename(

            title="실측자료 사진 선택",

            filetypes=[

                (
                    "사진 파일",
                    "*.jpg *.jpeg *.png *.bmp *.webp"
                ),

                (
                    "모든 파일",
                    "*.*"
                )

            ]

        )


        if not path:
            return


        try:

            # ------------------------------------------------
            # 핵심 수정
            #
            # cv2.imread(path)를 바로 쓰지 않는다.
            # 한글 경로 문제까지 피하기 위해
            # np.fromfile + cv2.imdecode 사용
            # ------------------------------------------------

            file_data = np.fromfile(
                path,
                dtype=np.uint8
            )


            image = cv2.imdecode(
                file_data,
                cv2.IMREAD_COLOR
            )


            if image is None:

                raise RuntimeError(
                    "사진 파일을 읽지 못했습니다."
                )


            self.image_path = path

            self.original_cv = image.copy()

            self.working_cv = image.copy()


            self.status_var.set(
                f"사진: {path}"
            )


            self.show_preview()


        except Exception as e:

            error_text = traceback.format_exc()

            error_file = self.save_error_log(
                error_text
            )


            message = (
                "사진을 불러오는 중 오류가 발생했습니다.\n\n"
                + str(e)
            )


            if error_file:

                message += (
                    "\n\n상세 오류:\n"
                    + error_file
                )


            messagebox.showerror(
                "사진 오류",
                message
            )


    # ========================================================
    # 사진 회전
    # ========================================================

    def rotate_image(self, angle):

        if self.working_cv is None:

            messagebox.showwarning(
                "확인",
                "먼저 실측사진을 불러오세요."
            )

            return


        if angle == 90:

            self.working_cv = cv2.rotate(
                self.working_cv,
                cv2.ROTATE_90_COUNTERCLOCKWISE
            )


        elif angle == -90:

            self.working_cv = cv2.rotate(
                self.working_cv,
                cv2.ROTATE_90_CLOCKWISE
            )


        elif angle == 180:

            self.working_cv = cv2.rotate(
                self.working_cv,
                cv2.ROTATE_180
            )


        self.show_preview()


    # ========================================================
    # 사진 미리보기
    # ========================================================

    def show_preview(self):

        if self.working_cv is None:
            return


        try:

            canvas_width = self.image_canvas.winfo_width()

            canvas_height = self.image_canvas.winfo_height()


            if canvas_width < 50:
                return


            if canvas_height < 50:
                return


            rgb = cv2.cvtColor(
                self.working_cv,
                cv2.COLOR_BGR2RGB
            )


            h, w = rgb.shape[:2]


            scale = min(

                canvas_width / w,

                canvas_height / h

            )


            scale = min(
                scale,
                1.0
            )


            new_width = max(
                1,
                int(w * scale)
            )


            new_height = max(
                1,
                int(h * scale)
            )


            resized = cv2.resize(

                rgb,

                (
                    new_width,
                    new_height
                ),

                interpolation=cv2.INTER_AREA

            )


            pil_image = Image.fromarray(
                resized
            )


            self.preview_photo = ImageTk.PhotoImage(
                pil_image
            )


            self.image_canvas.delete(
                "all"
            )


            self.image_canvas.create_image(

                canvas_width // 2,

                canvas_height // 2,

                image=self.preview_photo,

                anchor="center"

            )


        except Exception:
            pass


    # ========================================================
    # OCR Reader
    # ========================================================

    def get_reader(self):

        if self.reader is not None:

            return self.reader


        self.status_var.set(
            "OCR 엔진을 준비하고 있습니다..."
        )


        self.update_idletasks()


        self.reader = easyocr.Reader(

            ["en"],

            gpu=False,

            verbose=False

        )


        return self.reader


    # ========================================================
    # OCR용 이미지 전처리
    # ========================================================

    def prepare_ocr_image(self):

        if self.working_cv is None:

            raise RuntimeError(
                "사진이 없습니다."
            )


        image = self.working_cv.copy()


        # 너무 큰 사진은 OCR 처리 속도 때문에 축소
        h, w = image.shape[:2]


        max_side = max(
            h,
            w
        )


        if max_side > 3000:

            scale = 3000.0 / max_side


            image = cv2.resize(

                image,

                None,

                fx=scale,

                fy=scale,

                interpolation=cv2.INTER_AREA

            )


        # ----------------------------------------------------
        # EasyOCR에는 파일명이 아니라
        # 정상적인 numpy ndarray를 전달한다.
        # ----------------------------------------------------

        return np.ascontiguousarray(
            image
        )


    # ========================================================
    # OCR
    # ========================================================

    def run_ocr(self):

        if self.working_cv is None:

            messagebox.showwarning(
                "확인",
                "먼저 실측사진을 불러오세요."
            )

            return


        if not OCR_AVAILABLE:

            path = self.save_error_log(
                OCR_IMPORT_ERROR
            )


            message = (
                "OCR 엔진을 불러오지 못했습니다."
            )


            if path:

                message += (
                    "\n\n상세 오류:\n"
                    + path
                )


            messagebox.showerror(
                "OCR 오류",
                message
            )

            return


        try:

            self.title(
                "교량 실측 CAD 자동작성 - 숫자 인식 중..."
            )


            self.status_var.set(
                "사진에서 숫자를 찾고 있습니다..."
            )


            self.update_idletasks()


            reader = self.get_reader()


            image = self.prepare_ocr_image()


            # ------------------------------------------------
            # 중요:
            # 파일 경로가 아니라 OpenCV ndarray 전달
            # ------------------------------------------------

            results = reader.readtext(

                image,

                detail=1,

                paragraph=False,

                decoder="greedy"

            )


            found = []


            # =================================================
            # OCR 결과에서 숫자 + 위치 추출
            # =================================================

            for result in results:

                if len(result) < 3:
                    continue


                box = result[0]

                raw_text = str(
                    result[1]
                ).strip()


                try:

                    confidence = float(
                        result[2]
                    )

                except Exception:

                    confidence = 0.0


                # ------------------------------------------------
                # OCR 흔한 문자 오인식 일부 보정
                #
                # 단, 확정값으로 간주하지 않고
                # 상태에서 사용자 확인을 요구한다.
                # ------------------------------------------------

                normalized = (
                    raw_text
                    .replace(" ", "")
                    .replace(",", "")
                )


                corrected = normalized


                corrected = corrected.replace(
                    "O",
                    "0"
                )

                corrected = corrected.replace(
                    "o",
                    "0"
                )


                # 숫자만 추출
                number_matches = re.findall(

                    r"\d{3,5}",

                    corrected

                )


                if not number_matches:
                    continue


                # 박스 중심좌표
                try:

                    xs = [
                        float(p[0])
                        for p in box
                    ]


                    ys = [
                        float(p[1])
                        for p in box
                    ]


                    center_x = sum(xs) / len(xs)

                    center_y = sum(ys) / len(ys)


                except Exception:

                    center_x = 0

                    center_y = 0


                for number_text in number_matches:

                    try:

                        value = int(
                            number_text
                        )

                    except Exception:

                        continue


                    # --------------------------------------------
                    # 교량 실측값 후보 범위
                    #
                    # 너무 작은 도면 숫자 등을 조금 걸러내기 위한
                    # 1차 필터.
                    #
                    # 최종 확정은 사용자가 한다.
                    # --------------------------------------------

                    if value < 500:

                        continue


                    if value > 99999:

                        continue


                    found.append({

                        "value": value,

                        "confidence": confidence,

                        "x": center_x,

                        "y": center_y,

                        "raw": raw_text

                    })


            # =================================================
            # 위치순 정렬
            # =================================================

            # 현재 버전에서는
            # 위 → 아래, 같은 높이면 왼쪽 → 오른쪽

            found.sort(

                key=lambda item: (

                    round(
                        item["y"] / 40
                    ),

                    item["x"]

                )

            )


            self.ocr_items = found


            # =================================================
            # 표 초기화
            # =================================================

            children = self.tree.get_children()


            if children:

                self.tree.delete(
                    *children
                )


            # =================================================
            # 결과 없음
            # =================================================

            if not found:

                self.add_row()


                self.status_var.set(
                    "자동 인식된 실측값이 없습니다."
                )


                messagebox.showinfo(

                    "OCR 결과",

                    (
                        "자동으로 확인된 숫자가 없습니다.\n\n"
                        "사진 방향을 바꿔 다시 OCR하거나 "
                        "실측값을 직접 입력해주세요."
                    )

                )

                return


            # =================================================
            # 결과 표 입력
            # =================================================

            for index, item in enumerate(
                found,
                1
            ):

                confidence = item[
                    "confidence"
                ]


                # --------------------------------------------
                # 상태 판단
                # --------------------------------------------

                if confidence >= 0.85:

                    status = "자동 인식"


                elif confidence >= 0.65:

                    status = "확인 권장"


                else:

                    status = "확인 필요"


                # OCR 원문에 문자 보정이 있었으면
                # 반드시 확인하도록 한다.

                raw_compact = (
                    item["raw"]
                    .replace(" ", "")
                    .replace(",", "")
                )


                if not raw_compact.isdigit():

                    status = "확인 필요"


                self.tree.insert(

                    "",

                    "end",

                    values=(

                        index,

                        item["value"],

                        f"{confidence * 100:.0f}%",

                        status

                    )

                )


            self.status_var.set(

                f"OCR 완료 - 숫자 후보 {len(found)}개 / 반드시 실측지와 대조하세요."

            )


            messagebox.showinfo(

                "OCR 완료",

                (
                    f"숫자 후보 {len(found)}개를 찾았습니다.\n\n"
                    "현재 단계에서는 인쇄 치수도 함께 인식될 수 있습니다.\n"
                    "오른쪽 표와 왼쪽 실측사진을 비교해서 확인해주세요."
                )

            )


        except Exception as e:

            error_text = traceback.format_exc()


            path = self.save_error_log(
                error_text
            )


            message = (

                "OCR 처리 중 오류가 발생했습니다.\n\n"

                + str(e)

            )


            if path:

                message += (

                    "\n\n상세 오류 기록:\n"

                    + path

                )


            messagebox.showerror(
                "OCR 실행 오류",
                message
            )


        finally:

            self.title(
                "교량 실측 CAD 자동작성"
            )


    # ========================================================
    # 행 추가
    # ========================================================

    def add_row(self):

        number = (
            len(
                self.tree.get_children()
            )
            + 1
        )


        self.tree.insert(

            "",

            "end",

            values=(

                number,

                "",

                "-",

                "직접 입력"

            )

        )


    # ========================================================
    # 행 삭제
    # ========================================================

    def delete_selected_rows(self):

        selection = self.tree.selection()


        for item in selection:

            self.tree.delete(
                item
            )


        self.renumber_rows()


    # ========================================================
    # 번호 재정렬
    # ========================================================

    def renumber_rows(self):

        for index, item in enumerate(
            self.tree.get_children(),
            1
        ):

            values = list(
                self.tree.item(
                    item,
                    "values"
                )
            )


            if len(values) < 4:
                continue


            values[0] = index


            self.tree.item(
                item,
                values=values
            )


    # ========================================================
    # 셀 수정
    # ========================================================

    def edit_cell(self, event):

        region = self.tree.identify(
            "region",
            event.x,
            event.y
        )


        if region != "cell":
            return


        column = self.tree.identify_column(
            event.x
        )


        row = self.tree.identify_row(
            event.y
        )


        if not row:
            return


        # 실측값만 수정
        if column != "#2":
            return


        bbox = self.tree.bbox(
            row,
            column
        )


        if not bbox:
            return


        x, y, width, height = bbox


        old_value = self.tree.set(
            row,
            "value"
        )


        entry = ttk.Entry(
            self.tree
        )


        entry.place(

            x=x,

            y=y,

            width=width,

            height=height

        )


        entry.insert(
            0,
            old_value
        )


        entry.focus_set()


        entry.select_range(
            0,
            "end"
        )


        done = {
            "saved": False
        }


        def save(event=None):

            if done["saved"]:
                return


            value = entry.get().strip()


            if value:

                if not re.fullmatch(
                    r"\d+(?:\.\d+)?",
                    value
                ):

                    messagebox.showwarning(

                        "입력 오류",

                        "실측값은 숫자로 입력하세요."

                    )

                    entry.focus_set()

                    return


            done["saved"] = True


            self.tree.set(
                row,
                "value",
                value
            )


            self.tree.set(
                row,
                "confidence",
                "-"
            )


            self.tree.set(
                row,
                "status",
                "사용자 확인"
            )


            entry.destroy()


        entry.bind(
            "<Return>",
            save
        )


        entry.bind(
            "<FocusOut>",
            save
        )


    # ========================================================
    # CSV 저장
    # ========================================================

    def save_csv(self):

        rows = []


        for item in self.tree.get_children():

            value = str(
                self.tree.set(
                    item,
                    "value"
                )
            ).strip()


            if not value:

                messagebox.showwarning(

                    "빈칸 확인",

                    (
                        "빈 실측값이 있습니다.\n\n"
                        "사진과 대조하여 모든 값을 확인한 후 저장해주세요."
                    )

                )

                return


            try:

                number = float(
                    value
                )


                if number <= 0:

                    raise ValueError


            except Exception:

                messagebox.showwarning(

                    "실측값 오류",

                    f"숫자가 아닌 실측값이 있습니다: {value}"

                )

                return


            rows.append(
                value
            )


        if len(rows) < 1:

            messagebox.showwarning(
                "확인",
                "저장할 실측값이 없습니다."
            )

            return


        path = filedialog.asksaveasfilename(

            title="CADian용 실측값 CSV 저장",

            defaultextension=".csv",

            initialfile="실측값.csv",

            filetypes=[

                (
                    "CSV 파일",
                    "*.csv"
                )

            ]

        )


        if not path:
            return


        try:

            with open(

                path,

                "w",

                newline="",

                encoding="ascii"

            ) as file:


                writer = csv.writer(
                    file
                )


                for index, value in enumerate(
                    rows,
                    1
                ):


                    writer.writerow(

                        [
                            index,
                            value
                        ]

                    )


        except Exception as e:

            messagebox.showerror(

                "CSV 저장 오류",

                str(e)

            )

            return


        messagebox.showinfo(

            "저장 완료",

            (
                "CADian용 실측값 CSV를 저장했습니다.\n\n"
                f"{path}\n\n"
                "CADian에서 MEASUREAUTO를 실행하세요."
            )

        )


# ============================================================
# 시작
# ============================================================

if __name__ == "__main__":

    app = BridgeMeasureApp()

    app.mainloop()
