#!/usr/bin/env python3

import sys, os
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QFileDialog, QPushButton, QVBoxLayout, QWidget,
    QLabel, QSlider, QInputDialog, QHeaderView
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QShortcut, QKeySequence

if getattr(sys, 'frozen', False):
    os.environ['VLC_PLUGIN_PATH'] = os.path.join(sys._MEIPASS, 'vlc', 'plugins')

import vlc


class LyricWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LRC Maker")
        self.resize(600, 800)
        self.add_end_timestamp = True

        # ----- Layout -----
        central = QWidget()
        self.layout = QVBoxLayout()
        central.setLayout(self.layout)
        self.setCentralWidget(central)

        # ----- Table -----
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Time", "Lyric"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.enter_edit_mode)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.cellClicked.connect(self.set_current_row)
        self.layout.addWidget(self.table)

        # ----- Controls -----
        self.play_button = QPushButton("Play / Pause")
        self.play_button.clicked.connect(self.toggle_play)
        self.layout.addWidget(self.play_button)

        self.select_folder_button = QPushButton("Select Folder")
        self.select_folder_button.clicked.connect(self.select_folder)
        self.layout.addWidget(self.select_folder_button)

        self.select_song_button = QPushButton("Select Song")
        self.select_song_button.clicked.connect(self.select_song_from_current_folder)
        self.select_song_button.setEnabled(False)
        self.layout.addWidget(self.select_song_button)

        self.export_button = QPushButton("Export .lrc")
        self.export_button.clicked.connect(self.export_lrc)
        self.layout.addWidget(self.export_button)

        self.time_label = QLabel("00:00.00")
        self.layout.addWidget(self.time_label)

        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.sliderMoved.connect(self.seek_position)
        self.layout.addWidget(self.seek_slider)
        
        self.toggle_end_button = QPushButton("Toggle Final Timestamp: ON")
        self.toggle_end_button.clicked.connect(self.toggle_end_timestamp)
        self.layout.addWidget(self.toggle_end_button)


        # ----- Slider -----
        self.user_seeking = False
        self.seek_slider.sliderPressed.connect(lambda: setattr(self, 'user_seeking', True))
        self.seek_slider.sliderReleased.connect(lambda: setattr(self, 'user_seeking', False))

        # ----- Shortcuts -----
        QShortcut(QKeySequence("Space"), self).activated.connect(self.advance_row)
        QShortcut(QKeySequence("Backspace"), self).activated.connect(self.retime_previous_row)
        QShortcut(QKeySequence(","), self).activated.connect(self.rewind_5s)
        QShortcut(QKeySequence("."), self).activated.connect(self.replay_line)

        # ----- State -----
        self.current_row = 0
        self.player = None
        self.base_name = ""
        self.folder = ""
        self.cached_matches = []

        # ----- Timer -----
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_time_label)
        self.timer.start(50)
        
    # ---------- Folder Loading ----------
    
    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select folder")
        if not folder:
            return

        self.folder = folder
        self.select_song_button.setEnabled(True)
        self.cached_matches = self.scan_folder(folder)
        self.select_song_from_current_folder()

    # ---------- Song Loading ----------

    def select_song_from_current_folder(self):
        if not self.folder:
            return

        matches = self.cached_matches
        if not matches:
            return

        items = [os.path.basename(txt) for txt, _ in self.cached_matches]
        choice, ok = QInputDialog.getItem(
            self, "Select Lyrics", "Pick lyrics file:", items, 0, False
        )
        if not ok:
            return

        lyrics_file, audio_file = self.cached_matches[items.index(choice)]
        self.load_session(lyrics_file, audio_file)


    def load_session(self, lyrics_file, audio_file):
        self.load_txt(lyrics_file)

        self.base_name = os.path.splitext(os.path.basename(lyrics_file))[0]
        self.folder = os.path.dirname(lyrics_file)
        self.setWindowTitle(f"LRC Maker - {os.path.basename(self.folder)}")

        if self.player:
            self.player.stop()

        self.player = vlc.MediaPlayer(audio_file)
        self.player.video_set_key_input(False)
        self.player.video_set_mouse_input(False)
        
        events = self.player.event_manager()
        events.event_attach(
            vlc.EventType.MediaPlayerEndReached,
            lambda event: QTimer.singleShot(0, self.song_finished)
        )

        self.player.play()
        self.player.pause()

        self.current_row = 0
        self.table.selectRow(0)

    # ---------- File Matching ----------

    def scan_folder(self, folder):
        txt_files = [f for f in os.listdir(folder) if f.lower().endswith(".txt")]
        audio_files = [f for f in os.listdir(folder) if f.lower().endswith((".mp3", ".wav", ".flac"))]

        matches = []
        for txt in txt_files:
            txt_base = os.path.splitext(txt)[0].lower()
            for audio in audio_files:
                audio_base = os.path.splitext(audio)[0].lower()
                if txt_base in audio_base or audio_base in txt_base:
                    matches.append((os.path.join(folder, txt), os.path.join(folder, audio)))

        return matches

    # ---------- Lyrics ----------

    def load_txt(self, path):
        with open(path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]

        self.table.setRowCount(len(lines))
        for i, line in enumerate(lines):
            self.table.setItem(i, 0, QTableWidgetItem("00:00.00"))
            self.table.setItem(i, 1, QTableWidgetItem(line))

            header = self.table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

            self.table.setColumnWidth(0, 100)
            self.table.resizeRowsToContents()

    # ---------- Editing ----------
    
    def enter_edit_mode(self, row, column):
        if column == 1:
            self.table.editItem(self.table.item(row, column))

    # ---------- Timing ----------

    def update_time_label(self):
        if not self.player:
            return

        ms = self.player.get_time()
        if ms < 0:
            return

        minutes = ms // 60000
        seconds = (ms % 60000) // 1000
        hundredths = (ms % 1000) // 10

        length = self.player.get_length()
        if length > 0:
            total_m = length // 60000
            total_s = (length % 60000) // 1000
            self.time_label.setText(
                f"{minutes:02}:{seconds:02}.{hundredths:02} / {total_m:02}:{total_s:02}"
            )

            self.seek_slider.setMaximum(length)
            if not self.user_seeking:
                self.seek_slider.setValue(ms)

    def seek_position(self, position):
        if self.player:
            self.player.set_time(position)
            
    def toggle_end_timestamp(self):
        self.add_end_timestamp = not self.add_end_timestamp
        state = "ON" if self.add_end_timestamp else "OFF"
        self.toggle_end_button.setText(f"Toggle Final Timestamp: {state}")
        
    def add_final_timestamp(self):
        length = self.player.get_length()
        if length <= 0:
            return

        minutes = length // 60000
        seconds = (length % 60000) // 1000
        hundredths = (length % 1000) // 10
        timestamp = f"{minutes:02}:{seconds:02}.{hundredths:02}"
        
        last_row = self.table.rowCount() - 1
        if last_row >= 0:
            existing = self.table.item(last_row, 0).text()
            if existing == timestamp:
                return

        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(timestamp))
        self.table.setItem(row, 1, QTableWidgetItem(""))
        
    # ---------- Row Control ----------

    def set_current_row(self, row, column):
        self.current_row = row
        self.table.selectRow(row)

    def advance_row(self):
        if not self.player or self.current_row >= self.table.rowCount():
            return

        ms = self.player.get_time()
        minutes = ms // 60000
        seconds = (ms % 60000) // 1000
        hundredths = (ms % 1000) // 10
        timestamp = f"{minutes:02}:{seconds:02}.{hundredths:02}"

        self.table.setItem(self.current_row, 0, QTableWidgetItem(timestamp))
        self.current_row += 1

        if self.current_row < self.table.rowCount():
            self.table.selectRow(self.current_row)
            self.table.scrollToItem(self.table.item(self.current_row, 1))

    def retime_previous_row(self):
        if self.current_row > 0:
            self.current_row -= 1
            self.table.selectRow(self.current_row)
            self.table.setItem(self.current_row, 0, QTableWidgetItem("00:00.00"))

    # ---------- Playback Helpers ----------

    def toggle_play(self):
        if not self.player:
            return
        if self.player.is_playing():
            self.player.pause()
        else:
            self.player.play()

    def rewind_5s(self):
        if self.player:
            self.player.set_time(max(0, self.player.get_time() - 5000))

    def replay_line(self):
        if self.current_row == 0:
            return
        ts = self.table.item(self.current_row - 1, 0).text()
        m, s = ts.split(":")
        s, h = s.split(".")
        ms = (int(m) * 60 + int(s)) * 1000 + int(h) * 10
        self.player.set_time(ms)
        
    def song_finished(self):
        if not self.player:
            return

        if self.add_end_timestamp:
            self.add_final_timestamp()

        self.player.stop()
        self.player.set_time(0)

    # ---------- Export ----------

    def export_lrc(self):
        if self.table.rowCount() == 0:
            return

        default_path = os.path.join(self.folder, f"{self.base_name}.lrc")
        path, _ = QFileDialog.getSaveFileName(self, "Save LRC", default_path, "LRC files (*.lrc)")
        if not path:
            return

        lines = []
        for row in range(self.table.rowCount()):
            ts = self.table.item(row, 0).text()
            lyric = self.table.item(row, 1).text()
            lines.append(f"[{ts}]{lyric}")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


app = QApplication(sys.argv)
window = LyricWindow()
window.show()
sys.exit(app.exec())
