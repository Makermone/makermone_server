import sys
import os

# ==========================================
# [핵심] 윈도우 환경 LibreOffice DLL 및 PyUNO 경로 강제 주입
# ==========================================
lo_program_path = r"C:\Program Files\LibreOffice\program"

if os.name == 'nt':
    # 1. 파이썬 모듈 인식 경로 추가
    if lo_program_path not in sys.path:
        sys.path.append(lo_program_path)
    
    # 2. 윈도우 OS 시스템 DLL 인식 경로 추가 (이 부분이 없으면 Streamlit이 뻗어버립니다)
    if lo_program_path not in os.environ.get("PATH", ""):
        os.environ["PATH"] = lo_program_path + os.pathsep + os.environ.get("PATH", "")

# 경로 주입 후 안전하게 uno 임포트
try:
    import uno
    from com.sun.star.beans import PropertyValue
except ImportError as e:
    print(f"❌ PyUNO 라이브러리 임포트 실패 (경로 문제): {e}")

def render_ods_to_pdf(template_path, data):
    """
    백그라운드 LibreOffice 소켓에 접속하여 메모리 상의 .ods 셀에 데이터를 주입하고 PDF로 굽는 함수
    """
    # 1. 소켓 통신으로 데몬 접속
    localContext = uno.getComponentContext()
    resolver = localContext.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", localContext)
    
    try:
        ctx = resolver.resolve("uno:socket,host=localhost,port=2002;urp;StarOffice.ComponentContext")
    except Exception as e:
        raise Exception("❌ LibreOffice 데몬(포트 2002)이 실행되지 않았습니다.")
        
    smgr = ctx.ServiceManager
    desktop = smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    
    # 2. 폼 오버레이 에셋(.ods) Hidden 모드로 열기
    url = uno.systemPathToFileUrl(os.path.abspath(template_path))
    prop = PropertyValue()
    prop.Name = "Hidden"
    prop.Value = True
    doc = desktop.loadComponentFromURL(url, "_blank", 0, (prop,))
    
    sheet = doc.Sheets.getByIndex(0)
    
    # ==========================================
    # 3. 고정 변수 매핑 (엔지니어 절대 좌표 적용)
    # ==========================================
    sheet.getCellRangeByName("B4").String = data.get("doc_no", "")
    sheet.getCellRangeByName("E8").String = data.get("vendor_name", "")
    sheet.getCellRangeByName("E9").String = data.get("vendor_biz_no", "")
    sheet.getCellRangeByName("E10").String = data.get("vendor_address", "")
    sheet.getCellRangeByName("J8").String = data.get("vendor_ceo", "")
    
    sheet.getCellRangeByName("D22").String = data.get("po_title", "")
    sheet.getCellRangeByName("D23").String = data.get("po_date", "")
    sheet.getCellRangeByName("D24").String = data.get("po_details", "")
    sheet.getCellRangeByName("D25").String = data.get("due_date", "")
    
    sheet.getCellRangeByName("J48").String = data.get("total_amount", "")
    sheet.getCellRangeByName("D51").String = data.get("manage_no", "")
    sheet.getCellRangeByName("D52").String = data.get("attachment", "")
    sheet.getCellRangeByName("D53").String = data.get("payment_condition", "")
    
    # ==========================================
    # 4. 동적 변수 (표 구간) 매핑
    # ==========================================
    # 28행부터 시작 -> PyUNO 행 인덱스는 0부터 시작하므로 '27'
    start_row_idx = 27 
    
    for i, item in enumerate(data.get("po_items", [])):
        current_row = start_row_idx + i
        
        # 열 인덱스 (A=0, B=1, C=2, D=3, E=4, F=5, G=6, H=7, I=8, J=9)
        # C28: 프로젝트 관리번호
        sheet.getCellByPosition(2, current_row).String = item.get("project_manage_no", "")
        # E28: 모델(도면)번호
        sheet.getCellByPosition(4, current_row).String = item.get("model_no", "")
        # H28: 수량
        sheet.getCellByPosition(7, current_row).String = item.get("qty", "")
        # J28: 가격
        sheet.getCellByPosition(9, current_row).String = item.get("price", "")
        
    # ==========================================
    # 5. Native PDF 추출 (Export) 및 메모리 정리
    # ==========================================
    output_pdf_path = os.path.abspath(template_path).replace(".ods", "_output.pdf")
    out_url = uno.systemPathToFileUrl(output_pdf_path)
    
    filter_prop = PropertyValue()
    filter_prop.Name = "FilterName"
    filter_prop.Value = "calc_pdf_Export"
    
    doc.storeToURL(out_url, (filter_prop,))
    doc.close(True)
    
    return output_pdf_path