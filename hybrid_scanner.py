import os
import glob
import json
import requests
import cadquery as cq
from google import genai
from google.genai import types
from dotenv import load_dotenv

# 환경변수 로드 (.env 파일에 GCP_PROJECT_ID와 SUB_DB_API_URL이 있어야 합니다)
load_dotenv()
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "makermone-ai-core")

# Gemini 2.0 Flash 클라이언트 설정
client = genai.Client(vertexai=True, project=PROJECT_ID, location="us-central1")

def extract_step_data(step_path):
    """3D STEP 파일에서 기하학적 수치 추출 (수학적 정확도 100%)"""
    try:
        # STEP 파일 로드
        shape = cq.importers.importStep(step_path)
        bb = shape.val().BoundingBox()
        volume = shape.val().Volume()
        
        # 외곽 사이즈 (X * Y * Z)
        dims = f"{round(bb.xlen, 1)} x {round(bb.ylen, 1)} x {round(bb.zlen, 1)}"
        # 부피 (mm3 -> g 변환 등은 추후 재질 밀도 곱셈으로 확장 가능)
        vol_rounded = round(volume, 2)
        return dims, vol_rounded
    except Exception as e:
        return f"Error: {str(e)}", 0

def extract_pdf_vision_data(pdf_path):
    """2D PDF 도면에서 AI가 텍스트 및 공정 정보 추출 (멀티모달)"""
    try:
        # 로컬 PDF 파일을 Gemini에 업로드 (실시간 분석)
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
            
        # Gemini 2.5 Flash는 PDF를 직접 이해할 수 있습니다.
        prompt = """
        이 제작 도면의 표제란과 지시선을 정밀 분석해서 다음 정보를 한국어로 추출해줘.
        JSON 형식으로만 답변해야 해:
        {
          "material": "재질 정보 (예: AL6061, SUS304)",
          "finish": "후처리/표면처리 정보 (예: 흑색 아노다이징, 분체도장)",
          "notes": "기타 가공 특이사항 (예: 탭 가공 있음, 특수 공차)"
        }
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type='application/pdf'),
                prompt
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except Exception as e:
        return {"material": "N/A", "finish": "N/A", "notes": f"AI 분석 실패: {str(e)}"}

def run_test_scan(target_folder):
    """지정된 폴더의 도면 세트를 스캔하여 결과 출력"""
    pdf_files = glob.glob(os.path.join(target_folder, "*.pdf"))
    
    print("\n" + "="*80)
    print(f"🏭 메이커몬 하이브리드 스캐너 가동: {len(pdf_files)} 세트 탐색됨")
    print("="*80 + "\n")

    for pdf in pdf_files:
        base_name = os.path.splitext(os.path.basename(pdf))[0]
        step_path = os.path.join(target_folder, f"{base_name}.step")
        
        # 식별코드 자동 결합 (Prefix 4자리 + V01)
        identity_code = f"{base_name[:4]}V01"
        
        print(f"🔍 [분석 시작] 명찰: {identity_code} | 파일명: {base_name}")
        
        # 1. 3D 기하학 파싱
        dims, vol = "N/A", "N/A"
        if os.path.exists(step_path):
            dims, vol = extract_step_data(step_path)
            print(f"   📐 3D 분석 완료: 치수({dims}) / 체적({vol} mm³)")
        else:
            print(f"   ⚠️ STEP 파일이 없어 3D 분석을 건너뜁니다.")

        # 2. 2D AI 비전 파싱
        print(f"   🤖 AI가 도면을 읽고 있습니다...")
        vision_data = extract_pdf_vision_data(pdf)
        print(f"   📝 AI 분석 완료: 재질({vision_data['material']}) / 후처리({vision_data['finish']})")
        print(f"   💡 특이사항: {vision_data['notes']}")
        print("-" * 40)

def process_folder(target_folder):
    """폴더 내의 도면 세트를 스캔하여 구글 시트로 전송"""
    pdf_files = glob.glob(os.path.join(target_folder, "*.pdf"))
    parsed_results = []
    
    print("\n" + "="*80)
    print(f"🏭 메이커몬 하이브리드 스캐너 가동: {len(pdf_files)} 세트 탐색됨")
    print("="*80 + "\n")

    for pdf in pdf_files:
        base_name = os.path.splitext(os.path.basename(pdf))[0]
        step_path = os.path.join(target_folder, f"{base_name}.step")
        
        identity_code = f"{base_name[:4]}V01"
        print(f"🔍 [분석 시작] 명찰: {identity_code} | 파일명: {base_name}")
        
        dims, vol = "N/A", "N/A"
        if os.path.exists(step_path):
            dims, vol = extract_step_data(step_path)
            print(f"   📐 3D 분석 완료: 치수({dims}) / 체적({vol} mm³)")

        print(f"   🤖 AI가 도면을 읽고 있습니다...")
        vision_data = extract_pdf_vision_data(pdf)
        print(f"   📝 AI 분석 완료: 재질({vision_data.get('material')}) / 후처리({vision_data.get('finish')})")
        
        part_data = {
            "identity_code": identity_code,
            "part_no": base_name,
            "material": vision_data.get("material", ""),
            "dimensions": dims,
            "volume": vol,
            "notes": vision_data.get("notes", ""),
            "finish": vision_data.get("finish", "")
        }
        parsed_results.append(part_data)
        print("-" * 40)
        
    # --- [신규 추가] 구글 시트로 데이터 일괄 전송 ---
    if parsed_results:
        print("📤 구글 시트(Parts Master)로 데이터 전송을 시작합니다...")
        payload = {
            "action": "upload_scanned_parts",
            "parts_data": parsed_results
        }
        try:
            response = requests.post(SUB_DB_API_URL, json=payload, timeout=20)
            if response.status_code == 200:
                res_data = response.json()
                if res_data.get("status") == "success":
                    print(f"✅ 전송 대성공: {res_data.get('message')}")
                else:
                    print(f"❌ 전송 실패 (서버 응답): {res_data.get('message')}")
            else:
                print(f"❌ 통신 에러: HTTP {response.status_code}")
        except Exception as e:
            print(f"❌ 전송 중 치명적 에러 발생: {str(e)}")

if __name__ == "__main__":
    # 대표님의 로컬 경로로 강제 고정
    TEST_PATH = r"C:\Users\keede\Downloads\test_drawings"
    run_test_scan(TEST_PATH)