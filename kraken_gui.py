import sys
import os
import subprocess
import json
import traceback
from PIL import Image, ImageDraw
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTabWidget, QLabel, QLineEdit, QPushButton, QTextEdit,
    QScrollArea, QFileDialog, QMessageBox, QFrame
)
from PySide6.QtCore import Qt, QThread, QObject, Signal
from PySide6.QtGui import QPixmap, QImage

# --- للمساعدة في تحويل صور Pillow إلى QImage ---
from PIL.ImageQt import ImageQt

# ===================================================================================
# Worker Class for Threading
# ===================================================================================
class Worker(QObject):
    """
    ينقل المهام الطويلة (مثل subprocess) إلى خيط منفصل لمنع تجميد الواجهة.
    """
    finished = Signal(dict)  # إشارة عند انتهاء المهمة بنجاح أو بفشل
    progress = Signal(str)   # إشارة لإرسال تحديثات نصية (مثل سجل التدريب)

    def __init__(self, task_function, *args, **kwargs):
        super().__init__()
        self.task_function = task_function
        self.args = args
        self.kwargs = kwargs

    def run(self):
        """
        يقوم بتشغيل المهمة الفعلية.
        """
        try:
            result = self.task_function(self.progress.emit, *self.args, **self.kwargs)
            self.finished.emit({'success': True, 'result': result})
        except FileNotFoundError as e:
            error_str = f"خطأ ملف غير موجود: {e}\n\n" \
                        f"لم يتم العثور على الأمر 'kraken' أو 'ketos'.\n" \
                        f"يرجى التأكد من تثبيت Kraken بشكل صحيح وتحديد المسار الصحيح في حقل 'مسار Kraken/Ketos'."
            self.finished.emit({'success': False, 'error': error_str})
        except Exception as e:
            error_str = f"{str(e)}\n{traceback.format_exc()}"
            self.finished.emit({'success': False, 'error': error_str})

