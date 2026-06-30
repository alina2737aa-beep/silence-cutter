"""
批量重命名工具 - 独立版
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import platform, re
from pathlib import Path

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

BG_MAIN    = "#eaf2ff"
BG_CARD    = "#ffffff"
BG_LIST    = "#f0f6ff"
ACCENT     = "#1a6fd4"
ACCENT_HOV = "#1558b0"
BORDER     = "#90bef0"
TEXT_MAIN  = "#0d2a4a"
TEXT_GRAY  = "#5a7fa8"

IS_MAC = platform.system() == "Darwin"


def natural_sort_key(filename):
    """自然排序：数字部分按数值比较，而非字符串比较"""
    parts = re.split(r'(\d+)', filename)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("批量重命名工具")
        self.geometry("760x640")
        self.minsize(700, 560)
        self.configure(bg=BG_MAIN)

        self._folder = None
        self._files = []

        self._build_ui()

    def _build_ui(self):
        # 标题栏
        title_bar = ctk.CTkFrame(self, fg_color=ACCENT, corner_radius=0, height=72)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)
        ctk.CTkLabel(title_bar, text="📝  批量重命名工具",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color="#ffffff").pack(side="left", padx=24, pady=16)
        ctk.CTkLabel(title_bar, text="按自然顺序排序 · 一一对应重命名",
                     font=ctk.CTkFont(size=12),
                     text_color="#d0e8ff").pack(side="right", padx=24)

        # 主体
        body = ctk.CTkFrame(self, fg_color=BG_MAIN)
        body.pack(fill="both", expand=True, padx=20, pady=16)

        # 顶部操作行
        top_row = ctk.CTkFrame(body, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 10))
        ctk.CTkButton(top_row, text="📂 选择文件夹", height=34,
                      fg_color=ACCENT, hover_color=ACCENT_HOV,
                      command=self._load_folder).pack(side="left")
        self.status_lbl = ctk.CTkLabel(top_row, text="还没有选择文件夹",
                                        text_color=TEXT_GRAY, font=ctk.CTkFont(size=12))
        self.status_lbl.pack(side="left", padx=12)

        ctk.CTkLabel(body,
                     text="左列自动显示文件夹内的文件名（按自然顺序排列），右列粘贴新文件名（一行一个，顺序对应）",
                     font=ctk.CTkFont(size=11), text_color=TEXT_GRAY).pack(anchor="w", pady=(0, 8))

        # 双列区
        cols = ctk.CTkFrame(body, fg_color="transparent")
        cols.pack(fill="both", expand=True, pady=(0, 10))

        left = ctk.CTkFrame(cols, fg_color=BG_CARD, corner_radius=10)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        ctk.CTkLabel(left, text="原文件名", font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT_MAIN).pack(anchor="w", padx=10, pady=(10, 4))
        self.old_box = ctk.CTkTextbox(left, font=ctk.CTkFont(size=12),
                                       fg_color=BG_LIST, text_color=TEXT_MAIN,
                                       border_color=BORDER)
        self.old_box.pack(fill="both", expand=True, padx=8, pady=(0, 10))
        self.old_box.configure(state="disabled")

        right = ctk.CTkFrame(cols, fg_color=BG_CARD, corner_radius=10)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        ctk.CTkLabel(right, text="新文件名（粘贴到这里）",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT_MAIN).pack(anchor="w", padx=10, pady=(10, 4))
        self.new_box = ctk.CTkTextbox(right, font=ctk.CTkFont(size=12),
                                       fg_color="white", text_color=TEXT_MAIN,
                                       border_color=BORDER)
        self.new_box.pack(fill="both", expand=True, padx=8, pady=(0, 10))

        # 底部按钮区
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x")
        ctk.CTkButton(btn_row, text="清空", width=90, height=36,
                      fg_color="gray70", hover_color="gray60",
                      command=self._clear).pack(side="left")
        self.result_lbl = ctk.CTkLabel(btn_row, text="", text_color=TEXT_GRAY,
                                        font=ctk.CTkFont(size=12))
        self.result_lbl.pack(side="left", padx=12)
        ctk.CTkButton(btn_row, text="✅  执行重命名", height=36, width=160,
                      fg_color=ACCENT, hover_color=ACCENT_HOV,
                      font=ctk.CTkFont(size=14, weight="bold"),
                      command=self._execute).pack(side="right")

    # ── 逻辑 ────────────────────────────────────
    def _load_folder(self):
        folder = filedialog.askdirectory(title="选择要重命名文件所在的文件夹")
        if not folder:
            return
        self._reload(folder)

    def _reload(self, folder):
        self._folder = folder
        # 列出所有文件（不限制类型，方便通用使用）
        files = sorted(
            [f for f in Path(folder).iterdir() if f.is_file() and not f.name.startswith(".")],
            key=lambda x: natural_sort_key(x.name)
        )
        self._files = files
        self.old_box.configure(state="normal")
        self.old_box.delete("1.0", "end")
        for f in files:
            self.old_box.insert("end", f.name + "\n")
        self.old_box.configure(state="disabled")
        self.new_box.delete("1.0", "end")
        self.status_lbl.configure(text=f"已加载 {len(files)} 个文件 · {folder}")
        self.result_lbl.configure(text="")

    def _clear(self):
        self.old_box.configure(state="normal")
        self.old_box.delete("1.0", "end")
        self.old_box.configure(state="disabled")
        self.new_box.delete("1.0", "end")
        self._files = []
        self._folder = None
        self.status_lbl.configure(text="还没有选择文件夹")
        self.result_lbl.configure(text="")

    def _execute(self):
        if not self._files:
            messagebox.showwarning("提示", "请先选择文件夹！")
            return
        raw = self.new_box.get("1.0", "end").strip()
        new_names = [n.strip() for n in raw.split("\n") if n.strip()]
        if len(new_names) != len(self._files):
            messagebox.showerror(
                "错误",
                f"文件数量不匹配！\n原文件：{len(self._files)} 个\n新名称：{len(new_names)} 个"
            )
            return

        success, fail = 0, 0
        for old_path, new_name in zip(self._files, new_names):
            if not Path(new_name).suffix:
                new_name = new_name + old_path.suffix
            new_path = old_path.parent / new_name
            try:
                old_path.rename(new_path)
                success += 1
            except Exception:
                fail += 1

        self.result_lbl.configure(text=f"完成！成功 {success} 个，失败 {fail} 个")
        if self._folder:
            self._reload(self._folder)


if __name__ == "__main__":
    app = App()
    app.mainloop()
 
