# -*- coding: utf-8 -*-

import csv
import re
import traceback
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# ============================================================
# OCR 모듈 확인
# ============================================================

OCR_AVAILABLE = False
OCR_ERROR = ""

try:
    import easyocr
    OCR_AVAILABLE = True

except Exception:
    OCR_ERROR = traceback.format_exc()


# ============================================================
# 메인 프로그램
# ============================================================

class App(tk.Tk):

    def __init__(self):

        super().__init__()

        self.title("교량 실측 CAD 자동작성 - 테스트")
        self.geometry("880x650")

        self.image_path = None
        self.reader = None

        self.create_ui()


    # ========================================================
    # UI 생성
    # ========================================================

    def create_ui(self):

        # ----------------------------------------------------
        # 상단 버튼
        # ----------------------------------------------------

        top = ttk.Frame(
            self,
            padding=10
        )

        top.pack(
            fill="x"
        )


        ttk.Button(
            top,
            text="실측사진 불러오기",
            command=self.load_image
        ).pack(
            side="left",
            padx=4
        )


        ttk.Button(
            top,
            text="숫자 자동인식(OCR)",
            command=self.run_ocr
        ).pack(
            side="left",
            padx=4
        )


        ttk.Button(
            top,
            text="행 추가",
            command=self.add_row
        ).pack(
            side="left",
            padx=4
        )


        ttk.Button(
            top,
            text="선택 행 삭제",
            command=self.delete_row
        ).pack(
            side="left",
            padx=4
        )


        ttk.Button(
            top,
            text="CSV 저장",
            command=self.save_csv
        ).pack(
            side="right",
            padx=4
        )


        # ----------------------------------------------------
        # 사용 순서
        # ----------------------------------------------------

        info = ttk.LabelFrame(
            self,
            text="사용 순서",
            padding=10
        )

        info.pack(
            fill="x",
            padx=10,
            pady=(0, 10)
        )


        ttk.Label(
            info,
            text=(
                "1) 사진 불러오기 → "
                "2) OCR → "
                "3) 표에서 오류/빈칸 수정 → "
                "4) CSV 저장 → "
                "5) CADian에서 MEASUREAUTO 실행"
            )
        ).pack(
            anchor="w"
        )


        # ----------------------------------------------------
        # 선택된 사진 표시
        # ----------------------------------------------------

        self.path_var = tk.StringVar(
            value="사진: 선택 안 됨"
        )


        ttk.Label(
            self,
            textvariable=self.path_var,
            padding=(12, 0)
        ).pack(
            anchor="w"
        )


        # ----------------------------------------------------
        # 표
        # ----------------------------------------------------

        frame = ttk.Frame(
            self,
            padding=10
        )

        frame.pack(
            fill="both",
            expand=True
        )


        self.tree = ttk.Treeview(
            frame,
            columns=(
                "no",
                "value",
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
            "status",
            text="상태"
        )


        self.tree.column(
            "no",
            width=100,
            anchor="center"
        )


        self.tree.column(
            "value",
            width=250,
            anchor="center"
        )


        self.tree.column(
            "status",
            width=300,
            anchor="center"
        )


        self.tree.pack(
            side="left",
            fill="both",
            expand=True
        )


        self.tree.bind(
            "<Double-1>",
            self.edit_cell
        )


        scrollbar = ttk.Scrollbar(
            frame,
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


        # ----------------------------------------------------
        # 하단 안내
        # ----------------------------------------------------

        ttk.Label(
            self,
            text=(
                "※ OCR은 보조 기능입니다. "
                "CAD 적용 전 반드시 실측지와 숫자를 대조하세요. "
                "실측값은 더블클릭해서 수정할 수 있습니다."
            ),
            padding=10
        ).pack(
            fill="x"
        )


    # ========================================================
    # 오류 로그 저장
    # ========================================================

    def save_error_log(self, error_text):

        possible_paths = []


        # 바탕화면
        try:

            desktop = Path.home() / "Desktop"

            possible_paths.append(
                desktop / "ocr_error.txt"
            )

        except Exception:
            pass


        # EXE 실행 폴더
        try:

            if getattr(
                sys,
                "frozen",
                False
            ):

                exe_folder = Path(
                    sys.executable
                ).parent

            else:

                exe_folder = Path(
                    __file__
                ).resolve().parent


            possible_paths.append(
                exe_folder / "ocr_error.txt"
            )

        except Exception:
            pass


        # 사용자 홈
        try:

            possible_paths.append(
                Path.home() / "ocr_error.txt"
            )

        except Exception:
            pass


        for path in possible_paths:

            try:

                path.parent.mkdir(
                    parents=True,
                    exist_ok=True
                )


                with open(
                    path,
                    "w",
                    encoding="utf-8"
                ) as file:

                    file.write(
                        error_text
                    )


                return str(path)

            except Exception:
                continue


        return None


    # ========================================================
    # 사진 선택
    # ========================================================

    def load_image(self):

        path = filedialog.askopenfilename(

            title="실측자료 사진 선택",

            filetypes=[

                (
                    "Image files",
                    "*.png *.jpg *.jpeg *.bmp *.webp"
                ),

                (
                    "All files",
                    "*.*"
                )

            ]

        )


        if not path:
            return


        self.image_path = path


        self.path_var.set(
            f"사진: {path}"
        )


    # ========================================================
    # OCR 실행
    # ========================================================

    def run_ocr(self):

        # ----------------------------------------------------
        # 사진 확인
        # ----------------------------------------------------

        if not self.image_path:

            messagebox.showwarning(
                "확인",
                "먼저 실측사진을 불러오세요."
            )

            return


        # ----------------------------------------------------
        # EasyOCR import 확인
        # ----------------------------------------------------

        if not OCR_AVAILABLE:

            error_file = self.save_error_log(
                OCR_ERROR
            )


            message = (
                "OCR 엔진을 불러오지 못했습니다."
            )


            if error_file:

                message += (
                    "\n\n오류 기록을 저장했습니다.\n"
                    + error_file
                )


            messagebox.showerror(
                "OCR 모듈 오류",
                message
            )

            return


        try:

            # ------------------------------------------------
            # OCR Reader 초기화
            # ------------------------------------------------

            if self.reader is None:

                self.title(
                    "교량 실측 CAD 자동작성 - OCR 준비 중..."
                )


                self.update_idletasks()


                self.reader = easyocr.Reader(
                    ["en"],
                    gpu=False,
                    verbose=False
                )


            # ------------------------------------------------
            # OCR 시작
            # ------------------------------------------------

            self.title(
                "교량 실측 CAD 자동작성 - 숫자 인식 중..."
            )


            self.update_idletasks()


            result = self.reader.readtext(

                self.image_path,

                detail=1,

                paragraph=False

            )


            # ------------------------------------------------
            # OCR 결과 확인
            # ------------------------------------------------

            candidates = []


            for item in result:

                # EasyOCR 결과는 보통
                # [좌표, 문자, 신뢰도]
                # 형태이다.

                if len(item) < 3:
                    continue


                box = item[0]

                text = str(
                    item[1]
                )


                try:

                    confidence = float(
                        item[2]
                    )

                except Exception:

                    confidence = 0.0


                # 쉼표와 공백 제거
                cleaned = (
                    text
                    .replace(",", "")
                    .replace(" ", "")
                )


                # ------------------------------------------------
                # 3~5자리 숫자 후보
                # ------------------------------------------------

                numbers = re.findall(
                    r"(?<!\d)\d{3,5}(?!\d)",
                    cleaned
                )


                for number in numbers:

                    candidates.append(

                        (
                            int(number),
                            confidence
                        )

                    )


            # ------------------------------------------------
            # 기존 표 초기화
            # ------------------------------------------------

            children = self.tree.get_children()


            if children:

                self.tree.delete(
                    *children
                )


            # ------------------------------------------------
            # 숫자를 못 찾았을 때
            # ------------------------------------------------

            if not candidates:

                self.add_row()


                messagebox.showinfo(
                    "OCR 결과",
                    (
                        "자동으로 확인할 수 있는 실측 숫자를 "
                        "찾지 못했습니다.\n\n"
                        "필요한 값을 직접 입력해주세요."
                    )
                )

                return


            # ------------------------------------------------
            # 표에 결과 표시
            # ------------------------------------------------

            for index, data in enumerate(
                candidates,
                1
            ):

                value = data[0]

                confidence = data[1]


                if confidence >= 0.80:

                    status = "자동 인식"


                elif confidence >= 0.60:

                    status = "확인 권장"


                else:

                    status = "확인 필요"


                self.tree.insert(

                    "",

                    "end",

                    values=(

                        index,

                        value,

                        status

                    )

                )


            messagebox.showinfo(

                "OCR 완료",

                (
                    f"{len(candidates)}개의 "
                    "숫자 후보를 찾았습니다.\n\n"
                    "실측자료와 비교해서 값을 확인해주세요."
                )

            )


        # ----------------------------------------------------
        # 오류 발생
        # ----------------------------------------------------

        except Exception as e:

            error_text = traceback.format_exc()


            error_file = self.save_error_log(
                error_text
            )


            message = (
                "OCR 처리 중 오류가 발생했습니다.\n\n"
                + str(e)
            )


            if error_file:

                message += (
                    "\n\n상세 오류 기록을 저장했습니다:\n"
                    + error_file
                )


            else:

                message += (
                    "\n\n오류 로그 파일을 저장하지 못했습니다."
                )


            messagebox.showerror(
                "OCR 실행 오류",
                message
            )


        # ----------------------------------------------------
        # 프로그램 제목 복구
        # ----------------------------------------------------

        finally:

            self.title(
                "교량 실측 CAD 자동작성 - 테스트"
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

                "직접 입력"

            )

        )


    # ========================================================
    # 선택 행 삭제
    # ========================================================

    def delete_row(self):

        selection = self.tree.selection()


        for item in selection:

            self.tree.delete(
                item
            )


        self.renumber()


    # ========================================================
    # 순서 다시 지정
    # ========================================================

    def renumber(self):

        items = self.tree.get_children()


        for index, item in enumerate(
            items,
            1
        ):

            values = list(

                self.tree.item(
                    item,
                    "values"
                )

            )


            if len(values) < 3:

                continue


            values[0] = index


            self.tree.item(
                item,
                values=values
            )


    # ========================================================
    # 실측값 수정
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


        # 실측값 열만 수정 가능
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


        saved = {
            "done": False
        }


        def save_value(event=None):

            if saved["done"]:
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


            saved["done"] = True


            self.tree.set(
                row,
                "value",
                value
            )


            self.tree.set(
                row,
                "status",
                "검토/수정"
            )


            entry.destroy()


        entry.bind(
            "<Return>",
            save_value
        )


        entry.bind(
            "<FocusOut>",
            save_value
        )


    # ========================================================
    # CSV 저장
    # ========================================================

    def save_csv(self):

        rows = []


        # ----------------------------------------------------
        # 표 읽기
        # ----------------------------------------------------

        for item in self.tree.get_children():

            value = str(

                self.tree.set(
                    item,
                    "value"
                )

            ).strip()


            # 빈칸
            if not value:

                messagebox.showwarning(
                    "빈칸",
                    (
                        "빈 실측값이 있습니다.\n\n"
                        "모든 값을 확인한 후 저장해주세요."
                    )
                )

                return


            # 숫자 확인
            try:

                number = float(
                    value
                )


                if number <= 0:

                    raise ValueError


            except Exception:

                messagebox.showwarning(
                    "입력 오류",
                    f"잘못된 실측값이 있습니다: {value}"
                )

                return


            rows.append(
                value
            )


        # ----------------------------------------------------
        # 최소 개수 확인
        # ----------------------------------------------------

        if len(rows) < 2:

            messagebox.showwarning(
                "확인",
                "실측값을 2개 이상 입력하세요."
            )

            return


        # ----------------------------------------------------
        # 저장 위치
        # ----------------------------------------------------

        path = filedialog.asksaveasfilename(

            title="CADian용 실측값 CSV 저장",

            defaultextension=".csv",

            initialfile="실측값.csv",

            filetypes=[

                (
                    "CSV",
                    "*.csv"
                )

            ]

        )


        if not path:
            return


        # ----------------------------------------------------
        # CSV 작성
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # 완료
        # ----------------------------------------------------

        messagebox.showinfo(

            "저장 완료",

            (
                "실측값 CSV 저장이 완료되었습니다.\n\n"
                f"{path}\n\n"
                "CADian에서 MEASUREAUTO를 실행하세요."
            )

        )


# ============================================================
# 프로그램 시작
# ============================================================

if __name__ == "__main__":

    app = App()

    app.mainloop()
