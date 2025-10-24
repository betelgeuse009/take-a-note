import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QLineEdit, QPushButton, QListWidget, 
                           QTextEdit, QProgressBar, QLabel, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
import os
import requests
import feedparser
import whisper
from dotenv import load_dotenv

class TranscriptionWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(str, str)
    error = pyqtSignal(str)

    def __init__(self, audio_path):
        super().__init__()
        self.audio_path = audio_path

    def run(self):
        try:
            self.progress.emit("Loading Whisper model...")
            model = whisper.load_model("tiny")
            
            self.progress.emit("Transcribing audio...")
            result = model.transcribe(self.audio_path, fp16=False)
            
            # Format transcription
            lines = [seg["text"].strip() for seg in result["segments"]]
            formatted = "\n".join(lines)
            
            # Save transcription
            base_name = os.path.splitext(os.path.basename(self.audio_path))[0]
            txt_out = os.path.join("transcriptions", f"{base_name}.txt")
            
            with open(txt_out, "w", encoding="utf-8") as out:
                out.write(formatted)
            
            self.finished.emit(formatted, txt_out)
        except Exception as e:
            self.error.emit(str(e))

class DownloadWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, url, filename):
        super().__init__()
        self.url = url
        self.filename = filename

    def run(self):
        try:
            filepath = os.path.join("downloads", self.filename)
            self.progress.emit(f"Downloading: {self.filename}")
            
            with requests.get(self.url, stream=True) as resp:
                resp.raise_for_status()
                with open(filepath, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            self.finished.emit(filepath)
        except Exception as e:
            self.error.emit(str(e))

class PodcastTranscriberGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Podcast Transcriber")
        self.setMinimumSize(800, 600)
        
        # Load environment variables
        load_dotenv()
        self.api_key = os.getenv('API_KEY')
        self.api_secret = os.getenv('API_SECRET')
        
        if not self.api_key or not self.api_secret:
            QMessageBox.warning(self, "Configuration Error", 
                              "API keys not found. Please set them in .env file")
        
        # Create directories
        os.makedirs("downloads", exist_ok=True)
        os.makedirs("transcriptions", exist_ok=True)
        
        self.setup_ui()
    
    def setup_ui(self):
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # Search section
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search query...")
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search_podcasts)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_button)
        layout.addLayout(search_layout)
        
        # Results list
        self.results_list = QListWidget()
        self.results_list.itemDoubleClicked.connect(self.show_episodes)
        layout.addWidget(QLabel("Search Results (double-click to show episodes):"))
        layout.addWidget(self.results_list)
        
        # Episodes list
        self.episodes_list = QListWidget()
        self.episodes_list.itemDoubleClicked.connect(self.download_episode)
        layout.addWidget(QLabel("Episodes (double-click to download and transcribe):"))
        layout.addWidget(self.episodes_list)
        
        # Progress bar
        self.progress_label = QLabel("Status:")
        layout.addWidget(self.progress_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v%")
        layout.addWidget(self.progress_bar)
        
        # Transcription display
        layout.addWidget(QLabel("Transcription:"))
        self.transcription_display = QTextEdit()
        self.transcription_display.setReadOnly(True)
        layout.addWidget(self.transcription_display)
        
        # Store feed data
        self.current_feed = None
        self.current_episodes = []
    
    def search_podcasts(self):
        if not self.api_key or not self.api_secret:
            QMessageBox.warning(self, "Error", "API keys not configured")
            return
        
        query = self.search_input.text().strip()
        if not query:
            QMessageBox.warning(self, "Error", "Please enter a search query")
            return
        
        # Clear previous results
        self.results_list.clear()
        self.episodes_list.clear()
        self.transcription_display.clear()
        
        try:
            import hashlib
            import time
            
            url = f"https://api.podcastindex.org/api/1.0/search/byterm?q={query}"
            epoch_time = int(time.time())
            data_to_hash = self.api_key + self.api_secret + str(epoch_time)
            sha_1 = hashlib.sha1(data_to_hash.encode()).hexdigest()
            
            headers = {
                'X-Auth-Date': str(epoch_time),
                'X-Auth-Key': self.api_key,
                'Authorization': sha_1,
                'User-Agent': 'postcasting-index-python-gui'
            }
            
            r = requests.post(url, headers=headers)
            r.raise_for_status()
            
            data = r.json()
            feeds = data.get("feeds", [])
            
            if not feeds:
                QMessageBox.information(self, "No Results", "No podcasts found")
                return
            
            for feed in feeds:
                self.results_list.addItem(feed["title"])
            
            self.current_feed = feeds
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Search failed: {str(e)}")
    
    def show_episodes(self, item):
        feed_index = self.results_list.row(item)
        feed_data = self.current_feed[feed_index]
        rss_feed = feed_data["url"]
        
        try:
            parsed = feedparser.parse(rss_feed)
            self.episodes_list.clear()
            
            if not parsed.entries:
                QMessageBox.information(self, "No Episodes", "No episodes found")
                return
            
            self.current_episodes = parsed.entries[:10]
            for entry in self.current_episodes:
                self.episodes_list.addItem(entry.title)
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to fetch episodes: {str(e)}")
    
    def download_episode(self, item):
        episode_index = self.episodes_list.row(item)
        entry = self.current_episodes[episode_index]
        
        try:
            audio_url = entry.enclosures[0].href if entry.enclosures else None
            if not audio_url:
                QMessageBox.warning(self, "Error", "No audio found for this episode")
                return
            
            filename = os.path.basename(audio_url.split("?")[0])
            
            # Start download worker
            self.download_worker = DownloadWorker(audio_url, filename)
            self.download_worker.progress.connect(self.update_progress)
            self.download_worker.finished.connect(self.start_transcription)
            self.download_worker.error.connect(self.show_error)
            self.download_worker.start()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to process episode: {str(e)}")
    
    def start_transcription(self, audio_path):
        self.transcription_worker = TranscriptionWorker(audio_path)
        self.transcription_worker.progress.connect(self.update_progress)
        self.transcription_worker.finished.connect(self.show_transcription)
        self.transcription_worker.error.connect(self.show_error)
        self.transcription_worker.start()
    
    def update_progress(self, message):
        self.progress_label.setText(f"Status: {message}")
    
    def show_transcription(self, text, path):
        self.transcription_display.setText(text)
        self.progress_label.setText(f"Status: Transcription saved to {path}")
    
    def show_error(self, message):
        QMessageBox.critical(self, "Error", message)
        self.progress_label.setText("Status: Error occurred")

def closeEvent(self, event):
        # Cleanup any running workers
        if hasattr(self, 'download_worker') and self.download_worker.isRunning():
            self.download_worker.terminate()
            self.download_worker.wait()
        if hasattr(self, 'transcription_worker') and self.transcription_worker.isRunning():
            self.transcription_worker.terminate()
            self.transcription_worker.wait()
        event.accept()

def main():
    app = QApplication(sys.argv)
    window = PodcastTranscriberGUI()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()