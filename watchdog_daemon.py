import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# 기존 하이브리드 스캐너에서 함수를 가져옵니다.
from hybrid_scanner import run_test_scan

MASTER_PATH = r"G:\내 드라이브\메이커몬\관리도면"

class MakerMoneHandler(FileSystemEventHandler):
    def __init__(self):
        self.last_triggered = 0

    def on_created(self, event):
        # 폴더 생성은 무시합니다.
        if event.is_directory:
            return

        # PDF나 STEP 파일이 새로 생성되었을 때만 반응합니다.
        if event.src_path.lower().endswith(('.pdf', '.step')):
            current_time = time.time()
            
            # [Debounce 방어막] 동일한 파일이나 여러 파일이 쏟아질 때 
            # 10초 이내의 중복 트리거를 방지하여 서버 과부하를 막습니다.
            if current_time - self.last_triggered > 10:
                self.last_triggered = current_time
                print(f"\n👀 [Watchdog] 새로운 도면 감지: {os.path.basename(event.src_path)}")
                
                # 구글 드라이브 동기화(파일 쓰기)가 완전히 끝날 때까지 5초간 대기합니다.
                print("⏳ 파일 동기화 대기 중 (5초)...")
                time.sleep(5) 
                
                try:
                    print("🚀 하이브리드 스캐너를 자동 가동합니다!")
                    # 이미 캐시(scan_history.json)가 있으므로 351건은 0.1초 만에 스킵하고 신규 도면만 쏘게 됩니다.
                    run_test_scan(MASTER_PATH)
                except Exception as e:
                    print(f"❌ 자동 스캔 중 오류 발생: {e}")

def start_daemon():
    event_handler = MakerMoneHandler()
    observer = Observer()
    observer.schedule(event_handler, MASTER_PATH, recursive=True)
    observer.start()
    
    print("="*60)
    print("🛡️ [메이커몬 Zero-Touch 팩토리] Watchdog 데몬 가동 시작...")
    print(f"📂 감시 경로: {MASTER_PATH}")
    print("="*60)
    
    try:
        while True:
            # 1초마다 상태를 유지하며 무한 대기합니다.
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n🛑 Watchdog 데몬 종료.")
    observer.join()

if __name__ == "__main__":
    start_daemon()