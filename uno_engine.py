import sys
import os
import json
import re
# 리브레오피스 내장 모듈
import uno
from com.sun.star.beans import PropertyValue

def extract_numeric(val_str):
    if not val_str: return None
    cleaned = re.sub(r'[^0-9.]', '', str(val_str))
    return float(cleaned) if cleaned else None

def main():
    try:
        json_path = sys.argv[1]
        template_path = sys.argv[2]
        output_pdf_path = sys.argv[3]

        with open(json_path, 'r', encoding='utf-8') as f:
            data_json = json.load(f)

        # --------------------------------------------------
        # 🚨 [수정된 핵심 로직] 공장 통신 케이블(2002번) 복구
        # 제가 실수로 누락했던 바로 그 연결 코드입니다.
        # --------------------------------------------------
        localContext = uno.getComponentContext()
        resolver = localContext.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", localContext
        )
        # 백그라운드에 켜져 있는 2002번 데몬과 소켓으로 연결합니다.
        ctx = resolver.resolve("uno:socket,host=127.0.0.1,port=2002;urp;StarOffice.ComponentContext")
        smgr = ctx.ServiceManager
        desktop = smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        
        url_template = uno.systemPathToFileUrl(os.path.abspath(template_path))
        props = (PropertyValue("Hidden", 0, True, 0),)
        doc = desktop.loadComponentFromURL(url_template, "_blank", 0, props)
        
        if not doc:
            # 템플릿이 잠겨서 열리지 않을 경우 명확한 에러를 뱉습니다.
            print("❌ 템플릿 파일을 열 수 없습니다. (파일 잠금 또는 경로 오류)", file=sys.stderr)
            sys.exit(1)

        sheet = doc.Sheets.getByIndex(0)

        # --------------------------------------------------
        # [데이터 맵핑 (대표님 원본 오차 0% 로직)]
        # --------------------------------------------------
        sheet.getCellRangeByName("B4").String = str(data_json.get("doc_no", ""))
        sheet.getCellRangeByName("E8").String = str(data_json.get("vendor_name", ""))
        sheet.getCellRangeByName("J8").String = str(data_json.get("vendor_ceo", ""))
        sheet.getCellRangeByName("E9").String = str(data_json.get("vendor_biz_no", ""))
        sheet.getCellRangeByName("E10").String = str(data_json.get("vendor_address", ""))
        sheet.getCellRangeByName("D22").String = str(data_json.get("po_title", ""))
        sheet.getCellRangeByName("D23").String = str(data_json.get("po_date", ""))
        sheet.getCellRangeByName("D24").String = str(data_json.get("po_details", ""))
        sheet.getCellRangeByName("D25").String = str(data_json.get("due_date", ""))
        sheet.getCellRangeByName("D51").String = str(data_json.get("manage_no", ""))
        sheet.getCellRangeByName("D52").String = str(data_json.get("attachment", ""))
        sheet.getCellRangeByName("B53").String = str(data_json.get("condition_label", "결제 조건"))
        sheet.getCellRangeByName("D53").String = str(data_json.get("condition_content", ""))

        m_total_range = sheet.getCellRangeByPosition(9, 47, 11, 47)
        m_total_range.merge(True)
        cell_total = sheet.getCellByPosition(9, 47)
        total_val = extract_numeric(data_json.get("total_amount", ""))
        if total_val is not None:
            cell_total.Value = total_val
        else:
            cell_total.String = ""
        cell_total.HoriJustify = uno.Enum("com.sun.star.table.CellHoriJustify", "RIGHT")
        cell_total.VertJustify = uno.Enum("com.sun.star.table.CellVertJustify", "CENTER")

        items = data_json.get("po_items", [])
        if items:
            start_row = 27
            for item in items:
                sheet.getCellByPosition(1, start_row).String = str(item.get("project_manage_no", ""))
                sheet.getCellByPosition(4, start_row).String = str(item.get("model_no", ""))
                sheet.getCellByPosition(7, start_row).String = str(item.get("qty", ""))
                price_val = extract_numeric(item.get("price", ""))
                if price_val is not None:
                    sheet.getCellByPosition(9, start_row).Value = price_val
                else:
                    sheet.getCellByPosition(9, start_row).String = ""
                start_row += 1

        # --------------------------------------------------
        # [PDF 추출]
        # --------------------------------------------------
        url_pdf = uno.systemPathToFileUrl(os.path.abspath(output_pdf_path))
        filter_args = (PropertyValue("FilterName", 0, "calc_pdf_Export", 0),)
        doc.storeToURL(url_pdf, filter_args)
        doc.close(True)

    except Exception as e:
        # 🚨 [블랙박스 장착] 에러가 발생하면 텅 빈 메시지가 아니라, 파이썬의 상세 에러 추적 로그를 무조건 반환합니다.
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()