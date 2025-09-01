import sys
import os
import subprocess
import json
import requests
import threading
import tempfile
import time
import datetime
import webbrowser
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QTextEdit, QPushButton, 
                            QComboBox, QFileDialog, QSlider, QGroupBox,
                            QProgressBar, QMessageBox, QFrame, QStyle, QSizePolicy, 
                            QToolButton, QScrollArea, QSpacerItem)
from PyQt5.QtCore import Qt, QProcess, pyqtSignal, QObject, QUrl, QSize, QThread, QTimer
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtGui import QFont, QIcon, QColor, QPalette, QPixmap

# Define application paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
CONFIG_DIR = os.path.join(BASE_DIR, "configs")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
SAMPLES_DIR = os.path.join(BASE_DIR, "samples")
PIPER_EXE = os.path.join(BASE_DIR, "piper_win", "piper.exe")
ICON_PATH = os.path.join(BASE_DIR, "assets", "icon.ico")
MODELS_JSON_PATH = os.path.join(BASE_DIR, "models.json")

# Ensure directories exist
for directory in [MODELS_DIR, CONFIG_DIR, OUTPUT_DIR, SAMPLES_DIR]:
    os.makedirs(directory, exist_ok=True)

# Qualities available for voices
QUALITIES = ["x_low", "low", "medium", "high"]

# Model repository information with all English voices and qualities
MODEL_REPOSITORY = {}
if os.path.exists(MODELS_JSON_PATH):
    try:
        with open(MODELS_JSON_PATH, "r", encoding="utf-8") as f:
            MODEL_REPOSITORY = json.load(f)
        print("Model repository loaded from models.json.")
    except json.JSONDecodeError as e:
        print(f"Error decoding models.json: {e}")
    except Exception as e:
        print(f"An error occurred while loading models.json: {e}")
else:
    print("models.json not found, using an empty model repository.")


