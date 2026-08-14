import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import pymupdf  
from PIL import Image
import json
import os
import tempfile
import hashlib 
import re 
from tkinterdnd2 import TkinterDnD, DND_FILES

# --- Настройки продукта ---
APP_DATA_DIR = "app_data"
STATE_FILE = os.path.join(APP_DATA_DIR, "workbook_state.json")
HISTORY_FILE = os.path.join(APP_DATA_DIR, "print_history.json")

COLS = 4   
ROWS = 8   
TOTAL_SLOTS = COLS * ROWS

A4_WIDTH = 2480
A4_HEIGHT = 3508
CELL_W = A4_WIDTH // COLS
CELL_H = A4_HEIGHT // ROWS

ctk.set_appearance_mode("Light")

class CTk_DnD(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)

class OzonLabelOptimizer(CTk_DnD):
    def __init__(self):
        super().__init__()
        self.title("Ozon Print by Kulev")
        self.geometry("450x850") 
        
        if not os.path.exists(APP_DATA_DIR):
            os.makedirs(APP_DATA_DIR)
            
        self.print_history = self.load_history()
        self.pages = self.load_workbook()
        self.current_page_idx = len(self.pages) - 1
        self.current_image = self.load_page_image(self.current_page_idx)
        self.current_temp_pdf = None
        
        # --- ИНТЕРФЕЙС ---
        self.top_frame = ctk.CTkFrame(self, fg_color="#f8fafc", corner_radius=10, border_width=1, border_color="#e2e8f0")
        self.top_frame.pack(pady=10, padx=20, fill="x")
        
        self.lbl_status = ctk.CTkLabel(
            self.top_frame, text="Готово к работе. Добавляйте этикетки (можно перетащить файлы прямо в окно).", 
            font=ctk.CTkFont(family="Helvetica", size=13), 
            text_color="#334155", wraplength=380 
        )
        self.lbl_status.pack(pady=(10, 5), padx=10)

        self.paper_mode_var = ctk.BooleanVar(value=True)
        self.switch_paper = ctk.CTkSwitch(
            self.top_frame, text="Показывать линии разреза (крест)", 
            variable=self.paper_mode_var, command=self.draw_grid, font=ctk.CTkFont(size=12),
            progress_color="#64748b"
        )
        self.switch_paper.pack(pady=(5, 10))
        
        self.canvas_frame = ctk.CTkFrame(self, fg_color="white", border_width=2, border_color="#cbd5e1")
        self.canvas_frame.pack(pady=5)
        
        self.canvas_w = 420
        self.canvas_h = 594
        self.canvas = tk.Canvas(self.canvas_frame, width=self.canvas_w, height=self.canvas_h, bg="white", highlightthickness=0)
        self.canvas.pack(padx=2, pady=2)
        
        # --- СТРОКА НАВИГАЦИИ ---
        self.nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.nav_frame.pack(pady=10)
        
        self.btn_prev = ctk.CTkButton(self.nav_frame, text="< Назад", width=60, fg_color="#94a3b8", hover_color="#64748b", command=self.prev_page)
        self.btn_prev.grid(row=0, column=0, padx=5)
        
        self.lbl_page_info = ctk.CTkLabel(self.nav_frame, text="Лист 1 из 1", font=ctk.CTkFont(weight="bold"), text_color="#334155")
        self.lbl_page_info.grid(row=0, column=1, padx=10)
        
        self.btn_next = ctk.CTkButton(self.nav_frame, text="Вперед >", width=60, fg_color="#94a3b8", hover_color="#64748b", command=self.next_page)
        self.btn_next.grid(row=0, column=2, padx=5)
        
        self.btn_new_sheet = ctk.CTkButton(
            self.nav_frame, text="➕", font=ctk.CTkFont(size=14),
            fg_color="#f1f5f9", text_color="#0f172a", hover_color="#e2e8f0", 
            width=30, height=30, command=self.add_new_page, border_width=1, border_color="#cbd5e1"
        )
        self.btn_new_sheet.grid(row=0, column=3, padx=(10, 5))

        self.btn_del_sheet = ctk.CTkButton(
            self.nav_frame, text="🗑️", font=ctk.CTkFont(size=12), 
            fg_color="#fef2f2", text_color="#b91c1c", hover_color="#fee2e2", 
            width=30, height=30, command=self.delete_page, border_width=1, border_color="#fecaca"
        )
        self.btn_del_sheet.grid(row=0, column=4, padx=5)
        
        # --- СТРОКА ГЛАВНЫХ КНОПОК ---
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(pady=5)
        
        self.btn_add = ctk.CTkButton(
            self.btn_frame, text="Выбрать файлы", font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#64748b", hover_color="#475569", height=45, width=170, command=self.add_labels_dialog
        )
        self.btn_add.grid(row=0, column=0, padx=5)
        
        self.btn_print = ctk.CTkButton(
            self.btn_frame, text="Печать листа", font=ctk.CTkFont(size=13, weight="bold"),
            height=45, width=170, text_color_disabled="white", command=self.open_print_dialog
        )
        self.btn_print.grid(row=0, column=1, padx=5)

        self.update_ui()
        self.wm_state('normal')

        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.handle_drop_event)

    def show_message(self, text, msg_type="info"):
        colors = {"info": "#475569", "success": "#0f766e", "error": "#b91c1c", "action": "#0284c7"}
        self.lbl_status.configure(text=text, text_color=colors.get(msg_type, "#000000"))

    def get_blank_state(self):
        return [[{"s": 0, "t": "Пусто"} for _ in range(COLS)] for _ in range(ROWS)]

    def load_workbook(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    pages = json.load(f)
                    if pages and isinstance(pages, list): return pages
            except: pass
        return [self.get_blank_state()]

    def save_workbook(self):
        with open(STATE_FILE, 'w') as f: json.dump(self.pages, f)

    def load_page_image(self, page_idx):
        img_path = os.path.join(APP_DATA_DIR, f"page_{page_idx}.png")
        if os.path.exists(img_path):
            try:
                with Image.open(img_path) as img: return img.copy()
            except: pass
        return Image.new('RGB', (A4_WIDTH, A4_HEIGHT), 'white')

    def save_page_image(self, page_idx):
        img_path = os.path.join(APP_DATA_DIR, f"page_{page_idx}.png")
        self.current_image.save(img_path, "PNG")

    def prev_page(self):
        if self.current_page_idx > 0: self.change_page(self.current_page_idx - 1)

    def next_page(self):
        if self.current_page_idx < len(self.pages) - 1: self.change_page(self.current_page_idx + 1)

    def change_page(self, new_idx):
        self.save_page_image(self.current_page_idx)
        self.current_page_idx = new_idx
        self.current_image = self.load_page_image(self.current_page_idx)
        self.update_ui()
        self.show_message(f"Открыт Лист {new_idx + 1}.", "info")

    def add_new_page(self):
        self.save_page_image(self.current_page_idx)
        self.pages.append(self.get_blank_state())
        self.save_workbook()
        self.current_page_idx = len(self.pages) - 1
        self.current_image = Image.new('RGB', (A4_WIDTH, A4_HEIGHT), 'white')
        self.save_page_image(self.current_page_idx)
        self.update_ui()
        self.show_message("Создан новый чистый лист.", "success")

    def delete_page(self):
        if len(self.pages) == 1:
            self.show_message("Нельзя удалить единственный лист.", "error")
            return
            
        current_state = self.pages[self.current_page_idx]
        has_labels = any(cell["s"] != 0 for row in current_state for cell in row)
        
        if has_labels:
            if not messagebox.askyesno("Удаление", "На этом листе есть сохраненные этикетки.\nВы уверены, что хотите его удалить?"):
                return
                
        self.pages.pop(self.current_page_idx)
        
        del_path = os.path.join(APP_DATA_DIR, f"page_{self.current_page_idx}.png")
        if os.path.exists(del_path): 
            os.remove(del_path)
            
        for i in range(self.current_page_idx + 1, len(self.pages) + 1):
            old_path = os.path.join(APP_DATA_DIR, f"page_{i}.png")
            new_path = os.path.join(APP_DATA_DIR, f"page_{i-1}.png")
            if os.path.exists(old_path):
                os.rename(old_path, new_path)
                
        self.current_page_idx = min(self.current_page_idx, len(self.pages) - 1)
        self.current_image = self.load_page_image(self.current_page_idx)
        
        self.save_workbook()
        self.update_ui()
        self.show_message("Лист успешно удален.", "success")

    def update_ui(self):
        total = len(self.pages)
        curr = self.current_page_idx + 1
        self.lbl_page_info.configure(text=f"Лист {curr} из {total}")
        self.btn_prev.configure(state="normal" if curr > 1 else "disabled")
        self.btn_next.configure(state="normal" if curr < total else "disabled")
        
        current_state = self.pages[self.current_page_idx]
        has_unprinted = any(cell["s"] == 1 for row in current_state for cell in row)
        
        if has_unprinted:
            self.btn_print.configure(state="normal", fg_color="#10b981", hover_color="#059669")
        else:
            self.btn_print.configure(state="disabled", fg_color="#a855f7")
            
        self.draw_grid()

    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r') as f: return json.load(f)
            except: pass
        return []

    def save_history(self):
        with open(HISTORY_FILE, 'w') as f: json.dump(self.print_history, f)

    def get_file_hash(self, filepath):
        hasher = hashlib.md5()
        with open(filepath, 'rb') as f: hasher.update(f.read())
        return hasher.hexdigest()

    def extract_label_info(self, pdf_path):
        try:
            doc = pymupdf.open(pdf_path)
            raw_text = doc[0].get_text("text")
            doc.close()
            
            # --- 1. ПОИСК ID ЗАКАЗА ---
            
            # Склеиваем тире между цифрами
            id_text = re.sub(r'(?<=\d)[\s\n]*([-–—−])[\s\n]*(?=\d)', r'\1', raw_text)
            
            
            id_text = re.sub(r'(?<=\d)[ \t]+(?=\d)', '', id_text)
            
            order_id, suf1, suf2 = "", "", ""
            
            full_match = re.search(r'(\d{7,})[-–—−](\d{4})(?:[-–—−](\d{1,3}))?', id_text)
            
            if full_match:
                order_id = full_match.group(1)
                suf1 = full_match.group(2)
                suf2 = full_match.group(3) if full_match.group(3) else ""
            else:
                m_main = re.search(r'(?<!\d)(\d{7,})(?!\d)', id_text)
                if m_main: order_id = m_main.group(1)
                
                m_suf1 = re.search(r'[-–—−](\d{4})(?:[-–—−](\d{1,3}))?', id_text)
                if m_suf1:
                    suf1 = m_suf1.group(1)
                    suf2 = m_suf1.group(2) if m_suf1.group(2) else ""
                else:
                    m_suf2 = re.search(r'(?<!\d)(\d{4})[-–—−](\d{1,3})(?!\d)', id_text)
                    if m_suf2:
                        suf1 = m_suf2.group(1)
                        suf2 = m_suf2.group(2) if m_suf2.group(2) else ""

            if order_id and len(order_id) > 15:
                order_id = order_id[-15:]

            # Формируем итоговую склейку ID
            if order_id and suf1:
                formatted_id = f"{order_id}-\n{suf1}-{suf2}" if suf2 else f"{order_id}-\n{suf1}"
            elif order_id:
                formatted_id = order_id
            elif suf1:
                formatted_id = f"Заказ-\n{suf1}-{suf2}" if suf2 else f"Заказ-\n{suf1}"
            else:
                formatted_id = "Заказ"

            city = ""
            lines = [t.strip() for t in raw_text.split('\n') if t.strip()]
            
            for line in lines:
                upper_line = line.upper()
                if order_id and order_id in line: continue
                if suf1 and suf1 in line: continue
                
                if any(keyword in upper_line for keyword in ["СЦ ", "РЦ ", "МК ", "СКЛАД ", "ЦО "]):
                    city = line
                    break
                    
            if not city:
                for line in lines:
                    if order_id and order_id in line: continue
                    if suf1 and suf1 in line: continue
                    if len(line) > 3 and any(c.isalpha() for c in line) and "OZON" not in line.upper():
                        city = line
                        break
            
            clean_city = city[:25] if city else ""
            
            if clean_city:
                return f"{formatted_id}\n\n{clean_city}"
            return formatted_id
            
        except Exception:
            return "Ошибка\nчтения"

    def draw_grid(self):
        self.canvas.delete("all")
        w, h = self.canvas_w / COLS, self.canvas_h / ROWS
        current_state = self.pages[self.current_page_idx]
        
        wrap_width = w - 6 
        
        for r in range(ROWS):
            for c in range(COLS):
                x1, y1 = c * w, r * h
                x2, y2 = x1 + w, y1 + h
                
                cell = current_state[r][c]
                val, text = cell["s"], cell["t"]
                
                if val == 0:
                    bg, out, tc, fnt = "#ffffff", "#e2e8f0", "#94a3b8", ("Helvetica", 7)
                    self.canvas.create_rectangle(x1, y1, x2, y2, fill=bg, outline=out)
                    self.canvas.create_text(
                        x1 + w/2, y1 + h/2, 
                        text=text, fill=tc, font=fnt, justify="center", width=wrap_width
                    )
                else:
                    if val == 1:
                        bg, out, tc_city, fnt = "#e0f2fe", "#7dd3fc", "#0369a1", ("Helvetica", 7, "bold")
                        tc_id = "#000000"
                    else:
                        bg, out, tc_city, fnt = "#f1f5f9", "#cbd5e1", "#64748b", ("Helvetica", 7)
                        tc_id = "#000000"

                    self.canvas.create_rectangle(x1, y1, x2, y2, fill=bg, outline=out)
                    
                    parts = text.split('\n\n')
                    id_text = parts[0]
                    city_text = parts[1] if len(parts) > 1 else ""
                    
                    if "-\n" in id_text:
                        id_lines = id_text.split('-\n')
                        if len(id_lines[0]) > 15 and id_lines[0].isdigit():
                            id_lines[0] = id_lines[0][-15:] 
                            id_text = '-\n'.join(id_lines)
                    else:
                        if len(id_text) > 15 and id_text.isdigit():
                            id_text = id_text[-15:]
                            
                    # Отрисовка
                    if city_text:
                        self.canvas.create_text(
                            x1 + w/2, y1 + h/2 - 9, 
                            text=id_text, fill=tc_id, font=fnt, justify="center", width=wrap_width
                        )
                        self.canvas.create_text(
                            x1 + w/2, y1 + h/2 + 15, 
                            text=city_text, fill=tc_city, font=fnt, justify="center", width=wrap_width
                        )
                    else:
                        self.canvas.create_text(
                            x1 + w/2, y1 + h/2, 
                            text=id_text, fill=tc_id, font=fnt, justify="center", width=wrap_width
                        )
                    
        if self.paper_mode_var.get():
            cx, cy = self.canvas_w / 2, self.canvas_h / 2
            self.canvas.create_line(0, cy, self.canvas_w, cy, fill="#cbd5e1", width=2, dash=(5, 5))
            self.canvas.create_line(cx, 0, cx, self.canvas_h, fill="#cbd5e1", width=2, dash=(5, 5))

    def get_free_slots(self, count):
        slots = []
        current_state = self.pages[self.current_page_idx]
        for r in range(ROWS - 1, -1, -1):
            for c in range(COLS):
                if current_state[r][c]["s"] == 0:
                    slots.append((r, c))
                    if len(slots) == count: return slots
        return slots

    def add_labels_dialog(self):
        file_paths = filedialog.askopenfilenames(title="Выберите PDF этикетки", filetypes=[("PDF files", "*.pdf")])
        if file_paths:
            self.process_pdf_files(file_paths)

    def handle_drop_event(self, event):
        raw_data = event.data
        if '{' in raw_data:
            files = [x.strip('{}') for x in re.findall(r'{[^}]+}|[^\s{}]+', raw_data)]
        else:
            files = raw_data.split()
            
        pdf_files = [f for f in files if f.lower().endswith('.pdf')]
        
        if not pdf_files:
            self.show_message("ОШИБКА: Пожалуйста, перетаскивайте только PDF файлы.", "error")
            return
            
        self.process_pdf_files(pdf_files)

    def process_pdf_files(self, file_paths):
        valid_files = []
        for path in file_paths:
            f_hash = self.get_file_hash(path)
            if f_hash in self.print_history:
                if messagebox.askyesno("Обнаружен повтор", f"Этикетка '{os.path.basename(path)}' уже печаталась.\nРаспечатать повторно?"):
                    valid_files.append((path, f_hash))
            else:
                valid_files.append((path, f_hash))

        if not valid_files: return

        slots_needed = len(valid_files)
        free_slots = self.get_free_slots(slots_needed)
        
        if len(free_slots) < slots_needed:
            self.show_message(f"ОШИБКА: На этом листе свободно {len(free_slots)} мест. Создайте новый лист кнопкой ➕.", "error")
            return

        self.show_message("Обработка и распознавание текста...", "action")
        self.update_idletasks() 
        
        current_state = self.pages[self.current_page_idx]
        
        try:
            for i, (pdf_path, f_hash) in enumerate(valid_files):
                label_text = self.extract_label_info(pdf_path)
                
                doc = pymupdf.open(pdf_path) 
                page = doc.load_page(0)
                pix = page.get_pixmap(matrix=pymupdf.Matrix(3, 3))
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                img.thumbnail((CELL_W - 40, CELL_H - 40), Image.Resampling.LANCZOS)
                r, c = free_slots[i]
                
                paste_x = (c * CELL_W) + (CELL_W - img.width) // 2
                paste_y = (r * CELL_H) + (CELL_H - img.height) // 2
                
                self.current_image.paste(img, (paste_x, paste_y))
                current_state[r][c] = {"s": 1, "t": label_text}
                
                if f_hash not in self.print_history:
                    self.print_history.append(f_hash)
                    
                doc.close()
            
            self.save_page_image(self.current_page_idx)
            self.save_workbook()
            self.save_history() 
            self.update_ui()
            
            self.show_message(f"Добавлено этикеток: {slots_needed}. Можно печатать.", "success")
                    
        except Exception as e:
            for r, c in free_slots:
                current_state[r][c] = {"s": 0, "t": "Пусто"}
            self.show_message(f"Сбой: {str(e)}", "error")

    def open_print_dialog(self):
        print_image = Image.new('RGB', (A4_WIDTH, A4_HEIGHT), 'white')
        current_state = self.pages[self.current_page_idx]
        
        has_new = False
        
        for r in range(ROWS):
            for c in range(COLS):
                if current_state[r][c]["s"] == 1:
                    has_new = True
                    left = c * CELL_W
                    top = r * CELL_H
                    right = left + CELL_W
                    bottom = top + CELL_H
                    
                    cell_img = self.current_image.crop((left, top, right, bottom))
                    print_image.paste(cell_img, (left, top))
                    
        if not has_new:
            self.show_message("На этом листе нет новых этикеток для печати.", "error")
            return
            
        self.current_temp_pdf = os.path.join(tempfile.gettempdir(), f"ozon_print_page_{self.current_page_idx}.pdf")
        
        print_image.save(self.current_temp_pdf, "PDF", resolution=300.0)
        
        if os.path.exists(self.current_temp_pdf):
            try:
                os.startfile(self.current_temp_pdf)
                
                for r in range(ROWS):
                    for c in range(COLS):
                        if current_state[r][c]["s"] == 1:
                            current_state[r][c]["s"] = 2
                            
                self.save_workbook()
                self.update_ui()
                
                self.show_message(f"Отправлено на печать. Ячейки сохранены в историю (стали серыми).", "action")
            except Exception as e:
                self.show_message(f"Ошибка печати: {str(e)}", "error")

if __name__ == "__main__":
    app = OzonLabelOptimizer()
    app.mainloop()