import os
import time
import json
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# 기존 하이브리드 스캐너에서 함수를 가져옵니다.
from hybrid_scanner import run_test_scan

MASTER_PATH = r"G:\내 드라이브\메이커몬\관리도면"
HITL_QUEUE_FILE = "hitl_approval_queue.json" # 엔지니어 승인 대기열 메모리 파일
WEBHOOK_QUEUE_FILE = "agent1_webhook_queue.json"

# =========================================================================
# 🛡️ [Phase 2] 에이전트 하네스: 30초 이벤트 배칭 큐 (서버 다운/무한 루프 방지)
# =========================================================================
class EventBatchQueue:
    def __init__(self):
        self.events = set()
        self.lock = threading.Lock()
        self.last_processed = time.time()

    def add_event(self, filepath):
        """이벤트 발생 시 큐에 파일 경로를 추가 (중복 제거)"""
        with self.lock:
            self.events.add(filepath)

    def process_batch(self):
        """30초마다 쌓인 이벤트를 한 번에 묶어서(Batch) 처리"""
        with self.lock:
            if not self.events:
                return []
            batch_to_process = list(self.events)
            self.events.clear()
            self.last_processed = time.time()
            return batch_to_process

event_queue = EventBatchQueue()

# =========================================================================
# 🤖 [Phase 2] Agent 1 (PM) 능동형 워크플로우 & HITL 적재 로직
# =========================================================================
def agent_pm_analyzer(batch_files, webhook_events):
    """
    Agent 1이 압축된 30초 분량의 변동 사항(파일 + Sub DB 웹훅)을 분석하여
    고객 푸시 알림 초안을 작성하고, 즉각 실행 대신 'HITL 승인 대기열'로 이관합니다.
    """
    if not batch_files and not webhook_events:
        return

    print(f"\n🧠 [Agent 1] {len(batch_files)}개의 도면 변동 및 {len(webhook_events)}개의 DB 이벤트 분석 중...")
    
    # 1. AI PM의 능동형 리포팅 초안 작성 (예시)
    report_draft = {
        "timestamp": time.time(),
        "agent": "PM_Agent_1",
        "trigger_source": "Watchdog & Webhook",
        "detected_files": batch_files,
        "db_events": webhook_events,
        "proposed_action": "고객사 카카오톡 챗봇으로 신규 설계/양산 변동 알림(Push) 발송",
        "status": "PENDING_APPROVAL" # 🚨 엔지니어 통제 대기 상태
    }
    
    # 2. HITL (Streamlit 관제탑) 승인 대기열 파일에 안전하게 적재 (절대 자동 발송 금지)
    existing_queue = []
    if os.path.exists(HITL_QUEUE_FILE):
        try:
            with open(HITL_QUEUE_FILE, 'r', encoding='utf-8') as f:
                existing_queue = json.load(f)
        except:
            pass

    existing_queue.append(report_draft)
    
    with open(HITL_QUEUE_FILE, 'w', encoding='utf-8') as f:
        json.dump(existing_queue, f, ensure_ascii=False, indent=2)

    print("🛡️ [HITL] 외부 발송 차단됨. 엔지니어(대표) 승인 대기열(Streamlit)로 초안이 적재되었습니다.")

def background_queue_processor():
    """백그라운드에서 30초마다 큐를 확인하고 Agent 1을 깨우는 무한 루프 스레드"""
    while True:
        time.sleep(30) # 🚨 30초 디바운싱(배칭) 대기
        
        # 1. 로컬 파일 시스템(도면) 변동 사항 가져오기
        batch_files = event_queue.process_batch()
        
        # 2. app_router.py에서 적재한 Sub DB 웹훅 이벤트 가져오기
        webhook_events = []
        if os.path.exists(WEBHOOK_QUEUE_FILE):
            try:
                with open(WEBHOOK_QUEUE_FILE, 'r', encoding='utf-8') as f:
                    webhook_events = json.load(f)
                # 처리할 데이터를 가져온 후 큐 파일 초기화
                open(WEBHOOK_QUEUE_FILE, 'w').close() 
            except:
                pass
                
        if batch_files or webhook_events:
            print("\n" + "="*60)
            print("🚀 [하네스 작동] 30초 큐(Queue) 압축 해제. Agent 1 가동을 시작합니다.")
            
            # 파일이 들어왔다면 하이브리드 스캐너 가동
            if batch_files:
                try:
                    run_test_scan(MASTER_PATH)
                except Exception as e:
                    print(f"❌ 자동 스캔 중 오류 발생: {e}")
            
            # Agent 1 분석 및 HITL 관제탑 전송
            agent_pm_analyzer(batch_files, webhook_events)
            print("="*60)

class MakerMoneHandler(FileSystemEventHandler):
    def on_created(self, event):
        # 폴더 생성은 무시합니다.
        if event.is_directory:
            return

        # PDF나 STEP 파일이 새로 생성되었을 때만 반응합니다.
        if event.src_path.lower().endswith(('.pdf', '.step')):
            print(f"👀 [Watchdog] 새로운 도면 감지 (큐에 담습니다): {os.path.basename(event.src_path)}")
            # 즉시 처리하지 않고 30초 이벤트 배칭 큐에 담아둡니다.
            event_queue.add_event(event.src_path)

def start_daemon():
    print("="*60)
    print("🛡️ [메이커몬 Zero-Touch 팩토리] Watchdog 데몬 가동 전 초기 동기화 진행 중...")
    print("🔍 데몬이 꺼져있던 동안 누락된 신규 도면을 탐색합니다.")
    print("="*60)
    
    # 🚀 감시(Observer) 시작 전, 누락분 전수 조사 1회 선제 실행
    try:
        run_test_scan(MASTER_PATH)
    except Exception as e:
        print(f"❌ 초기 동기화 중 오류 발생: {e}")

    # 이벤트 큐를 처리하는 백그라운드 스레드 가동
    processor_thread = threading.Thread(target=background_queue_processor, daemon=True)
    processor_thread.start()

    event_handler = MakerMoneHandler()
    observer = Observer()
    observer.schedule(event_handler, MASTER_PATH, recursive=True)
    observer.start()
    
    print("\n" + "="*60)
    print("👀 30초 배칭(Batching) 실시간 감시 모드로 전환되었습니다...")
    print("🤖 Agent 1 (PM) 능동형 분석기 스탠바이 완료.")
    print(f"📂 감시 경로: {MASTER_PATH}")
    print("="*60)
    
    try:
        while True:
            # 메인 스레드는 1초마다 상태를 유지하며 무한 대기합니다.
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n🛑 Watchdog 데몬 종료.")
    observer.join()

if __name__ == "__main__":
    start_daemon()