# -*- coding: utf-8 -*-

import csv
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# EasyOCR을 EXE 환경에서도 정상적으로 찾도록 처리
OCR_AVAILABLE = False
OCR_ERROR = ""

try:
    import easyocr
    OCR_AVAILABLE = True
except Exception as e:
    OCR_ERROR = str(e)


class App(tk.Tk):

    def __init__(self):
        super().__init__()

        self.title("교량 실측 CAD 자동작성 - 테스트")
        self.geometry("820x620")

        self.image_path = None
        self.reader = None

        self.create_ui()


    def create_ui(self):

        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Button(
            top,
            text="실측사진 불러오기",
            command=self.load_image
        ).pack(side="left", padx=4)

        ttk.Button(
            top,
            text="숫자 자동인식(OCR)",
            command=self.run_ocr
        ).pack(side="left", padx=4)

        ttk.Button(
            top,
            text="행 추가",
            command=self.add_row
        ).pack(side="left", padx=4)

        ttk.Button(
            top,
            text="선택 행 삭제",
            command=self.delete_row
        ).pack(side="left", padx=4)

        ttk.Button(
            top,
            text="CSV 저장",
            command=self.save_csv
        ).pack(side="right", padx=4)


        info = ttk.LabelFrame(
            self,
            text="사용 순서",
            padding=10
        )

        info.pack(fill="x", padx=10, pady=(0,10))

        ttk.Label(
            info,
            text=(
                "1) 사진 불러오기 → "
                "2) OCR → "
                "3) 표에서 오류/빈칸 수정 → "
                "4) CSV 저장 → "
                "5) CADian에서 MEASUREAUTO 실행"
            )
        ).pack(anchor="w")


        self.path_var = tk.StringVar(
            value="사진: 선택 안 됨"
        )

        ttk.Label(
            self,
            textvariable=self.path_var,
            padding=(12,0)
        ).pack(anchor="w")


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
            columns=("no","value","status"),
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
            width=80,
            anchor="center"
        )

        self.tree.column(
            "value",
            width=180,
            anchor="center"
        )

        self.tree.column(
            "status",
            width=260,
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


        ttk.Label(
            self,
            text=(
                "※ OCR은 보조 기능입니다. "
                "CAD 적용 전 반드시 실측지와 숫자를 대조하세요. "
                "실측값은 더블클릭해서 수정할 수 있습니다."
            ),
            padding=10
        ).pack(fill="x")


    # -------------------------
    # 사진 선택
    # -------------------------

    def load_image(self):

        path = filedialog.askopenfilename(

            title="실측자료 사진 선택",

            filetypes=[
                (
                    "Image",
                    "*.png *.jpg *.jpeg *.bmp *.webp"
                ),
                (
                    "All files",
                    "*.*"
                )
            ]
        )

        if path:

            self.image_path = path

            self.path_var.set(
                f"사진: {path}"
            )


    # -------------------------
    # OCR
    # -------------------------

    def run_ocr(self):

        if not self.image_path:

            messagebox.showwarning(
                "확인",
                "먼저 실측사진을 불러오세요."
            )

            return


        if not OCR_AVAILABLE:

            messagebox.showerror(
                "OCR 오류",
                "OCR 엔진을 불러오지 못했습니다.\n\n"
                + OCR_ERROR
            )

            return


        try:

            # 처음 OCR할 때만 로딩
            if self.reader is None:

                self.title(
                    "교량 실측 CAD 자동작성 - OCR 준비 중..."
                )

                self.update()

                self.reader = easyocr.Reader(
                    ['en'],
                    gpu=False
                )


            self.title(
                "교량 실측 CAD 자동작성 - 숫자 인식 중..."
            )

            self.update()


            result = self.reader.readtext(
                self.image_path,
                detail=1,
                paragraph=False
            )


            candidates = []


            for box, text, confidence in result:

                cleaned = (
                    text
                    .replace(",", "")
                    .replace(" ", "")
                )


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


            self.tree.delete(
                *self.tree.get_children()
            )


            if not candidates:

                self.add_row()

                messagebox.showinfo(
                    "OCR 결과",
                    "숫자를 찾지 못했습니다.\n"
                    "필요한 값을 직접 입력해주세요."
                )

                return


            for index, data in enumerate(
                candidates,
                1
            ):

                value = data[0]
                confidence = data[1]


                if confidence < 0.65:

                    status = "확인 필요"

                else:

                    status = "자동 인식"


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
                f"{len(candidates)}개의 숫자 후보를 찾았습니다.\n\n"
                "실측자료와 비교해서 값을 확인해주세요."
            )


        except Exception as e:

            messagebox.showerror(
                "OCR 실행 오류",
                str(e)
            )


        finally:

            self.title(
                "교량 실측 CAD 자동작성 - 테스트"
            )


    # -------------------------
    # 행 추가
    # -------------------------

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


    # -------------------------
    # 행 삭제
    # -------------------------

    def delete_row(self):

        for item in self.tree.selection():

            self.tree.delete(item)


        self.renumber()


    # -------------------------
    # 번호 재정렬
    # -------------------------

    def renumber(self):

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

            values[0] = index

            self.tree.item(
                item,
                values=values
            )


    # -------------------------
    # 값 수정
    # -------------------------

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


        if column != "#2":
            return


        x, y, width, height = self.tree.bbox(
            row,
            column
        )


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


        def save_value(event=None):

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

                    return


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


    # -------------------------
    # CSV 저장
    # -------------------------

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
                    "빈칸",
                    "빈 실측값이 있습니다."
                )

                return


            try:

                number = float(value)

                if number <= 0:

                    raise ValueError


            except:

                messagebox.showwarning(
                    "입력 오류",
                    f"잘못된 실측값: {value}"
                )

                return


            rows.append(value)


        if len(rows) < 2:

            messagebox.showwarning(
                "확인",
                "실측값을 2개 이상 입력하세요."
            )

            return


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


        with open(
            path,
            "w",
            newline="",
            encoding="ascii"
        ) as file:

            writer = csv.writer(file)


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


        messagebox.showinfo(
            "저장 완료",
            "실측값 CSV 저장이 완료되었습니다.\n\n"
            "CADian에서 MEASUREAUTO를 실행하세요."
        )


if __name__ == "__main__":

    app = App()

    app.mainloop()