class DownloadWorker(QObject):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    status_update = pyqtSignal(str)  # New signal for status updates
    
    def __init__(self, url, save_path, description=""):
        super().__init__()
        self.url = url
        self.save_path = save_path
        self.description = description
        self.is_cancelled = False
        
    def run(self):
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.save_path), exist_ok=True)
            
            # Download with progress tracking
            response = requests.get(self.url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            block_size = 1024  # 1 Kibibyte
            downloaded = 0
            
            with open(self.save_path, 'wb') as file:
                for data in response.iter_content(block_size):
                    if self.is_cancelled:
                        file.close()
                        os.remove(self.save_path)
                        self.error.emit("Download cancelled")
                        return
                    
                    file.write(data)
                    downloaded += len(data)
                    if total_size > 0:
                        progress = int((downloaded / total_size) * 100)
                        self.progress.emit(progress)
                        if progress % 10 == 0:  # Update status every 10% progress
                            self.status_update.emit(f"Downloading {self.description} - {progress}%")
            
            self.finished.emit(self.save_path)
        except Exception as e:
            self.error.emit(str(e))

    def cancel(self):
        self.is_cancelled = True

class SUZAVoiceStudio(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SUZA Voice Studio")
        self.setMinimumSize(1100, 700)
        self.setStyleSheet(self.load_stylesheet())
        
        # Set the app icon using the .ico file
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        else:
            print(f"Warning: Icon file not found at {ICON_PATH}")
        
        # Initialize variables
        self.model_path = ""
        self.output_file = os.path.join(OUTPUT_DIR, "output.wav")
        self.process = QProcess()
        self.player = QMediaPlayer()
        self.download_threads = []
        self.models_dir = MODELS_DIR
        self.piper_exe = PIPER_EXE
        
        # Check if piper.exe exists
        if not os.path.exists(self.piper_exe):
            QMessageBox.critical(
                self,
                "Error",
                f"piper.exe not found at {self.piper_exe}. Please make sure it's in the same directory as this script."
            )
            sys.exit(1)
        
        # Set up the UI
        self.init_ui()
        
        # Populate model selection
        self.populate_model_selection()
        
    def load_stylesheet(self):
        # Improved QSS for readability and modern look
        return """
        QMainWindow {
            background: #121215;
        }
        QWidget {
            color: #e0e0e0;
            font-family: 'Segoe UI', 'Roboto', Arial, sans-serif;
            font-size: 15px;
        }
        QGroupBox {
            background: rgba(30,30,40,0.7);
            border-radius: 12px;
            border: 1px solid rgba(80,80,120,0.18);
            margin-top: 18px;
            padding: 18px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top center;
            padding: 0 5px;
            color: #FFFFFF;
            font-weight: bold;
            font-size: 15px;
        }
        QLabel {
            color: #e0e0e0;
        }
        QLabel#LogoLabel {
            font-size: 32px;
            font-weight: bold;
            color: #fff;
            letter-spacing: 2px;
            padding: 0 0 0 10px;
        }
        QLabel#AppNameLabel {
            font-size: 22px;
            color: #a0a0ff;
            font-weight: 600;
            letter-spacing: 1.5px;
        }
        QComboBox, QSlider, QLineEdit, QTextEdit {
            background: rgba(30,30,40,0.95);
            border-radius: 8px;
            border: 1px solid rgba(108, 99, 255, 0.6);
            color: #fff;
            padding: 4px 8px;
        }
        QComboBox:hover, QLineEdit:hover, QTextEdit:hover {
            border: 1px solid rgba(126, 118, 255, 0.8);
        }
        QComboBox:focus, QLineEdit:focus, QTextEdit:focus {
            border: 1px solid rgba(126, 118, 255, 1.0);
        }
        QComboBox QAbstractItemView {
            background: #23234a;
            color: #fff;
            selection-background-color: rgba(108, 99, 255, 0.7);
            selection-color: #fff;
            border: 1px solid rgba(108, 99, 255, 0.4);
            border-radius: 4px;
        }
        QTextEdit {
            min-height: 160px;
            font-size: 16px;
            padding: 18px;
        }
        QPushButton, QToolButton {
            background: rgba(35, 35, 50, 0.95);
            border-radius: 8px;
            border: 1px solid rgba(108, 99, 255, 0.6);
            color: #fff;
            font-weight: 500;
            padding: 8px 16px;
            margin: 4px;
        }
        QPushButton:hover, QToolButton:hover {
            background: rgba(45, 45, 65, 0.95);
            border: 1px solid rgba(126, 118, 255, 0.8);
        }
        QPushButton:pressed, QToolButton:pressed {
            background: rgba(30, 30, 45, 0.95);
        }
        QPushButton:disabled, QToolButton:disabled {
            background: rgba(30, 30, 45, 0.5);
            border: 1px solid rgba(80, 80, 100, 0.3);
            color: #666;
        }
        QPushButton#GenerateButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(108, 99, 255, 0.7), stop:1 rgba(58, 28, 113, 0.7));
            color: #fff;
            font-size: 16px;
            font-weight: bold;
            border: none;
            padding: 10px 20px;
        }
        QPushButton#GenerateButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(126, 118, 255, 0.8), stop:1 rgba(68, 38, 133, 0.8));
        }
        QPushButton#GenerateButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(98, 89, 235, 0.9), stop:1 rgba(48, 18, 103, 0.9));
        }
        QSlider::groove:horizontal {
            border: 1px solid rgba(60, 63, 84, 0.8);
            height: 6px;
            background: rgba(40, 43, 56, 0.8);
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: rgba(108, 99, 255, 0.8);
            border: 1px solid rgba(108, 99, 255, 0.4);
            width: 14px;
            margin: -4px 0;
            border-radius: 7px;
        }
        QSlider::handle:horizontal:hover {
            background: rgba(126, 118, 255, 0.9);
        }
        QProgressBar {
            background: rgba(35, 35, 50, 0.8);
            border-radius: 4px;
            text-align: center;
            color: #fff;
            font-size: 12px;
        }
        QProgressBar::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                                        stop:0 rgba(108, 99, 255, 0.7), 
                                        stop:1 rgba(126, 118, 255, 0.7));
            border-radius: 4px;
        }
        QFrame#topBar {
            background-color: rgba(25, 28, 37, 0.95);
            border-radius: 10px;
            border: 1px solid rgba(60, 63, 84, 0.6);
        }
        QFrame#leftPanel, QFrame#rightPanel {
            background-color: rgba(30, 33, 45, 0.85);
            border-radius: 10px;
            border: 1px solid rgba(60, 63, 84, 0.6);
        }
        """
        
    def init_ui(self):
        """Initialize the user interface"""
        # Main widget and layout
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Top bar - Logo and App Name
        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_bar.setStyleSheet("""
            #topBar {
                background-color: rgba(25, 28, 37, 0.9);
                border-radius: 10px;
                border: 1px solid rgba(60, 63, 84, 0.6);
            }
        """)
        top_bar.setMinimumHeight(60)
        top_bar.setMaximumHeight(60)
        top_bar_layout = QHBoxLayout(top_bar)
        
        # App title
        app_title = QLabel("SUZA Voice Studio")
        app_title.setStyleSheet("""
            font-size: 24px; 
            font-weight: 600; 
            color: #FFFFFF;
            letter-spacing: 1px;
        """)
        
        # Add "See More Info" button
        more_info_btn = QPushButton("See More Info")
        more_info_btn.setCursor(Qt.PointingHandCursor)
        more_info_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(108, 99, 255, 0.7);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 13px;
                font-weight: 500;
                max-width: 120px;
            }
            QPushButton:hover {
                background-color: rgba(126, 118, 255, 0.9);
            }
            QPushButton:pressed {
                background-color: rgba(90, 82, 235, 0.9);
            }
        """)
        more_info_btn.clicked.connect(self.open_more_info)
        
        top_bar_layout.addWidget(app_title)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(more_info_btn)
        
        # Main content layout (horizontal split)
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)
        
        # Left panel for voice selection
        left_panel = QFrame()
        left_panel.setObjectName("leftPanel")
        left_panel.setStyleSheet("""
            #leftPanel {
                background-color: rgba(30, 33, 45, 0.8);
                border-radius: 10px;
                border: 1px solid rgba(60, 63, 84, 0.6);
            }
        """)
        left_panel.setMinimumWidth(300)
        left_panel.setMaximumWidth(340)
        left_panel_layout = QVBoxLayout(left_panel)
        left_panel_layout.setContentsMargins(15, 15, 15, 15)
        
        # Voice control panel
        voice_group = QGroupBox("Voice Selection")
        voice_group.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                color: #FFFFFF;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 5px;
            }
        """)
        voice_layout = QVBoxLayout(voice_group)
        voice_layout.setSpacing(10)
        
        # Language selection
        language_layout = QVBoxLayout()
        language_label = QLabel("Language:")
        language_label.setStyleSheet("color: #FFFFFF;")
        self.language_combo = QComboBox()
        self.language_combo.addItem("English Great Britain", "en_GB")
        self.language_combo.addItem("English United States", "en_US")
        self.language_combo.addItem("Bahasa Indonesia Indonesia", "id_ID")
        self.language_combo.addItem("Català Spain", "ca_ES")
        self.language_combo.addItem("Cymraeg Great Britain", "cy_GB")
        self.language_combo.addItem("Dansk Denmark", "da_DK")
        self.language_combo.addItem("Deutsch Germany", "de_DE")
        self.language_combo.addItem("Español Argentina", "es_AR")
        self.language_combo.addItem("Español Mexico", "es_MX")
        self.language_combo.addItem("Español Spain", "es_ES")
        self.language_combo.addItem("Français France", "fr_FR")
        self.language_combo.addItem("Italiano Italy", "it_IT")
        self.language_combo.addItem("Kiswahili Democratic Republic of the Congo", "sw_CD")
        self.language_combo.addItem("Latviešu Latvia", "lv_LV")
        self.language_combo.addItem("Lëtzebuergesch Luxembourg", "lb_LU")
        self.language_combo.addItem("Magyar Hungary", "hu_HU")
        self.language_combo.addItem("Nederlands Belgium", "nl_BE")
        self.language_combo.addItem("Nederlands Netherlands", "nl_NL")
        self.language_combo.addItem("Norsk Norway", "no_NO")
        self.language_combo.addItem("Polski Poland", "pl_PL")
        self.language_combo.addItem("Português Brazil", "pt_BR")
        self.language_combo.addItem("Português Portugal", "pt_PT")
        self.language_combo.addItem("Română Romania", "ro_RO")
        self.language_combo.addItem("Slovenčina Slovakia", "sk_SK")
        self.language_combo.addItem("Slovenščina Slovenia", "sl_SI")
        self.language_combo.addItem("srpski Serbia", "sr_RS")
        self.language_combo.addItem("Suomi Finland", "fi_FI")
        self.language_combo.addItem("Svenska Sweden", "sv_SE")
        self.language_combo.addItem("Tiếng Việt Vietnam", "vi_VN")
        self.language_combo.addItem("Türkçe Turkey", "tr_TR")
        self.language_combo.addItem("íslenska Iceland", "is_IS")
        self.language_combo.addItem("Čeština Czech Republic", "cs_CZ")
        self.language_combo.addItem("Ελληνικά Greece", "el_GR")
        self.language_combo.addItem("Русский Russia", "ru_RU")
        self.language_combo.addItem("украї́нська мо́ва Ukraine", "uk_UA")
        self.language_combo.addItem("қазақша Kazakhstan", "kk_KZ")
        self.language_combo.addItem("עברית Israel", "he_IL")
        self.language_combo.addItem("العربية Jordan", "ar_JO")
        self.language_combo.addItem("فارسی Iran", "fa_IR")
        self.language_combo.addItem("नेपाली Nepal", "ne_NP")
        self.language_combo.addItem("हिन्दी India", "hi_IN")
        self.language_combo.addItem("తెలుగు India", "te_IN")
        self.language_combo.addItem("മലയാളം India", "ml_IN")
        self.language_combo.addItem("ქართული ენა Georgia", "ka_GE")
        self.language_combo.addItem("简体中文 China", "zh_CN")
        self.language_combo.currentIndexChanged.connect(self.update_voice_selection)
        self.language_combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(40, 43, 56, 0.8);
                color: white;
                padding: 5px;
                border-radius: 6px;
                border: 1px solid rgba(60, 63, 84, 0.8);
            }
            QComboBox:hover {
                background-color: rgba(50, 53, 68, 0.8);
                border: 1px solid rgba(80, 83, 104, 0.8);
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
        """)
        language_layout.addWidget(language_label)
        language_layout.addWidget(self.language_combo)
        
        # Voice selection
        voice_list_label = QLabel("Voice:")
        voice_list_label.setStyleSheet("color: #FFFFFF; margin-top: 10px;")
        self.voice_combo = QComboBox()
        self.voice_combo.setMinimumHeight(30)
        self.voice_combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(40, 43, 56, 0.8);
                color: white;
                padding: 8px;
                border-radius: 6px;
                border: 1px solid rgba(60, 63, 84, 0.8);
                font-size: 14px;
            }
            QComboBox:hover {
                background-color: rgba(50, 53, 68, 0.8);
                border: 1px solid rgba(80, 83, 104, 0.8);
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox QAbstractItemView {
                background-color: rgba(30, 33, 45, 0.9);
                border: 1px solid rgba(60, 63, 84, 0.8);
                selection-background-color: rgba(78, 84, 200, 0.6);
                selection-color: white;
            }
        """)
        self.voice_combo.currentIndexChanged.connect(self.update_available_qualities)
        
        # Quality selection (now appears after voice selection)
        quality_layout = QVBoxLayout()
        quality_label = QLabel("Quality:")
        quality_label.setStyleSheet("color: #FFFFFF; margin-top: 5px;")
        self.quality_combo = QComboBox()
        self.quality_combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(40, 43, 56, 0.8);
                color: white;
                padding: 5px;
                border-radius: 6px;
                border: 1px solid rgba(60, 63, 84, 0.8);
            }
            QComboBox:hover {
                background-color: rgba(50, 53, 68, 0.8);
                border: 1px solid rgba(80, 83, 104, 0.8);
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
        """)
        quality_layout.addWidget(quality_label)
        quality_layout.addWidget(self.quality_combo)
        
        # Sample voice button
        self.sample_button = QPushButton("▶ Play Sample")
        self.sample_button.setMinimumHeight(32)
        self.sample_button.setMaximumHeight(32)
        self.sample_button.clicked.connect(self.sample_button_clicked)
        self.sample_button.setEnabled(False)
        self.sample_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(40, 43, 56, 0.8);
                color: white;
                border: 1px solid rgba(60, 63, 84, 0.8);
                border-radius: 6px;
                padding: 4px;
                font-weight: 500;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: rgba(50, 53, 68, 0.8);
                border: 1px solid rgba(80, 83, 104, 0.8);
            }
            QPushButton:pressed {
                background-color: rgba(35, 38, 50, 0.8);
            }
            QPushButton:disabled {
                background-color: rgba(35, 38, 50, 0.5);
                color: #5D6379;
                border: 1px solid rgba(45, 48, 65, 0.8);
            }
        """)
        
        # Custom model selection
        model_label = QLabel("Or select custom model file:")
        model_label.setStyleSheet("color: #FFFFFF; margin-top: 15px;")
        self.model_path_label = QLabel("No model selected")
        self.model_path_label.setWordWrap(True)
        self.model_path_label.setStyleSheet("color: #8E95A9;")
        model_browse_button = QPushButton("Browse...")
        model_browse_button.clicked.connect(self.browse_model)
        model_browse_button.setMaximumHeight(28)
        model_browse_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(40, 43, 56, 0.8);
                color: white;
                border: 1px solid rgba(60, 63, 84, 0.8);
                border-radius: 6px;
                padding: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(50, 53, 68, 0.8);
                border: 1px solid rgba(80, 83, 104, 0.8);
            }
            QPushButton:pressed {
                background-color: rgba(35, 38, 50, 0.8);
            }
        """)
        
        model_browse_layout = QHBoxLayout()
        model_browse_layout.addWidget(self.model_path_label)
        model_browse_layout.addWidget(model_browse_button)
        
        # Add components to voice layout
        voice_layout.addLayout(language_layout)
        voice_layout.addWidget(voice_list_label)
        voice_layout.addWidget(self.voice_combo)
        voice_layout.addLayout(quality_layout)
        voice_layout.addWidget(self.sample_button)
        voice_layout.addWidget(model_label)
        voice_layout.addLayout(model_browse_layout)
        
        # Add to left panel
        left_panel_layout.addWidget(voice_group)
        left_panel_layout.addStretch()
        
        # Right panel for text input and controls
        right_panel = QFrame()
        right_panel.setObjectName("rightPanel")
        right_panel.setStyleSheet("""
            #rightPanel {
                background-color: rgba(30, 33, 45, 0.8);
                border-radius: 10px;
                border: 1px solid rgba(60, 63, 84, 0.6);
            }
        """)
        right_panel_layout = QVBoxLayout(right_panel)
        right_panel_layout.setContentsMargins(15, 15, 15, 15)
        
        # Text input section
        text_group = QGroupBox("Text Input")
        text_group.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                color: #FFFFFF;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 5px;
            }
        """)
        text_layout = QVBoxLayout(text_group)
        
        text_label = QLabel("Enter text to synthesize:")
        text_label.setStyleSheet("color: #FFFFFF;")
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Type or paste text here...")
        self.text_edit.setMinimumHeight(200)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: rgba(40, 43, 56, 0.8);
                color: white;
                border: 1px solid rgba(60, 63, 84, 0.8);
                border-radius: 8px;
                padding: 10px;
                font-size: 14px;
            }
            QTextEdit:focus {
                border: 1px solid rgba(80, 83, 104, 0.8);
            }
        """)
        
        text_layout.addWidget(text_label)
        text_layout.addWidget(self.text_edit)
        
        # Waveform display (placeholder)
        self.waveform = QLabel("[waveform]")
        self.waveform.setAlignment(Qt.AlignCenter)
        self.waveform.setMinimumHeight(60)
        self.waveform.setStyleSheet("""
            background-color: rgba(25, 28, 37, 0.8);
            color: #8E95A9;
            border-radius: 6px;
            border: 1px solid rgba(60, 63, 84, 0.6);
            padding: 10px;
        """)
        text_layout.addWidget(self.waveform)
        
        # Controls section
        controls_group = QGroupBox("Controls")
        controls_group.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                color: #FFFFFF;
                margin-top: 20px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 5px;
            }
        """)
        controls_layout = QVBoxLayout(controls_group)
        
        # Audio player controls
        audio_controls_layout = QHBoxLayout()
        
        self.rewind_btn = QPushButton("⏮")
        self.rewind_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(40, 43, 56, 0.8);
                color: white;
                border: 1px solid rgba(60, 63, 84, 0.8);
                border-radius: 6px;
                font-size: 16px;
                padding: 2px;
                min-width: 30px;
                max-width: 30px;
                max-height: 28px;
            }
            QPushButton:hover {
                background-color: rgba(50, 53, 68, 0.8);
                border: 1px solid rgba(80, 83, 104, 0.8);
            }
            QPushButton:pressed {
                background-color: rgba(35, 38, 50, 0.8);
            }
            QPushButton:disabled {
                background-color: rgba(35, 38, 50, 0.5);
                color: #5D6379;
                border: 1px solid rgba(45, 48, 65, 0.8);
            }
        """)
        self.rewind_btn.clicked.connect(self.rewind_audio)
        self.rewind_btn.setEnabled(False)
        
        self.duration_label = QLabel("00:00")
        self.duration_label.setStyleSheet("color: #8E95A9; min-width: 60px; text-align: center;")
        
        audio_controls_layout.addWidget(self.rewind_btn)
        audio_controls_layout.addWidget(self.duration_label)
        audio_controls_layout.addStretch()
        
        # Action buttons
        buttons_layout = QHBoxLayout()
        
        # Use a purple/indigo accent color from the image
        accent_color = "rgba(108, 99, 255, 0.9)"
        hover_color = "rgba(126, 118, 255, 0.9)"
        pressed_color = "rgba(90, 82, 235, 0.9)"
        
        self.generate_btn = QPushButton("Generate Speech")
        self.generate_btn.clicked.connect(self.generate_speech)
        self.generate_btn.setMaximumHeight(36)
        self.generate_btn.setMinimumWidth(120)
        self.generate_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {accent_color};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {pressed_color};
            }}
            QPushButton:disabled {{
                background-color: rgba(35, 38, 50, 0.5);
                color: #5D6379;
            }}
        """)
        
        self.play_btn = QPushButton("Play")
        self.play_btn.clicked.connect(self.play_audio)
        self.play_btn.setEnabled(False)
        self.play_btn.setMaximumHeight(36)
        self.play_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(40, 43, 56, 0.8);
                color: white;
                border: 1px solid rgba(60, 63, 84, 0.8);
                border-radius: 6px;
                padding: 4px 14px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(50, 53, 68, 0.8);
                border: 1px solid rgba(80, 83, 104, 0.8);
            }
            QPushButton:pressed {
                background-color: rgba(35, 38, 50, 0.8);
            }
            QPushButton:disabled {
                background-color: rgba(35, 38, 50, 0.5);
                color: #5D6379;
                border: 1px solid rgba(45, 48, 65, 0.8);
            }
        """)
        
        self.save_btn = QPushButton("Save As...")
        self.save_btn.clicked.connect(self.save_audio)
        self.save_btn.setEnabled(False)
        self.save_btn.setMaximumHeight(36)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(40, 43, 56, 0.8);
                color: white;
                border: 1px solid rgba(60, 63, 84, 0.8);
                border-radius: 6px;
                padding: 4px 14px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(50, 53, 68, 0.8);
                border: 1px solid rgba(80, 83, 104, 0.8);
            }
            QPushButton:pressed {
                background-color: rgba(35, 38, 50, 0.8);
            }
            QPushButton:disabled {
                background-color: rgba(35, 38, 50, 0.5);
                color: #5D6379;
                border: 1px solid rgba(45, 48, 65, 0.8);
            }
        """)
        
        buttons_layout.addWidget(self.generate_btn)
        buttons_layout.addWidget(self.play_btn)
        buttons_layout.addWidget(self.save_btn)
        buttons_layout.addStretch()
        
        # Progress section
        progress_layout = QVBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid rgba(60, 63, 84, 0.8);
                border-radius: 6px;
                background-color: rgba(25, 28, 37, 0.8);
                color: white;
                text-align: center;
                height: 18px;
            }
            QProgressBar::chunk {
                background-color: rgba(108, 99, 255, 0.9);
                border-radius: 6px;
            }
        """)
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("""
            color: #8E95A9;
            font-size: 13px;
            padding: 5px;
        """)
        
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.status_label)
        
        # Add layouts to controls
        controls_layout.addLayout(audio_controls_layout)
        controls_layout.addLayout(buttons_layout)
        controls_layout.addLayout(progress_layout)
        
        # Add to right panel
        right_panel_layout.addWidget(text_group)
        right_panel_layout.addWidget(controls_group)
        
        # Add panels to content layout
        content_layout.addWidget(left_panel)
        content_layout.addWidget(right_panel)
        
        # Add all sections to main layout
        main_layout.addWidget(top_bar)
        main_layout.addLayout(content_layout)
        
        # Set the main layout
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)
        
        # Initialize the sample player
        self.sample_player = QMediaPlayer()
        
        # Connect media player signals
        self.player = QMediaPlayer()
        self.player.stateChanged.connect(self.handle_player_state_change)
        
        # Apply overall window styling
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121420;
            }
        """)

    def handle_player_state_change(self, state):
        if state == QMediaPlayer.PlayingState:
            self.play_btn.setText("Pause")
            self.play_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(40, 43, 56, 0.8);
                    color: white;
                    border: 1px solid rgba(60, 63, 84, 0.8);
                    border-radius: 6px;
                    padding: 4px 14px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: rgba(50, 53, 68, 0.8);
                    border: 1px solid rgba(80, 83, 104, 0.8);
                }
                QPushButton:pressed {
                    background-color: rgba(35, 38, 50, 0.8);
                }
            """)
            self.rewind_btn.setEnabled(True)
        else:
            self.play_btn.setText("Play")
            self.play_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(40, 43, 56, 0.8);
                    color: white;
                    border: 1px solid rgba(60, 63, 84, 0.8);
                    border-radius: 6px;
                    padding: 4px 14px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: rgba(50, 53, 68, 0.8);
                    border: 1px solid rgba(80, 83, 104, 0.8);
                }
                QPushButton:pressed {
                    background-color: rgba(35, 38, 50, 0.8);
                }
            """)
            # Keep rewind enabled even when paused
            if state == QMediaPlayer.StoppedState:
                self.rewind_btn.setEnabled(False)
    
    def populate_model_selection(self):
        """Initial population of the language and voice dropdowns"""
        # Language dropdown is pre-populated
        # Populate the voices for the initially selected language
        self.update_voice_selection()
        
        # Connect combo boxes
        self.voice_combo.currentIndexChanged.connect(self.update_sample_button_state)
        self.quality_combo.currentIndexChanged.connect(self.update_sample_button_state)
        
    def update_voice_selection(self):
        """Update the voice dropdown based on the selected language"""
        self.voice_combo.clear()
        language_code = self.language_combo.currentData()
        
        if language_code in MODEL_REPOSITORY:
            for voice_id, voice_info in MODEL_REPOSITORY[language_code].items():
                self.voice_combo.addItem(voice_info["name"], voice_id)
        
        # Update sample button state
        self.update_sample_button_state()
        
        # After updating voices, update qualities for the first voice
        self.update_available_qualities()
    
    def update_available_qualities(self):
        """Update the quality dropdown based on the selected voice"""
        self.quality_combo.clear()
        
        language_code = self.language_combo.currentData()
        voice_id = self.voice_combo.currentData()
        
        if not voice_id:
            return
            
        if language_code in MODEL_REPOSITORY and voice_id in MODEL_REPOSITORY[language_code]:
            voice_info = MODEL_REPOSITORY[language_code][voice_id]
            
            if "qualities" in voice_info:
                # Get available qualities
                available_qualities = list(voice_info["qualities"].keys())
                
                # Add quality options with user-friendly display names
                for quality_id in QUALITIES:
                    if quality_id in available_qualities:
                        if quality_id == "x_low":
                            display_name = "Extra Low"
                        elif quality_id == "low":
                            display_name = "Low"
                        elif quality_id == "medium":
                            display_name = "Medium"
                        elif quality_id == "high":
                            display_name = "High"
                        else:
                            display_name = quality_id.capitalize()
                        
                        self.quality_combo.addItem(display_name, quality_id)
                
                # Set appropriate default quality
                if "medium" in available_qualities:
                    self.quality_combo.setCurrentText("Medium")
                elif "high" in available_qualities:
                    self.quality_combo.setCurrentText("High")
                elif "low" in available_qualities:
                    self.quality_combo.setCurrentText("Low")
                elif "x_low" in available_qualities:
                    self.quality_combo.setCurrentText("Extra Low")
                elif available_qualities:
                    # If none of the standard qualities are available, use the first one
                    first_quality = available_qualities[0]
                    self.quality_combo.setCurrentText(first_quality.capitalize())
                
        # Clear any custom model when voice changes
        self.clear_custom_model_on_dropdown_change()
    
    def clear_custom_model_on_dropdown_change(self):
        """Clear the custom model path when dropdown selections change"""
        # Check if the voice_combo has items. If the language was changed to one with no voices,
        # this might be called with an empty combo.
        # Or, if the signal is from language_combo, voice_combo might not be the sender.
        # We want to clear if either dropdown is interacted with.
        
        # Only print and change if model_path was actually set
        if self.model_path: # Check if there was a custom model path to clear
            print("Log: Dropdown selection changed, clearing custom model path.")
            self.model_path = ""
            self.model_path_label.setText("No model selected")
            self.waveform.setText("[waveform]")
        elif not self.model_path and self.waveform.text() != "[waveform]":
            # This case handles if model_path was already "" but label was not reset
            self.waveform.setText("[waveform]")
            self.model_path_label.setText("No model selected")

    def browse_model(self):
        """Open file dialog to select a model file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Model File", "", "ONNX Models (*.onnx)"
        )
        
        if file_path:
            self.model_path = file_path
            self.waveform.setText(os.path.basename(file_path))
    
    def get_model_path_for_voice(self, language_code, voice_id):
        """Get the local path for a voice model"""
        if language_code in MODEL_REPOSITORY and voice_id in MODEL_REPOSITORY[language_code]:
            voice_info = MODEL_REPOSITORY[language_code][voice_id]
            
            # Get current quality selection
            quality = self.quality_combo.currentData()
            
            # Check if this voice has the selected quality
            if "qualities" in voice_info and quality in voice_info["qualities"]:
            # Remove query string from filename
                url = voice_info["qualities"][quality]["url"]
            filename = os.path.basename(url.split('?', 1)[0])
            return os.path.join(self.models_dir, language_code, voice_id, filename)
            
            # Quality not available, try to find any available quality
            if "qualities" in voice_info and voice_info["qualities"]:
                # Use the first available quality as fallback
                first_quality = list(voice_info["qualities"].keys())[0]
                url = voice_info["qualities"][first_quality]["url"]
                filename = os.path.basename(url.split('?', 1)[0])
                
                # Update UI to show the selected quality
                quality_index = self.quality_combo.findData(first_quality)
                if quality_index >= 0:
                    self.quality_combo.setCurrentIndex(quality_index)
                
                self.status_label.setText(f"Selected quality not available for {voice_id}, using {first_quality} instead")
                return os.path.join(self.models_dir, language_code, voice_id, filename)
        
        self.status_label.setText(f"Error: Could not find model for {voice_id}")
        return None
    
    def check_model_downloaded(self, language_code, voice_id):
        """Check if a model has been downloaded"""
        model_path = self.get_model_path_for_voice(language_code, voice_id)
        if model_path:
            return os.path.exists(model_path)
        return False
    
    def download_model(self, language_code, voice_id):
        """Download a model if it's not already downloaded"""
        if language_code not in MODEL_REPOSITORY or voice_id not in MODEL_REPOSITORY[language_code]:
            self.status_label.setText(f"Error: Model {voice_id} not found in repository")
            return False
        
        voice_info = MODEL_REPOSITORY[language_code][voice_id]
        
        # Get selected quality
        quality = self.quality_combo.currentData()
        
        # Check if quality exists for this voice, otherwise use fallback
        if "qualities" not in voice_info or quality not in voice_info["qualities"]:
            # Use first available quality as fallback
            quality = list(voice_info["qualities"].keys())[0]
            quality_name = quality.capitalize()
            self.status_label.setText(f"Selected quality not available, using {quality_name} quality instead")
        
        model_url = voice_info["qualities"][quality]["url"]
        config_url = voice_info["qualities"][quality]["config_url"]
        
        # Get the model path (will handle fallback qualities if needed)
        model_path = self.get_model_path_for_voice(language_code, voice_id)
        config_path = model_path + ".json"
        
        # Show download notification
        QMessageBox.information(
            self,
            "Model Download",
            f"The model '{voice_info['name']}' needs to be downloaded. This may take a few minutes depending on your internet connection."
        )
        
        # Set up progress display
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setText(f"Downloading {voice_info['name']}...")
        self.generate_btn.setEnabled(False)
        
        # Download model file
        self.download_worker = DownloadWorker(model_url, model_path, voice_info["name"])
        self.download_thread = threading.Thread(target=self.download_worker.run)
        
        # Connect signals
        self.download_worker.progress.connect(self.update_download_progress)
        self.download_worker.finished.connect(lambda: self.download_config(config_url, config_path, voice_info['name']))
        self.download_worker.error.connect(self.handle_download_error)
        
        # Start download
        self.download_thread.start()
        self.download_threads.append(self.download_thread)
        
        return True
    
    def download_config(self, config_url, config_path, voice_name):
        """Download the config file for a model"""
        self.status_label.setText(f"Downloading configuration for {voice_name}...")
        
        try:
            response = requests.get(config_url)
            response.raise_for_status()
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            with open(config_path, 'wb') as file:
                file.write(response.content)
            
            self.download_complete(voice_name)
        except Exception as e:
            self.handle_download_error(str(e))
    
    def update_download_progress(self, progress):
        """Update the progress bar during download"""
        self.progress_bar.setValue(progress)
    
    def download_complete(self, voice_name):
        """Handle completion of model download"""
        print(f"Log: Download complete for {voice_name}")
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Model {voice_name} downloaded successfully")
        self.generate_btn.setEnabled(True)
        
        # Proceed with speech generation
        print(f"Log: Triggering generate_speech after download of {voice_name}")
        self.generate_speech()
    
    def handle_download_error(self, error_message):
        """Handle errors during model download"""
        print(f"Log: Download error: {error_message}")
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Error downloading model: {error_message}")
        self.generate_btn.setEnabled(True)
        
        QMessageBox.critical(
            self,
            "Download Error",
            f"Failed to download model: {error_message}"
        )
    
    def generate_speech(self):
        """Generate speech using the Piper TTS engine"""
        print("Log: generate_speech called")
        # Get the text to synthesize
        text_to_synthesize = self.text_edit.toPlainText().strip()
        if not text_to_synthesize:
            self.status_label.setText("Error: No text to synthesize")
            print("Log: Error - No text to synthesize")
            return
        print(f"Log: Text to synthesize: '{text_to_synthesize[:50]}...'")
        
        # Generate a unique filename based on voice and text
        language_code = self.language_combo.currentData()
        voice_id = self.voice_combo.currentData()
        
        # Create a safe filename from the first few words of text
        text_part = text_to_synthesize.split()[:3]  # First 3 words
        text_part = "_".join(text_part).lower()
        # Remove special characters
        text_part = ''.join(c if c.isalnum() or c == '_' else '' for c in text_part)
        
        # Limit length
        if len(text_part) > 30:
            text_part = text_part[:30]
        
        # Format: voice_textexcerpt_timestamp.wav
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{voice_id}_{text_part}_{timestamp}.wav"
        self.output_file = os.path.join(OUTPUT_DIR, filename)
        
        # Get the model path
        current_model_path = self.model_path # Use a local variable for clarity in this function
        if not current_model_path:
            print("Log: No custom model path set, using selected voice.")
            
            if not voice_id:
                self.status_label.setText("Error: No voice selected")
                print("Log: Error - No voice selected")
                return
            print(f"Log: Selected language: {language_code}, voice: {voice_id}")
            
            if not self.check_model_downloaded(language_code, voice_id):
                print(f"Log: Model for {language_code}/{voice_id} not downloaded. Starting download.")
                self.download_model(language_code, voice_id)
                return 
            
            current_model_path = self.get_model_path_for_voice(language_code, voice_id)
            print(f"Log: Using downloaded model: {current_model_path}")
        else:
            print(f"Log: Using custom model path: {current_model_path}")
        
        if not current_model_path or not os.path.exists(current_model_path):
            self.status_label.setText(f"Error: Model file not found at {current_model_path}")
            print(f"Log: Error - Model file not found at {current_model_path}")
            return
        
        self.status_label.setText("Generating speech...")
        self.generate_btn.setEnabled(False)
        print("Log: UI updated - 'Generating speech...', button disabled.")
        
        # No longer creating a temporary file for text input.
        # self.temp_path will not be used with stdin approach.
        if hasattr(self, 'temp_path') and self.temp_path:
             # Clean up any old temp file if it exists from previous runs/logic
            try:
                if os.path.exists(self.temp_path):
                    os.remove(self.temp_path)
                    print(f"Log: Cleaned up old temp file: {self.temp_path}")
                self.temp_path = None
            except Exception as e_clean:
                print(f"Log: Error cleaning up old temp file {self.temp_path}: {e_clean}")

        # Parameters are removed, use fixed defaults
        command_args = [
            "--model", current_model_path,
            "--output_file", os.path.abspath(self.output_file)
        ]
        
        print(f"Log: Starting QProcess with: {self.piper_exe} {' '.join(command_args)} (text via stdin)")
        
        piper_dir = os.path.dirname(self.piper_exe)
        self.process.setWorkingDirectory(piper_dir)
        print(f"Log: Set QProcess working directory to: {piper_dir}")

        # Connect process signals for monitoring
        self.process.finished.connect(self.process_finished)

        self.process.start(
            self.piper_exe,
            command_args
        )
        
        if not self.process.waitForStarted(5000):
            error_string = self.process.errorString()
            self.status_label.setText(f"Error starting Piper: {error_string}")
            print(f"Log: Failed to start QProcess. Error: {error_string}")
            self.generate_btn.setEnabled(True)
            return
        
        print("Log: QProcess started successfully.")
        
        # Write text to piper.exe's stdin
        print("Log: Writing text to process stdin...")
        self.process.write(text_to_synthesize.encode('utf-8'))
        # Close the write channel (stdin) to signal end of input
        self.process.closeWriteChannel()
        print("Log: Closed QProcess write channel (stdin) after writing text.")

    def process_finished(self, exit_code, exit_status):
        print(f"Log: process_finished called. Exit code: {exit_code}, Exit status: {exit_status}")
        
        # No temporary file to clean up with stdin approach for text input
        # The self.temp_path logic was removed from generate_speech for this path.

        self.generate_btn.setEnabled(True)
        print("Log: Generate button re-enabled.")
        
        if exit_code == 0:
            # Check if the output file was actually created and is not empty
            output_file_exists = os.path.exists(self.output_file)
            output_file_size = os.path.getsize(self.output_file) if output_file_exists else 0
            
            print(f"Log: Piper process finished successfully. Checking output file: {self.output_file}")
            print(f"Log: Output file exists: {output_file_exists}, Size: {output_file_size} bytes")

            if output_file_exists and output_file_size > 0:
                self.status_label.setText("Speech generated successfully")
                self.play_btn.setEnabled(True)
                self.save_btn.setEnabled(True)
                print("Log: Speech generated successfully. Output file valid. Play/Save buttons enabled.")
            else:
                self.status_label.setText(f"Error: Speech generation reported success, but output file is missing or empty ({self.output_file})")
                self.play_btn.setEnabled(False)
                self.save_btn.setEnabled(False)
                print(f"Log: Error - Piper reported success, but output file d:\Developer\Windows\Piper\output\output.wav is missing or empty.")
        else:
            # Try to get more error details if QProcess captured some
            error_output = self.process.readAllStandardError().data().decode(errors="replace").strip()
            error_string = self.process.errorString() # QProcess specific error like "crashed"
            
            status_message = f"Error: Process exited with code {exit_code} (Status: {exit_status})"
            if error_output:
                status_message += f"\nPiper stderr: {error_output}"
                print(f"Log: Piper stderr on error: {error_output}")
            if error_string and error_string.lower() != "unknown error": # QProcess error string
                 status_message += f"\nProcess error: {error_string}"
                 print(f"Log: QProcess errorString: {error_string}")

            self.status_label.setText(status_message)
            print(f"Log: Process finished with error. UI updated.")
    
    def play_audio(self):
        """Play the generated audio"""
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
            return
            
        abs_output_file = os.path.abspath(self.output_file)
        print(f"Log: play_audio called. Checking for file: {abs_output_file}")
        if os.path.exists(abs_output_file) and os.path.getsize(abs_output_file) > 0:
            print(f"Log: File found for playback: {abs_output_file}")
            content = QMediaContent(QUrl.fromLocalFile(abs_output_file))
            if content.isNull():
                print(f"Log: QMediaContent is null for {abs_output_file}. The file might be corrupted or an unsupported format for QMediaPlayer.")
                self.status_label.setText(f"Error: Cannot create media content for {os.path.basename(abs_output_file)}. File might be invalid.")
                return

            self.player.setMedia(content)
            
            # Check player status and error
            if self.player.error() != QMediaPlayer.NoError:
                print(f"Log: QMediaPlayer error before play: {self.player.errorString()}")
                self.status_label.setText(f"Player Error: {self.player.errorString()}")

            self.player.play()
            print(f"Log: Play command issued. Player state: {self.player.state()}")
        else:
            print(f"Log: Play audio - file not found or empty at {abs_output_file}")
            self.status_label.setText(f"Error: Output file not found or empty at {os.path.basename(abs_output_file)}")
    
    def save_audio(self):
        """Save the generated audio to a user-specified location"""
        abs_output_file = os.path.abspath(self.output_file)
        print(f"Log: save_audio called. Checking for file: {abs_output_file}")
        if not os.path.exists(abs_output_file) or os.path.getsize(abs_output_file) == 0:
            self.status_label.setText("Error: No audio file to save (missing or empty)")
            print(f"Log: Save audio - file not found or empty at {abs_output_file}")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Audio File", "", "WAV Files (*.wav);;All Files (*.*)"
        )
        
        if file_path:
            # Copy the output file to the selected location
            try:
                with open(self.output_file, 'rb') as src_file:
                    with open(file_path, 'wb') as dst_file:
                        dst_file.write(src_file.read())
                
                self.status_label.setText(f"Audio saved to {file_path}")
            except Exception as e:
                self.status_label.setText(f"Error saving audio: {str(e)}")
    
    def check_cuda_support(self):
        """Check if CUDA is available for Piper"""
        # For simplicity, we'll assume CUDA is not available
        # This could be enhanced to actually check for CUDA support
        return False

    def reset_fields(self):
        self.text_edit.clear()
        self.speed_slider.setValue(100)
        self.pitch_slider.setValue(0)
        self.emotion_slider.setValue(50)
        self.format_combo.setCurrentIndex(0)
        self.status_label.setText("Ready")
        self.waveform.setText("[waveform]")

    def rewind_audio(self):
        self.player.setPosition(0)
        self.duration_label.setText("00:00")

    def sample_button_clicked(self):
        """Handle sample button clicks with play/stop toggle functionality"""
        # If player is already playing, stop it
        if self.sample_player.state() == QMediaPlayer.PlayingState:
            self.sample_player.stop()
            self.sample_button.setText("▶ Play Sample")
            self.status_label.setText("Ready")
            return
            
        # Otherwise play the sample
        self.play_voice_sample()

    def play_voice_sample(self):
        """Play a sample of the selected voice from local samples folder"""
        language_code = self.language_combo.currentData()
        voice_id = self.voice_combo.currentData()
        quality = self.quality_combo.currentData()
        
        if not language_code or not voice_id:
            self.status_label.setText("No voice selected")
            return
            
        # Update status
        voice_name = MODEL_REPOSITORY[language_code][voice_id]["name"] if language_code in MODEL_REPOSITORY and voice_id in MODEL_REPOSITORY[language_code] else voice_id
        self.status_label.setText(f"Playing sample of {voice_name}...")
        self.sample_button.setText("⏹ Stop")
        
        # First try to play from local samples
        sample_path = os.path.join(SAMPLES_DIR, "en", language_code, voice_id, quality, "samples", "speaker_0.mp3")
        if os.path.exists(sample_path):
            try:
                media_content = QMediaContent(QUrl.fromLocalFile(sample_path))
                self.sample_player.setMedia(media_content)
                self.sample_player.play()
                print(f"Log: Playing local sample from {sample_path}")
                return
            except Exception as e:
                print(f"Log: Error playing local sample: {str(e)}")
                # Continue to try online sample if local fails
            
        # If local sample not found or failed, try online sample
        if language_code in MODEL_REPOSITORY and voice_id in MODEL_REPOSITORY[language_code]:
            voice_info = MODEL_REPOSITORY[language_code][voice_id]
            
            # Try to get sample URL for current quality
            sample_url = voice_info.get("sample_url", "")
            if sample_url:
                try:
                    # Create a QMediaContent from the URL
                    media_content = QMediaContent(QUrl(sample_url))
                    self.sample_player.setMedia(media_content)
                    self.sample_player.play()
                    print(f"Log: Playing online sample from {sample_url}")
                    
                    # Connect error handler
                    self.sample_player.error.connect(lambda: self.status_label.setText(f"Error playing sample: {self.sample_player.errorString()}"))
                except Exception as e:
                    print(f"Log: Error playing online sample: {str(e)}")
                    self.status_label.setText(f"Error playing sample: {str(e)}")
            else:
                self.status_label.setText(f"No sample available for {voice_name}")
        else:
            self.status_label.setText(f"No sample available for {voice_name}")
    
    def handle_sample_error(self, error_message):
        """Handle errors during sample playback"""
        self.status_label.setText(error_message)
        self.sample_button.setText("▶ Play Sample")
        print(f"Log: Sample playback error: {error_message}")
    
    def handle_sample_playback_state(self, state):
        """Handle sample player state changes"""
        if state == QMediaPlayer.StoppedState:
            self.sample_button.setText("▶ Play Sample")
            self.status_label.setText("Ready")
        elif state == QMediaPlayer.PlayingState:
            self.sample_button.setText("⏹ Stop")

    def update_sample_button_state(self):
        """Update the state of the sample button based on the selected voice"""
        language_code = self.language_combo.currentData()
        voice_id = self.voice_combo.currentData()
        
        if language_code and voice_id:
            # Check for sample URL
            sample_available = False
            if language_code in MODEL_REPOSITORY and voice_id in MODEL_REPOSITORY[language_code]:
                if "sample_url" in MODEL_REPOSITORY[language_code][voice_id]:
                    sample_available = True
            
            self.sample_button.setEnabled(sample_available)
        else:
            self.sample_button.setEnabled(False)

    def open_more_info(self):
        """Open the SUZA Voice Studio website"""
        webbrowser.open("https://suzagear.com/voicestudio")

def main():
    app = QApplication(sys.argv)
    window = SUZAVoiceStudio()
    window.show()  # Ensure the window is shown
    sys.exit(app.exec_())  # Start the Qt event loop

if __name__ == "__main__":
    main()
