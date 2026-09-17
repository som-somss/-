# -*- coding: utf-8 -*-
"""
CADian 2023 실측자료 보조 프로그램 - 테스트 버전
- 실측사진 불러오기
- OCR로 3~5자리 숫자 후보 추출 (EasyOCR 설치 시)
- 값 검토/수정/추가/삭제
- CADian LISP가 읽을 CSV 저장

실행: python measure_assistant.py
"""
import csv
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("교량 실측 CAD 자동작성 - 테스트")
        self.geometry("820x620")
        self.image_path = None
        self.values = []
        self._build()

    def _build(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Button(top, text="실측사진 불러오기", command=self.load_image).pack(side="left", padx=4)
        ttk.Button(top, text="숫자 자동인식(OCR)", command=self.run_ocr).pack(side="left", padx=4)
        ttk.Button(top, text="행 추가", command=self.add_row).pack(side="left", padx=4)
        ttk.Button(top, text="선택 행 삭제", command=self.delete_row).pack(side="left", padx=4)
        ttk.Button(top, text="CSV 저장", command=self.save_csv).pack(side="right", padx=4)

        info = ttk.LabelFrame(self, text="사용 순서", padding=10)
        info.pack(fill="x", padx=10, pady=(0,10))
        ttk.Label(
            info,
            text="1) 사진 불러오기 → 2) OCR → 3) 표에서 오류/빈칸 수정 → "
                 "4) CSV 저장 → 5) CADian에서 MEASUREAUTO 실행"
        ).pack(anchor="w")

        self.path_var = tk.StringVar(value="사진: 선택 안 됨")
        ttk.Label(self, textvariable=self.path_var, padding=(12,0)).pack(anchor="w")

        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(frm, columns=("no","value","status"), show="headings", selectmode="extended")
        self.tree.heading("no", text="순서")
        self.tree.heading("value", text="실측값")
        self.tree.heading("status", text="상태")
        self.tree.column("no", width=80, anchor="center")
        self.tree.column("value", width=180, anchor="center")
        self.tree.column("status", width=260, anchor="center")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", self.edit_cell)

        sb = ttk.Scrollbar(frm, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)

        bottom = ttk.Label(
            self,
            text="※ OCR는 보조 기능입니다. CAD 적용 전 반드시 실측지와 숫자를 대조하세요. "
                 "표의 실측값 셀은 더블클릭해서 수정할 수 있습니다.",
            padding=10
        )
        bottom.pack(fill="x")

    def load_image(self):
        p = filedialog.askopenfilename(
            title="실측자료 사진 선택",
            filetypes=[("Image", "*.png *.jpg *.jpeg *.bmp *.webp"), ("All files","*.*")]
        )
        if p:
            self.image_path = p
            self.path_var.set(f"사진: {p}")

    def run_ocr(self):
        if not self.image_path:
            messagebox.showwarning("확인", "먼저 실측사진을 불러오세요.")
            return
        try:
            import easyocr
        except Exception:
            messagebox.showerror(
                "EasyOCR 필요",
                "OCR 모듈이 설치되어 있지 않습니다.\n\n"
                "명령 프롬프트에서 아래 명령을 한 번 실행하세요:\n"
                "pip install easyocr\n\n"
                "설치 후 프로그램을 다시 실행하면 됩니다."
            )
            return

        try:
            reader = easyocr.Reader(['en'], gpu=False)
            result = reader.readtext(self.image_path, detail=1, paragraph=False)
        except Exception as e:
            messagebox.showerror("OCR 오류", str(e))
            return

        candidates = []
        for box, text, conf in result:
            cleaned = text.replace(",", "").replace(" ", "")
            # 현장 실측값을 주로 3~5자리 정수로 가정
            nums = re.findall(r"(?<!\d)\d{3,5}(?!\d)", cleaned)
            for n in nums:
                candidates.append((int(n), conf))

        self.tree.delete(*self.tree.get_children())
        if not candidates:
            self.add_row()
            messagebox.showinfo("OCR 결과", "확실한 숫자 후보를 찾지 못했습니다. 표에 직접 입력해 주세요.")
            return

        for idx, (val, conf) in enumerate(candidates, 1):
            status = "확인 권장" if conf < 0.65 else "인식"
            self.tree.insert("", "end", values=(idx, val, status))

    def add_row(self):
        n = len(self.tree.get_children()) + 1
        self.tree.insert("", "end", values=(n, "", "직접 입력"))

    def delete_row(self):
        for iid in self.tree.selection():
            self.tree.delete(iid)
        self.renumber()

    def renumber(self):
        for i, iid in enumerate(self.tree.get_children(), 1):
            vals = list(self.tree.item(iid, "values"))
            vals[0] = i
            self.tree.item(iid, values=vals)

    def edit_cell(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        row = self.tree.identify_row(event.y)
        if not row or col != "#2":
            return
        x, y, w, h = self.tree.bbox(row, col)
        old = self.tree.set(row, "value")
        entry = ttk.Entry(self.tree)
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, old)
        entry.focus_set()
        entry.select_range(0, "end")
        def commit(_=None):
            v = entry.get().strip()
            if v and not re.fullmatch(r"\d+(?:\.\d+)?", v):
                messagebox.showwarning("입력 오류", "실측값은 숫자로 입력하세요.")
                return
            self.tree.set(row, "value", v)
            self.tree.set(row, "status", "검토/수정")
            entry.destroy()
        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)

    def save_csv(self):
        rows = []
        for iid in self.tree.get_children():
            v = str(self.tree.set(iid, "value")).strip()
            if not v:
                messagebox.showwarning("빈칸", "빈 실측값이 있습니다. 모두 입력한 뒤 저장하세요.")
                return
            try:
                fv = float(v)
                if fv <= 0:
                    raise ValueError
            except Exception:
                messagebox.showwarning("입력 오류", f"잘못된 실측값: {v}")
                return
            rows.append(v)

        if len(rows) < 2:
            messagebox.showwarning("확인", "실측값을 2개 이상 입력하세요.")
            return

        p = filedialog.asksaveasfilename(
            title="CADian용 실측값 CSV 저장",
            defaultextension=".csv",
            initialfile="실측값.csv",
            filetypes=[("CSV", "*.csv")]
        )
        if not p:
            return

        # CADian AutoLISP에서 한글/인코딩 문제를 피하기 위해 숫자만 ASCII로 저장
        with open(p, "w", newline="", encoding="ascii") as f:
            wr = csv.writer(f)
            for i, v in enumerate(rows, 1):
                wr.writerow([i, v])

        messagebox.showinfo(
            "저장 완료",
            f"CSV 저장 완료:\n{p}\n\n"
            "이제 CADian에서 cadian_measure.lsp를 APPLOAD한 뒤\n"
            "MEASUREAUTO 명령을 실행하세요."
        )

if __name__ == "__main__":
    App().mainloop()
