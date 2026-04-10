import os
import glob
import json
import requests
import cadquery as cq
from google import genai
from google.genai import types
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "makermone-ai-core")
MASTER_DB_API_URL = os.getenv("MASTER_DB_API_URL")

client = genai.Client(vertexai=True, project=PROJECT_ID, location="us-central1")

# =========================================================
# 🛡️ [신규] 중복 스캔 방지 로직 (Local Cache)
# =========================================================
CACHE_FILE = "scan_history.json"

def load_scanned_history():
    """이미 스캔 완료된 파일명 목록을 불러옵니다."""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_scanned_history(history_list):
    """스캔 완료된 파일명 목록을 저장합니다."""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(history_list, f, ensure_ascii=False, indent=2)

def extract_step_data(step_path):
    """3D STEP 파일에서 기하학적 수치 추출 및 단위 추가"""
    try:
        shape = cq.importers.importStep(step_path)
        bb = shape.val().BoundingBox()
        volume = shape.val().Volume()
        
        # 치수 뒤에 mm 단위 추가 (예: 150.0 x 100.0 x 15.0 mm)
        dims = f"{round(bb.xlen, 1)} x {round(bb.ylen, 1)} x {round(bb.zlen, 1)} mm"
        
        # 체적 뒤에 mm³ 단위 추가 (예: 1401284.4 mm³)
        vol_with_unit = f"{round(volume, 2)} mm³"
        
        return dims, vol_with_unit
    except Exception as e:
        return "N/A", "0 mm³"