# ===================================================================================
# Main Application Window
# ===================================================================================
class KrakenPySideApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("واجهة Kraken OCR المتكاملة (تعرف وتدريب) - PySide6")
        self.setGeometry(100, 100, 1200, 850)

        # تحديد المسار الأساسي (مهم عند تجميع التطبيق في ملف exe)
        if getattr(sys, 'frozen', False):
            self.base_path = sys._MEIPASS
        else:
            self.base_path = os.path.dirname(os.path.abspath(__file__))

        # --- Shared Variables ---
        self.thread = None
        self.worker = None
        self.selected_file_path_ocr = ""
        self.pil_original_image_ocr = None
        self.segmentation_successful_ocr = False
        self.temp_output_file_ocr = os.path.join(self.base_path, "kraken_temp_ocr_output.txt")
        self.temp_segmentation_json_ocr = os.path.join(self.base_path, "kraken_temp_segmentation.json")
        self.training_pairs = []
        self.training_pair_widgets = [] # لتتبع واجهات أزواج التدريب

        # --- Main Layout ---
        self.main_layout = QVBoxLayout(self)

        # --- Configuration Frame ---
        config_frame = QFrame()
        config_frame.setFrameShape(QFrame.Shape.StyledPanel)
        config_layout = QHBoxLayout(config_frame)
        config_layout.addWidget(QLabel("مسار مجلد Kraken/Ketos:"))
        self.kraken_path_entry = QLineEdit()
        self.kraken_path_entry.setPlaceholderText("مثال: C:/Users/YourUser/kraken-env/Scripts")
        config_layout.addWidget(self.kraken_path_entry)
        browse_kraken_path_button = QPushButton("تصفح...")
        browse_kraken_path_button.clicked.connect(self.browse_kraken_path)
        config_layout.addWidget(browse_kraken_path_button)
        self.main_layout.addWidget(config_frame)

        # --- TabView ---
        self.tab_view = QTabWidget()
        self.main_layout.addWidget(self.tab_view)

        # --- Create Tabs ---
        self.ocr_tab = QWidget()
        self.training_tab = QWidget()

        self.tab_view.addTab(self.ocr_tab, "التعرف الضوئي (OCR)")
        self.tab_view.addTab(self.training_tab, "تدريب نموذج جديد")

        # --- Populate Tabs ---
        self.create_ocr_tab_widgets()
        self.create_training_tab_widgets()

    def browse_kraken_path(self):
        """يفتح حوار لاختيار المجلد الذي يحتوي على ملفات kraken و ketos التنفيذية."""
        directory = QFileDialog.getExistingDirectory(self, "اختر مجلد Kraken")
        if directory:
            self.kraken_path_entry.setText(directory)

    def get_subprocess_env(self):
        """يُعد بيئة التشغيل للعمليات الفرعية مع إضافة مسار kraken المحدد."""
        sub_env = os.environ.copy()
        sub_env["PYTHONIOENCODING"] = "utf-8"
        sub_env["PYTHONUTF8"] = "1"
        
        kraken_dir = self.kraken_path_entry.text()
        if kraken_dir and os.path.isdir(kraken_dir):
            # إضافة المسار المحدد إلى بداية متغير PATH
            sub_env["PATH"] = f"{kraken_dir}{os.pathsep}{sub_env.get('PATH', '')}"
        
        return sub_env

    # ===================================================================================
    # OCR TAB WIDGETS AND LOGIC
    # ===================================================================================
    def create_ocr_tab_widgets(self):
        layout = QGridLayout(self.ocr_tab)

        # --- File input frame ---
        file_frame = QFrame()
        file_layout = QHBoxLayout(file_frame)
        file_layout.addWidget(QLabel("ملف الصورة:"))
        self.ocr_file_path_entry = QLineEdit("لم يتم تحديد ملف صورة")
        self.ocr_file_path_entry.setReadOnly(True)
        file_layout.addWidget(self.ocr_file_path_entry)
        browse_button = QPushButton("تصفح...")
        browse_button.clicked.connect(self.browse_file_ocr)
        file_layout.addWidget(browse_button)
        layout.addWidget(file_frame, 0, 0)

        # --- Controls frame ---
        controls_frame = QFrame()
        controls_layout = QHBoxLayout(controls_frame)
        self.ocr_segment_button = QPushButton("1. تجزئة الصورة")
        self.ocr_segment_button.clicked.connect(self.start_segmentation)
        controls_layout.addWidget(self.ocr_segment_button)

        controls_layout.addWidget(QLabel("نموذج التعرف:"))
        self.ocr_model_name_entry = QLineEdit("arabic_best.mlmodel")
        controls_layout.addWidget(self.ocr_model_name_entry)

        self.ocr_run_button = QPushButton("2. استخراج النص")
        self.ocr_run_button.setEnabled(False)
        self.ocr_run_button.clicked.connect(self.start_ocr_after_segmentation)
        controls_layout.addWidget(self.ocr_run_button)
        layout.addWidget(controls_frame, 1, 0)

        # --- Image display frame ---
        image_display_frame = QFrame()
        image_display_layout = QGridLayout(image_display_frame)
        image_display_layout.addWidget(QLabel("الصورة الأصلية:"), 0, 0, Qt.AlignmentFlag.AlignBottom)
        self.ocr_original_image_label = QLabel("لم يتم تحميل صورة")
        self.ocr_original_image_label.setMinimumSize(250, 250)
        self.ocr_original_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ocr_original_image_label.setFrameShape(QFrame.Shape.StyledPanel)
        image_display_layout.addWidget(self.ocr_original_image_label, 1, 0)

        image_display_layout.addWidget(QLabel("الصورة المجزأة:"), 0, 1, Qt.AlignmentFlag.AlignBottom)
        self.ocr_segmented_image_label = QLabel("لم يتم إنشاء صورة مجزأة")
        self.ocr_segmented_image_label.setMinimumSize(250, 250)
        self.ocr_segmented_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ocr_segmented_image_label.setFrameShape(QFrame.Shape.StyledPanel)
        image_display_layout.addWidget(self.ocr_segmented_image_label, 1, 1)
        layout.addWidget(image_display_frame, 2, 0)

        # --- Result textbox ---
        layout.addWidget(QLabel("النص المستخرج:"), 3, 0)
        self.ocr_result_textbox = QTextEdit()
        self.ocr_result_textbox.setReadOnly(True)
        layout.addWidget(self.ocr_result_textbox, 4, 0)

        # --- Status label ---
        self.ocr_status_label = QLabel("الحالة: جاهز")
        layout.addWidget(self.ocr_status_label, 5, 0)
        
        layout.setRowStretch(2, 2) # Image frame
        layout.setRowStretch(4, 1) # Result textbox

    def display_image(self, label_widget, pil_image):
        if pil_image is None:
            label_widget.setText("لا توجد صورة")
            label_widget.setPixmap(QPixmap()) # Clear image
            return

        try:
            q_image = ImageQt(pil_image)
            pixmap = QPixmap.fromImage(q_image)
            scaled_pixmap = pixmap.scaled(label_widget.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            label_widget.setPixmap(scaled_pixmap)
        except Exception as e:
            print(f"Error displaying image: {e}")
            label_widget.setText("خطأ في عرض الصورة")

    def browse_file_ocr(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "اختر ملف صورة للتعرف", "", "ملفات الصور (*.png *.jpg *.jpeg *.bmp *.tiff);;All files (*.*)")
        if file_path:
            self.selected_file_path_ocr = file_path
            self.ocr_file_path_entry.setText(os.path.basename(file_path))
            
            self.ocr_result_textbox.clear()
            self.update_status_ocr("الحالة: جاهز")
            self.segmentation_successful_ocr = False
            self.ocr_run_button.setEnabled(False)

            try:
                self.pil_original_image_ocr = Image.open(self.selected_file_path_ocr)
                self.display_image(self.ocr_original_image_label, self.pil_original_image_ocr)
            except Exception as e:
                QMessageBox.critical(self, "خطأ في الصورة", f"لا يمكن تحميل الصورة الأصلية: {e}")
                self.pil_original_image_ocr = None
                self.display_image(self.ocr_original_image_label, None)

            self.display_image(self.ocr_segmented_image_label, None)
            self.ocr_segmented_image_label.setText("لم يتم إنشاء صورة مجزأة بعد")

    def update_status_ocr(self, message):
        self.ocr_status_label.setText(message)

    def start_segmentation(self):
        if not self.selected_file_path_ocr:
            QMessageBox.critical(self, "خطأ", "يرجى تحديد ملف صورة أولاً.")
            return
            
        self.ocr_segment_button.setEnabled(False)
        self.ocr_run_button.setEnabled(False)
        self.update_status_ocr("الحالة: جاري تجزئة الصورة، يرجى الانتظار...")
        self.ocr_result_textbox.clear()
        self.display_image(self.ocr_segmented_image_label, None)
        self.ocr_segmented_image_label.setText("جاري إنشاء الصورة المجزأة...")
        self.segmentation_successful_ocr = False

        self.run_long_task(self._perform_segmentation_task, self.on_segmentation_finished)

    def _perform_segmentation_task(self, progress_callback):
        image_path = self.selected_file_path_ocr
        segment_command = ["kraken", "-i", image_path, self.temp_segmentation_json_ocr, "segment"]
        
        process = subprocess.run(segment_command, capture_output=True, text=True, 
                                 encoding='utf-8', errors='replace', check=False, 
                                 env=self.get_subprocess_env())
        
        if process.returncode != 0:
            error_message = f"فشل تجزئة OCR:\nCode: {process.returncode}\nStderr:\n{process.stderr}"
            raise Exception(error_message)
        
        return None # لا نحتاج لإعادة قيمة هنا

    def on_segmentation_finished(self, result):
        self.ocr_segment_button.setEnabled(True)
        if not result['success']:
            self.ocr_result_textbox.setText(result['error'])
            self.update_status_ocr("الحالة: خطأ في تجزئة الصورة.")
            self.segmentation_successful_ocr = False
            return

        self.segmentation_successful_ocr = True
        self.update_status_ocr("الحالة: اكتملت التجزئة. جاهز لاستخراج النص.")
        self.ocr_run_button.setEnabled(True)
        
        try:
            with open(self.temp_segmentation_json_ocr, 'r', encoding='utf-8') as f:
                segmentation_data = json.load(f)
            
            image_to_draw_on = self.pil_original_image_ocr.copy().convert("RGB")
            draw = ImageDraw.Draw(image_to_draw_on)
            
            lines_to_draw = segmentation_data.get("lines", [])
            for line_info in lines_to_draw:
                polygon = line_info.get("baseline")
                if polygon and isinstance(polygon, list) and len(polygon) > 1:
                    flat_polygon = [coord for point in polygon for coord in point]
                    if len(flat_polygon) >= 4:
                        draw.polygon(flat_polygon, outline="red", width=2)

            self.display_image(self.ocr_segmented_image_label, image_to_draw_on)
        except Exception as e:
            self.update_status_ocr("الحالة: خطأ في رسم الصورة المجزأة.")
            print(f"Error drawing segmented image: {e}")

    def start_ocr_after_segmentation(self):
        if not self.selected_file_path_ocr or not self.segmentation_successful_ocr or not os.path.exists(self.temp_segmentation_json_ocr):
            QMessageBox.critical(self, "خطأ", "يرجى تحديد صورة وتجزئتها بنجاح أولاً.")
            return
        model_name = self.ocr_model_name_entry.text()
        if not model_name:
            QMessageBox.critical(self, "خطأ", "يرجى إدخال اسم نموذج التعرف.")
            return
            
        self.ocr_run_button.setEnabled(False)
        self.ocr_segment_button.setEnabled(False)
        self.update_status_ocr("الحالة: جاري استخراج النص (OCR)، يرجى الانتظار...")
        self.ocr_result_textbox.clear()

        self.run_long_task(self._perform_ocr_task, self.on_ocr_finished, model_name)

    def _perform_ocr_task(self, progress_callback, model_name):
        image_path = self.selected_file_path_ocr
        ocr_command = ["kraken", "-i", image_path, self.temp_output_file_ocr, "ocr", "--model", model_name, "--lines", self.temp_segmentation_json_ocr]
        
        process_ocr = subprocess.run(ocr_command, capture_output=True, text=True, 
                                     encoding='utf-8', errors='replace', check=False, 
                                     env=self.get_subprocess_env())
        
        if process_ocr.returncode != 0:
            error_message = f"فشل OCR:\nCode: {process_ocr.returncode}\nStderr:\n{process_ocr.stderr}\nStdout:\n{process_ocr.stdout}"
            raise Exception(error_message)
        
        if os.path.exists(self.temp_output_file_ocr):
            with open(self.temp_output_file_ocr, "r", encoding="utf-8") as f:
                return f.read()
        else:
            return process_ocr.stdout if process_ocr.stdout else "لا يوجد إخراج نصي."

    def on_ocr_finished(self, result):
        self.ocr_segment_button.setEnabled(True)
        if self.segmentation_successful_ocr:
            self.ocr_run_button.setEnabled(True)
        
        if not result['success']:
            self.ocr_result_textbox.setText(result['error'])
            self.update_status_ocr("الحالة: خطأ في التعرف الضوئي.")
        else:
            self.ocr_result_textbox.setText(result.get('result', ''))
            self.update_status_ocr("الحالة: اكتمل التعرف الضوئي بنجاح!")
        
        if os.path.exists(self.temp_output_file_ocr):
            try:
                os.remove(self.temp_output_file_ocr)
            except Exception as e_remove:
                print(f"Failed to remove temp OCR output: {e_remove}")
    
    # ===================================================================================
    # TRAINING TAB WIDGETS AND LOGIC
    # ===================================================================================
    def create_training_tab_widgets(self):
        layout = QVBoxLayout(self.training_tab)

        # --- Controls for adding pairs and training params ---
        train_controls_frame = QFrame()
        train_controls_layout = QGridLayout(train_controls_frame)
        
        add_pair_button = QPushButton("إضافة زوج (صورة + نص كتابي)")
        add_pair_button.clicked.connect(self.add_training_pair)
        train_controls_layout.addWidget(add_pair_button, 0, 0, 1, 2)
        
        train_controls_layout.addWidget(QLabel("اسم النموذج الناتج:"), 1, 0)
        self.train_output_model_name_entry = QLineEdit("my_arabic_model.mlmodel")
        train_controls_layout.addWidget(self.train_output_model_name_entry, 1, 1)
        
        train_controls_layout.addWidget(QLabel("عدد الحقب (Epochs):"), 2, 0)
        self.train_epochs_entry = QLineEdit("100")
        train_controls_layout.addWidget(self.train_epochs_entry, 2, 1)
        layout.addWidget(train_controls_frame)

        # --- Scrollable frame for training pairs ---
        layout.addWidget(QLabel("ملفات التدريب المضافة:"))
        self.training_pairs_scroll_area = QScrollArea()
        self.training_pairs_scroll_area.setWidgetResizable(True)
        self.training_pairs_scroll_area.setFrameShape(QFrame.Shape.StyledPanel)
        
        self.scroll_content_widget = QWidget()
        self.scroll_content_layout = QVBoxLayout(self.scroll_content_widget)
        self.scroll_content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.training_pairs_scroll_area.setWidget(self.scroll_content_widget)
        layout.addWidget(self.training_pairs_scroll_area)

        # --- Buttons below scrollable frame ---
        train_action_buttons_frame = QFrame()
        train_action_buttons_layout = QHBoxLayout(train_action_buttons_frame)
        self.train_clear_list_button = QPushButton("مسح القائمة")
        self.train_clear_list_button.clicked.connect(self.clear_training_pairs)
        train_action_buttons_layout.addWidget(self.train_clear_list_button)
        
        self.train_start_button = QPushButton("بدء التدريب")
        self.train_start_button.clicked.connect(self.start_training)
        train_action_buttons_layout.addWidget(self.train_start_button)
        layout.addWidget(train_action_buttons_frame)
        
        # --- Training Log Textbox ---
        layout.addWidget(QLabel("سجل التدريب:"))
        self.training_log_textbox = QTextEdit()
        self.training_log_textbox.setReadOnly(True)
        layout.addWidget(self.training_log_textbox)
        
        self.training_status_label = QLabel("الحالة: جاهز لإضافة ملفات التدريب.")
        layout.addWidget(self.training_status_label)

        layout.setStretch(1, 1) # Scroll area
        layout.setStretch(4, 2) # Log textbox

    def add_training_pair(self):
        image_path, _ = QFileDialog.getOpenFileName(self, "اختر صورة المخطوطة للتدريب", "", "ملفات الصور (*.png *.jpg *.jpeg *.tif *.tiff);;All files (*.*)")
        if not image_path: return

        gt_path, _ = QFileDialog.getOpenFileName(self, f"اختر ملف النص الكتابي (Ground Truth) للصورة: {os.path.basename(image_path)}", "", "ملفات نصية (*.txt *.gt.txt);;All files (*.*)")
        if not gt_path: return

        self.training_pairs.append({'image': image_path, 'gt': gt_path})
        self.update_training_pairs_display()
        self.update_status_training(f"تمت إضافة {len(self.training_pairs)} زوج تدريب.")

    def update_training_pairs_display(self):
        for widget in self.training_pair_widgets:
            widget.deleteLater()
        self.training_pair_widgets = []

        for i, pair in enumerate(self.training_pairs):
            pair_frame = QFrame()
            pair_frame.setFrameShape(QFrame.Shape.StyledPanel)
            pair_layout = QHBoxLayout(pair_frame)
            
            img_name = os.path.basename(pair['image'])
            gt_name = os.path.basename(pair['gt'])
            
            pair_layout.addWidget(QLabel(f"صورة: {img_name}"))
            pair_layout.addWidget(QLabel(f"نص: {gt_name}"))
            pair_layout.addStretch()
            
            remove_button = QPushButton("إزالة")
            remove_button.clicked.connect(lambda checked=False, idx=i: self.remove_training_pair(idx))
            pair_layout.addWidget(remove_button)
            
            self.scroll_content_layout.addWidget(pair_frame)
            self.training_pair_widgets.append(pair_frame)

    def remove_training_pair(self, index):
        if 0 <= index < len(self.training_pairs):
            del self.training_pairs[index]
            self.update_training_pairs_display()
            self.update_status_training(f"تمت إزالة زوج. المجموع: {len(self.training_pairs)}.")

    def clear_training_pairs(self):
        reply = QMessageBox.question(self, "تأكيد", "هل أنت متأكد أنك تريد مسح جميع أزواج ملفات التدريب؟", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.training_pairs = []
            self.update_training_pairs_display()
            self.update_status_training("تم مسح قائمة ملفات التدريب.")

    def update_status_training(self, message):
        self.training_status_label.setText(f"الحالة: {message}")

    def append_to_training_log(self, text):
        self.training_log_textbox.append(text)
        self.training_log_textbox.verticalScrollBar().setValue(self.training_log_textbox.verticalScrollBar().maximum())

    def start_training(self):
        if not self.training_pairs:
            QMessageBox.critical(self, "خطأ في التدريب", "يرجى إضافة ملفات تدريب (صور ونصوصها الكتابية) أولاً.")
            return

        output_model_name = self.train_output_model_name_entry.text()
        if not output_model_name:
            QMessageBox.critical(self, "خطأ في التدريب", "يرجى تحديد اسم للنموذج الناتج.")
            return
        if not output_model_name.endswith(".mlmodel"):
            output_model_name += ".mlmodel"
            self.train_output_model_name_entry.setText(output_model_name)

        try:
            epochs = int(self.train_epochs_entry.text())
            if epochs <= 0: raise ValueError
        except ValueError:
            QMessageBox.critical(self, "خطأ في التدريب", "يرجى إدخال عدد صحيح موجب لعدد الحقب (Epochs).")
            return

        self.set_training_buttons_state(False)
        self.update_status_training(f"بدء التدريب لنموذج '{output_model_name}'...")
        self.training_log_textbox.clear()
        self.append_to_training_log(f"Starting training for model: {output_model_name} with {epochs} epochs.\n")
        self.append_to_training_log(f"Using {len(self.training_pairs)} training pairs.\n\n")

        self.run_long_task(self._perform_training_task, self.on_training_finished, output_model_name, epochs)

    def _perform_training_task(self, progress_callback, output_model_name, epochs):
        command = ["ketos", "train", "-o", output_model_name, "--epochs", str(epochs), "-f", "text"]
        for pair in self.training_pairs:
            command.append(pair['image'])
            command.append(pair['gt'])
            
        progress_callback(f"Executing command: {' '.join(command)}\n\n")

        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                   text=True, encoding='utf-8', errors='replace', 
                                   env=self.get_subprocess_env(), bufsize=1)

        for line in iter(process.stdout.readline, ''):
            progress_callback(line)
        
        process.stdout.close()
        return_code = process.wait()

        if return_code != 0:
            raise Exception(f"فشل التدريب. كود الخطأ: {return_code}")

    def on_training_finished(self, result):
        self.set_training_buttons_state(True)
        if result['success']:
            output_model_name = self.train_output_model_name_entry.text()
            self.append_to_training_log(f"\n\nالتدريب اكتمل بنجاح! النموذج المحفوظ: {output_model_name}")
            self.update_status_training(f"اكتمل التدريب. النموذج: {output_model_name}")
            QMessageBox.information(self, "اكتمل التدريب", f"تم تدريب النموذج بنجاح وحفظه باسم:\n{output_model_name}\nيمكنك الآن استخدامه في تبويب التعرف الضوئي.")
        else:
            self.append_to_training_log(f"\n\nفشل التدريب.\n{result['error']}")
            self.update_status_training("فشل التدريب.")

    def set_training_buttons_state(self, enabled):
        self.train_start_button.setEnabled(enabled)
        self.train_clear_list_button.setEnabled(enabled)

    # ===================================================================================
    # Generic Long Task Runner
    # ===================================================================================
    def run_long_task(self, task_function, on_finish_slot, *args):
        self.thread = QThread()
        self.worker = Worker(task_function, *args)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(on_finish_slot)
        self.worker.progress.connect(self.append_to_training_log) # يرسل سجل التدريب
        
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = KrakenPySideApp()
    window.show()
    sys.exit(app.exec())

