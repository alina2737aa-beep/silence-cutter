"""
口播去气口工具 v2 - 蓝色系界面 + 按前缀自动分组合并
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False

import subprocess, threading, os, re, sys, platform, tempfile, shutil
from pathlib import Path
from collections import defaultdict

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# 蓝色系配色
BG_MAIN    = "#0d1b2a"
BG_CARD    = "#1b2838"
BG_LIST    = "#162032"
ACCENT     = "#1e6fd9"
ACCENT_HOV = "#2a85f5"
BORDER     = "#2a5fa8"
TEXT_MAIN  = "#cce4ff"
TEXT_GRAY  = "#6a9cc9"
RED        = "#c0392b"
RED_HOV    = "#e74c3c"
GREEN      = "#1a6b4a"
GREEN_HOV  = "#228b5e"

IS_MAC = platform.system() == "Darwin"

# ── FFmpeg 工具函数 ──────────────────────────────

def find_ffmpeg():
    # 同目录下（打包后）
    base = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    for name in ["ffmpeg", "ffmpeg.exe"]:
        p = base / name
        if p.exists():
            return str(p)
    # Homebrew 路径（M1/M2/Intel Mac）
    for p in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
        if Path(p).exists():
            return p
    # 系统 PATH
    return shutil.which("ffmpeg")

def get_duration(ffprobe, path):
    try:
        r = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except:
        return 0.0

def detect_silence(ffmpeg, path, threshold_db, min_duration):
    cmd = [ffmpeg, "-i", str(path),
           "-af", f"silencedetect=noise={threshold_db}dB:duration={min_duration}",
           "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends   = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return list(zip(starts, ends))

def build_keep_segments(silence_segs, total_duration, padding=0.05):
    segments, prev = [], 0.0
    for (s, e) in silence_segs:
        end_keep = max(prev, s - padding)
        if end_keep - prev > 0.05:
            segments.append((prev, end_keep))
        prev = min(e + padding, total_duration)
    if total_duration - prev > 0.05:
        segments.append((prev, total_duration))
    return segments

def remove_silence_to_file(ffmpeg, ffprobe, input_path, out_file, threshold, min_dur, progress_cb=None):
    tmp_dir = Path(tempfile.mkdtemp(prefix="sc_"))
    try:
        silence_segs = detect_silence(ffmpeg, input_path, threshold, min_dur)
        total_dur = get_duration(ffprobe, input_path)
        keep_segs = build_keep_segments(silence_segs, total_dur)
        concat_file = tmp_dir / "concat.txt"
        lines = []
        n = max(len(keep_segs), 1)
        for i, (s, e) in enumerate(keep_segs):
            seg = tmp_dir / f"seg_{i:04d}.mp4"
            subprocess.run([
                ffmpeg, "-y", "-ss", f"{s:.4f}", "-to", f"{e:.4f}",
                "-i", str(input_path),
                "-c:v", "libx264", "-c:a", "aac",
                "-avoid_negative_ts", "make_zero",
                str(seg), "-loglevel", "error"
            ], capture_output=True, timeout=120)
            if seg.exists():
                lines.append(f"file '{seg}'\n")
            if progress_cb:
                progress_cb((i + 1) / n)
        concat_file.write_text("".join(lines), encoding="utf-8")
        subprocess.run([
            ffmpeg, "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_file), "-c", "copy",
            str(out_file), "-loglevel", "error"
        ], capture_output=True, timeout=300)
        return out_file.exists(), len(keep_segs)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

def merge_files(ffmpeg, file_list, out_file):
    tmp_dir = Path(tempfile.mkdtemp(prefix="sc_merge_"))
    try:
        concat_file = tmp_dir / "concat.txt"
        lines = [f"file '{f}'\n" for f in file_list if Path(f).exists()]
        concat_file.write_text("".join(lines), encoding="utf-8")
        subprocess.run([
            ffmpeg, "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_file), "-c", "copy",
            str(out_file), "-loglevel", "error"
        ], capture_output=True, timeout=600)
        return out_file.exists()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

def get_prefix(filename):
    stem = Path(filename).stem
    m = re.match(r'^(.+?)[-_]', stem)
    return m.group(1) if m else stem


# ── 主界面 ──────────────────────────────────────

class App(TkinterDnD.Tk if HAS_DND else tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("口播去气口工具")
        self.geometry("740x840")
        self.minsize(740, 720)
        self.resizable(True, True)
        self.configure(bg=BG_MAIN)

        self.files = []
        self.processing = False
        self._ffmpeg  = find_ffmpeg()
        self._ffprobe = shutil.which("ffprobe") or (
            str(Path(self._ffmpeg).parent / "ffprobe") if self._ffmpeg else None)

        self._build_ui()
        self._check_ffmpeg()

    def _build_ui(self):
        # ── 标题栏 ──────────────────────────────
        title_bar = ctk.CTkFrame(self, fg_color="#0a1628", corner_radius=0, height=72)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)
        ctk.CTkLabel(title_bar, text="🎙  口播去气口工具",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=TEXT_MAIN).pack(side="left", padx=24, pady=16)
        ctk.CTkLabel(title_bar, text="去气口 · 自动分组 · 批量合并",
                     font=ctk.CTkFont(size=12),
                     text_color=TEXT_GRAY).pack(side="right", padx=24)

        # ── 拖拽区 ──────────────────────────────
        drop_outer = ctk.CTkFrame(self, fg_color=BG_MAIN)
        drop_outer.pack(fill="x", padx=20, pady=(14, 8))

        self.drop_frame = ctk.CTkFrame(drop_outer, height=100, corner_radius=12,
                                       border_width=2, border_color=BORDER,
                                       fg_color=BG_CARD)
        self.drop_frame.pack(fill="x")
        self.drop_frame.pack_propagate(False)

        inner = ctk.CTkFrame(self.drop_frame, fg_color="transparent")
        inner.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(inner, text="🎬  拖拽视频文件到这里，或点击选择",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=ACCENT_HOV).pack()
        ctk.CTkLabel(inner, text="支持多选 MP4 / MOV / MKV，按文件名前缀自动分组",
                     font=ctk.CTkFont(size=11), text_color=TEXT_GRAY).pack(pady=(2,0))

        for w in (self.drop_frame, inner):
            w.bind("<Button-1>", lambda e: self._pick_files())
            if HAS_DND:
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)
                w.dnd_bind("<<DragEnter>>", lambda e: self.drop_frame.configure(border_color=ACCENT_HOV))
                w.dnd_bind("<<DragLeave>>", lambda e: self.drop_frame.configure(border_color=BORDER))
        for child in inner.winfo_children():
            child.bind("<Button-1>", lambda e: self._pick_files())
            if HAS_DND:
                child.drop_target_register(DND_FILES)
                child.dnd_bind("<<Drop>>", self._on_drop)

        # ── 文件列表卡片 ────────────────────────
        lf = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=12)
        lf.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        top_row = ctk.CTkFrame(lf, fg_color="transparent")
        top_row.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(top_row, text="待处理文件队列",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT_MAIN).pack(side="left")
        self.count_label = ctk.CTkLabel(top_row, text="0 个文件 · 0 组",
                                         text_color=TEXT_GRAY,
                                         font=ctk.CTkFont(size=12))
        self.count_label.pack(side="right")

        self.file_listbox = tk.Listbox(
            lf, bg=BG_LIST, fg=TEXT_MAIN,
            selectbackground=ACCENT, selectforeground="white",
            relief="flat", activestyle="none",
            font=("PingFang SC" if IS_MAC else "Microsoft YaHei", 12),
            height=9, borderwidth=0, highlightthickness=0)
        self.file_listbox.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        btn_row = ctk.CTkFrame(lf, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(0, 12))
        ctk.CTkButton(btn_row, text="＋ 添加文件", width=110, height=30,
                      fg_color=ACCENT, hover_color=ACCENT_HOV,
                      command=self._pick_files).pack(side="left", padx=(0,8))
        ctk.CTkButton(btn_row, text="✕ 删除选中", width=110, height=30,
                      fg_color=RED, hover_color=RED_HOV,
                      command=self._remove_selected).pack(side="left", padx=(0,8))
        ctk.CTkButton(btn_row, text="清空", width=70, height=30,
                      fg_color="#1e2d40", hover_color="#253650",
                      command=self._clear_files).pack(side="left")
        ctk.CTkButton(btn_row, text="👁 预览分组", width=110, height=30,
                      fg_color=GREEN, hover_color=GREEN_HOV,
                      command=self._preview_groups).pack(side="right")

        # ── 参数卡片 ────────────────────────────
        pf = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=12)
        pf.pack(fill="x", padx=20, pady=(0, 8))

        ctk.CTkLabel(pf, text="参数设置",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT_MAIN).grid(
                         row=0, column=0, columnspan=4, sticky="w", padx=14, pady=(12,8))

        ctk.CTkLabel(pf, text="静音阈值（dB）：",
                     text_color=TEXT_MAIN).grid(row=1, column=0, padx=14, pady=6, sticky="w")
        self.threshold_slider = ctk.CTkSlider(
            pf, from_=-60, to=-10, number_of_steps=50,
            button_color=ACCENT, button_hover_color=ACCENT_HOV,
            progress_color=ACCENT, command=self._upd_threshold)
        self.threshold_slider.set(-35)
        self.threshold_slider.grid(row=1, column=1, padx=8)
        self.threshold_lbl = ctk.CTkLabel(pf, text="-35 dB", width=72, text_color=TEXT_MAIN)
        self.threshold_lbl.grid(row=1, column=2)
        ctk.CTkLabel(pf, text="越大=删越多", text_color=TEXT_GRAY,
                     font=ctk.CTkFont(size=11)).grid(row=1, column=3, padx=6)

        ctk.CTkLabel(pf, text="最短静音时长（秒）：",
                     text_color=TEXT_MAIN).grid(row=2, column=0, padx=14, pady=6, sticky="w")
        self.duration_slider = ctk.CTkSlider(
            pf, from_=0.1, to=1.5, number_of_steps=28,
            button_color=ACCENT, button_hover_color=ACCENT_HOV,
            progress_color=ACCENT, command=self._upd_duration)
        self.duration_slider.set(0.3)
        self.duration_slider.grid(row=2, column=1, padx=8)
        self.duration_lbl = ctk.CTkLabel(pf, text="0.30 秒", width=72, text_color=TEXT_MAIN)
        self.duration_lbl.grid(row=2, column=2)
        ctk.CTkLabel(pf, text="短于此不删", text_color=TEXT_GRAY,
                     font=ctk.CTkFont(size=11)).grid(row=2, column=3, padx=6)

        ctk.CTkLabel(pf, text="输出目录：",
                     text_color=TEXT_MAIN).grid(row=3, column=0, padx=14, pady=(6,14), sticky="w")
        self.output_var = ctk.StringVar(value="（与源文件相同目录）")
        ctk.CTkEntry(pf, textvariable=self.output_var, width=270,
                     fg_color=BG_LIST, border_color=BORDER,
                     text_color=TEXT_MAIN).grid(row=3, column=1, columnspan=2, padx=8, pady=(6,14))
        ctk.CTkButton(pf, text="选择", width=64, height=30,
                      fg_color=ACCENT, hover_color=ACCENT_HOV,
                      command=self._pick_output).grid(row=3, column=3, padx=6, pady=(6,14))

        # ── 开始按钮 ────────────────────────────
        self.start_btn = ctk.CTkButton(
            self, text="▶  开始处理（去气口 + 分组合并导出）",
            height=50, corner_radius=10,
            fg_color=ACCENT, hover_color=ACCENT_HOV,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="white",
            command=self._start)
        self.start_btn.pack(padx=20, pady=(0, 8), fill="x")

        # ── 进度区 ──────────────────────────────
        prog_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=12)
        prog_frame.pack(fill="x", padx=20, pady=(0, 16))

        self.progress_bar = ctk.CTkProgressBar(prog_frame, height=10, corner_radius=5,
                                                progress_color=ACCENT, fg_color=BG_LIST)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=14, pady=(12, 4))

        self.status_lbl = ctk.CTkLabel(prog_frame, text="就绪",
                                        text_color=TEXT_GRAY,
                                        font=ctk.CTkFont(size=12))
        self.status_lbl.pack(pady=(0, 6))

        self.log_box = ctk.CTkTextbox(prog_frame, height=65,
                                       font=ctk.CTkFont(size=11),
                                       fg_color=BG_LIST, text_color=TEXT_MAIN,
                                       border_color=BORDER)
        self.log_box.pack(fill="x", padx=14, pady=(0, 12))
        self.log_box.configure(state="disabled")

    # ── 拖拽 ────────────────────────────────────
    def _on_drop(self, event):
        raw = event.data
        paths = re.findall(r'\{([^}]+)\}', raw)
        paths += re.sub(r'\{[^}]+\}', '', raw).split()
        added = 0
        for p in paths:
            p = p.strip()
            if p and Path(p).suffix.lower() in (".mp4",".mov",".mkv",".avi",".m4v"):
                if p not in [f for f,_ in self.files]:
                    self.files.append((p, Path(p).name))
                    added += 1
        self._refresh_list()
        self.drop_frame.configure(border_color=BORDER)
        if added:
            self._log(f"✅ 拖入 {added} 个文件")

    # ── 文件操作 ────────────────────────────────
    def _pick_files(self):
        paths = filedialog.askopenfilenames(
            title="选择视频文件",
            filetypes=[("视频文件","*.mp4 *.mov *.mkv *.avi *.m4v"),("所有文件","*.*")])
        for p in paths:
            if p not in [f for f,_ in self.files]:
                self.files.append((p, Path(p).name))
        self._refresh_list()

    def _remove_selected(self):
        for i in reversed(self.file_listbox.curselection()):
            self.file_listbox.delete(i)
            self.files.pop(i)
        self._refresh_count()

    def _clear_files(self):
        self.files.clear()
        self.file_listbox.delete(0, "end")
        self._refresh_count()

    def _refresh_list(self):
        self.files.sort(key=lambda x: x[1])
        self.file_listbox.delete(0, "end")
        for _, name in self.files:
            self.file_listbox.insert("end", f"  {name}")
        self._refresh_count()

    def _refresh_count(self):
        groups = self._build_groups()
        self.count_label.configure(
            text=f"{len(self.files)} 个文件 · {len(groups)} 组")

    def _build_groups(self):
        groups = defaultdict(list)
        for path, name in self.files:
            groups[get_prefix(name)].append(path)
        for k in groups:
            groups[k].sort(key=lambda x: Path(x).name)
        return dict(sorted(groups.items()))

    def _preview_groups(self):
        groups = self._build_groups()
        if not groups:
            messagebox.showinfo("分组预览", "还没有文件！")
            return
        lines = []
        for prefix, paths in groups.items():
            lines.append(f"【{prefix}】共 {len(paths)} 个片段 → 合并为 {prefix}_合并.mp4")
            for p in paths:
                lines.append(f"    · {Path(p).name}")
            lines.append("")
        win = ctk.CTkToplevel(self)
        win.title("分组预览")
        win.geometry("520x420")
        win.configure(fg_color=BG_MAIN)
        ctk.CTkLabel(win, text="分组预览",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=TEXT_MAIN).pack(pady=(16,8))
        tb = ctk.CTkTextbox(win, font=ctk.CTkFont(size=12),
                             fg_color=BG_CARD, text_color=TEXT_MAIN)
        tb.pack(fill="both", expand=True, padx=16, pady=(0,16))
        tb.insert("end", "\n".join(lines))
        tb.configure(state="disabled")

    def _pick_output(self):
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            self.output_var.set(d)

    def _upd_threshold(self, val):
        self.threshold_lbl.configure(text=f"{int(round(float(val)))} dB")

    def _upd_duration(self, val):
        self.duration_lbl.configure(text=f"{round(float(val),2):.2f} 秒")

    def _check_ffmpeg(self):
        if not self._ffmpeg:
            self._log("⚠️ 未检测到 ffmpeg！请先：brew install ffmpeg")
            self.start_btn.configure(state="disabled")
        else:
            self._log("✅ ffmpeg 就绪，可以开始处理")

    def _log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _set_status(self, msg):
        self.status_lbl.configure(text=msg)

    def _set_progress(self, val):
        self.progress_bar.set(max(0.0, min(1.0, val)))

    def _start(self):
        if self.processing:
            return
        if not self.files:
            messagebox.showwarning("提示", "请先添加视频文件！")
            return
        if not self._ffmpeg:
            messagebox.showerror("错误", "未找到 ffmpeg！")
            return
        self.processing = True
        self.start_btn.configure(state="disabled", text="处理中…")
        threading.Thread(target=self._process_all, daemon=True).start()

    def _process_all(self):
        threshold = int(round(self.threshold_slider.get()))
        min_dur   = round(self.duration_slider.get(), 2)
        out_root  = self.output_var.get()
        groups    = self._build_groups()
        total_groups = len(groups)
        success = fail = 0
        tmp_root = Path(tempfile.mkdtemp(prefix="sc_main_"))
        total_files = sum(len(v) for v in groups.values())
        done_files = 0

        try:
            for g_idx, (prefix, paths) in enumerate(groups.items()):
                self.after(0, self._set_status,
                           f"处理第 {g_idx+1}/{total_groups} 组：【{prefix}】")
                self.after(0, self._log,
                           f"\n━━ 第{g_idx+1}组【{prefix}】共{len(paths)}个片段 ━━")

                cut_files = []
                for f_idx, fpath in enumerate(paths):
                    fname = Path(fpath).name
                    self.after(0, self._log, f"  [{f_idx+1}/{len(paths)}] {fname}")
                    out_tmp = tmp_root / f"{prefix}_{f_idx:04d}.mp4"
                    try:
                        def prog(v, _df=done_files, _tf=total_files):
                            self.after(0, self._set_progress, (_df + v) / _tf)
                        ok, segs = remove_silence_to_file(
                            self._ffmpeg, self._ffprobe,
                            Path(fpath), out_tmp, threshold, min_dur, prog)
                        if ok:
                            cut_files.append(str(out_tmp))
                            self.after(0, self._log, f"    ✅ 完成（{segs}段）")
                        else:
                            self.after(0, self._log, f"    ❌ 失败")
                    except Exception as ex:
                        self.after(0, self._log, f"    ❌ 错误：{ex}")
                    done_files += 1

                if cut_files:
                    if out_root and out_root != "（与源文件相同目录）":
                        out_dir = Path(out_root)
                    else:
                        out_dir = Path(paths[0]).parent / "output_cut"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_file = out_dir / f"{prefix}_合并.mp4"
                    self.after(0, self._log, f"  🔗 合并{len(cut_files)}个片段…")
                    if merge_files(self._ffmpeg, cut_files, out_file):
                        self.after(0, self._log, f"  ✅ 导出：{out_file.name}")
                        success += 1
                    else:
                        self.after(0, self._log, f"  ❌ 合并失败")
                        fail += 1
                else:
                    self.after(0, self._log, f"  ⚠️ 无有效片段")
                    fail += 1
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)

        self.after(0, self._set_progress, 1.0)
        self.after(0, self._set_status, f"完成！成功 {success} 组，失败 {fail} 组")
        self.after(0, self._log, f"\n🎉 完成！导出 {success} 个视频，失败 {fail} 组")
        self.after(0, self.start_btn.configure,
                   {"state": "normal", "text": "▶  开始处理（去气口 + 分组合并导出）"})
        self.processing = False


if __name__ == "__main__":
    app = App()
    app.mainloop()