def extract_pdf_vision_data(pdf_path):
    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
            
        # [메이커몬 맞춤형 초정밀 프롬프트]
        # 대표님의 도면 양식에 적힌 실제 텍스트(예: "품명", "재질")와 일치하도록 앵커를 설정합니다.
        prompt = """
        당신은 메이커몬의 10년 차 수석 기구설계 엔지니어입니다. 제공된 2D 제작 도면(PDF)을 정밀하게 분석하여 아래 JSON 형식으로만 답변하세요.

        [추출 지침 - 표제란]
        1. "part_name": 도면 우측 하단(또는 상단) 표제란에 '품명', 'DRAWING TITLE', 'DESCRIPTION' 등의 라벨 옆/아래에 기재된 텍스트를 정확히 추출할 것.
        2. "material": 표제란의 'MATL/SPEC', '소재', 'MATERIAL' 라벨 옆/아래에 기재된 텍스트를 추출.
        3. "finish": 표제란의 '표면처리', '후처리', 'REMARKS' 라벨 옆/아래에 기재된 텍스트를 추출.

        [추출 지침 - 가공 특이사항 (매우 중요)]
        4. "notes": 가공 난이도와 원가 산출에 **직접적인 영향을 주는 핵심 지시사항**만 간결하게 추출할 것.
           - ✅ [필수 추출]: TAP(탭) 가공 사이즈 및 전체 개수 합산, 절곡(Bending) 횟수 및 각도, 카운터보어, 압입(INSERT 등), 특수 사상(Lapping 등).
           - ❌ [절대 제외(블랙리스트)]: 도면마다 공통으로 인쇄되어 있는 **'일반 공차표(금형 제품 공차, 기계 가공 공차 등)' 데이터는 절대 추출하지 말고 100% 무시할 것.**
           - 추출한 핵심 사항들은 엔지니어가 한눈에 볼 수 있도록 핵심 키워드 위주로 짧게 요약할 것.

        [출력 규칙]
        - 내용이 없는 항목은 '미기재'로 출력할 것.
        - JSON의 Value는 반드시 단순 문자열(String)만 사용할 것. (배열이나 객체 중첩 절대 금지)

        [출력 포맷]
        {
          "part_name": "...",
          "material": "...",
          "finish": "...",
          "notes": "..."
        }
        """
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[types.Part.from_bytes(data=pdf_bytes, mime_type='application/pdf'), prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except Exception as e:
        return {"part_name": "AI 분석 실패", "material": "", "finish": "", "notes": str(e)}

# 👉 대표님이 찾으시던 바로 그 함수명으로 원복했습니다!
def run_test_scan(target_folder):
    # 🚀 [절대 규칙 7-2 적용] 하위 폴더를 무한대로 파고들어(Infinite Depth) 모든 PDF를 색인합니다.
    search_pattern = os.path.join(target_folder, "**", "*.pdf")
    all_pdf_files = glob.glob(search_pattern, recursive=True)
    
    # 🛡️ 캐시 로직 적용: 이미 스캔한 파일은 리스트에서 제외
    scanned_history = load_scanned_history()
    pdf_files = [f for f in all_pdf_files if os.path.basename(f) not in scanned_history]
    
    skipped_count = len(all_pdf_files) - len(pdf_files)
    
    print(f"\n🏭 스캐너 가동: 총 {len(all_pdf_files)}건 중, 중복 제외된 신규 도면 {len(pdf_files)}건 분석 시작 (건너뜀: {skipped_count}건)\n" + "="*50)

    if not pdf_files:
        print("✅ 모든 도면이 이미 최신 상태로 스캔되어 있습니다. 종료합니다.")
        return

    parsed_results = []
    success_file_names = [] # 이번에 성공한 파일명들

    for pdf in pdf_files:
        # 파일 경로가 복잡해지므로, 순수 파일명(예: BH03PRE001-A)만 정확히 발라냅니다.
        base_name = os.path.splitext(os.path.basename(pdf))[0]
        # STEP 파일도 동일한 폴더(동일한 경로)에 있다고 가정하고 찾습니다.
        pdf_dir = os.path.dirname(pdf)
        step_path = os.path.join(pdf_dir, f"{base_name}.step")
        
        identity_code = f"{base_name[:4]}V01"
        
        # [신규 로직] 품번(base_name) 슬라이싱 (예: BH03 AEX 003 - A)
        process_type = base_name[4:7] if len(base_name) >= 7 else ""
        serial_num = base_name[7:10] if len(base_name) >= 10 else ""
        
        # 3D 분석 결과에 이미 단위가 포함되어 반환됩니다.
        dims, vol_str = extract_step_data(step_path) if os.path.exists(step_path) else ("N/A", "0 mm³")
        vision_data = extract_pdf_vision_data(pdf)
        
        # [핵심] C, G, H열 데이터가 모두 포함된 포장지(Dictionary)
        part_data = {
            "identity_code": identity_code,
            "part_no": base_name,
            "part_name": vision_data.get("part_name", ""),
            "material": vision_data.get("material", ""),
            "process_type": process_type,
            "serial_num": serial_num,
            "dimensions": dims,      # "150.0 x 100.0 x 15.0 mm" 형태로 전송
            "volume": vol_str,       # "1401284.4 mm³" 형태로 전송
            "notes": str(vision_data.get("notes", "")),
            "finish": vision_data.get("finish", "")
        }
        parsed_results.append(part_data)
        success_file_names.append(os.path.basename(pdf))
        print(f"✅ 분석: {base_name} | 부품명: {vision_data.get('part_name')} | 공정: {process_type} | 일련번호: {serial_num}")

    print("="*50)

    # ==========================================================
    # 🚨 수정된 전송 로직: 대량 데이터 청크(Chunk) 분할 전송 및 타임아웃 연장
    # ==========================================================
    if parsed_results:
        total_count = len(parsed_results)
        print(f"\n📤 구글 시트로 총 {total_count}건의 데이터 청크(Batch) 전송을 시작합니다...")
        
        # 구글 서버 과부하 방지를 위해 50개씩 쪼개서(Batch) 보냅니다.
        chunk_size = 50 
        
        for i in range(0, total_count, chunk_size):
            chunk = parsed_results[i : i + chunk_size]
            payload = {"action": "upload_scanned_parts", "parts_data": chunk}
            
            print(f"📡 [배치 전송] {i + 1} ~ {min(i + chunk_size, total_count)}건 전송 중...")
            
            try:
                # 구글 Apps Script가 시트에 글을 쓸 시간을 넉넉하게 120초로 연장
                res = requests.post(MASTER_DB_API_URL, json=payload, timeout=120)
                if res.status_code == 200:
                    print(f"   ✅ 서버 응답: {res.text}")
                    # 🛡️ 전송까지 완벽히 성공한 경우에만 캐시에 기록
                    scanned_history.extend(success_file_names[i : i + chunk_size])
                    save_scanned_history(scanned_history)
                else:
                    print(f"   ❌ HTTP 에러: {res.text}")
            except Exception as e:
                print(f"   ❌ 전송 실패 (해당 배치): {e}")
                
        print("\n🎉 모든 데이터 전송 프로세스가 완료되었습니다!")
    else:
        print("⚠️ 분석된 결과가 없어 전송을 건너뜁니다.")

if __name__ == "__main__":
    # 대표님의 구글 드라이브 로컬 동기화 경로
    MASTER_PATH = r"G:\내 드라이브\메이커몬\관리도면"
    run_test_scan(MASTER_PATH)