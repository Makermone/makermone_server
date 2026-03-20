import sys
import os
import json
import uno
from com.sun.star.beans import PropertyValue

def render(json_path):
    local_context = uno.getComponentContext()
    resolver = local_context.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local_context)
    
    try:
        ctx = resolver.resolve("uno:socket,host=localhost,port=2002;urp;StarOffice.ComponentContext")
        smgr = ctx.ServiceManager
        desktop = smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        template_path = data.get("_template_path")
        file_url = uno.systemPathToFileUrl(template_path)
        
        load_props = (PropertyValue(Name="Hidden", Value=True),)
        doc = desktop.loadComponentFromURL(file_url, "_blank", 0, load_props)
        sheet = doc.Sheets.getByIndex(0)

        # ★ 1페이지 강제 압축 (2페이지 밀림 원천 차단)
        page_style_name = sheet.PageStyle
        page_style = doc.StyleFamilies.getByName("PageStyles").getByName(page_style_name)
        page_style.ScaleToPages = 1

        # ★ 정렬 모듈 안전 호출 (Import 에러 해결)
        ALIGN_CENTER_HORI = uno.Enum("com.sun.star.table.CellHoriJustify", "CENTER")
        ALIGN_RIGHT_HORI = uno.Enum("com.sun.star.table.CellHoriJustify", "RIGHT")
        ALIGN_CENTER_VERT = uno.Enum("com.sun.star.table.CellVertJustify", "CENTER")

        # ==========================================
        # 1. 고정 변수 매핑 [태그 치환 방식]
        # ==========================================
        replacements = {
            "{{문서번호}}": data.get("doc_no", ""),
            "{{기업명}}": data.get("vendor_name", ""),
            "{{기업번호}}": data.get("vendor_biz_no", ""),
            "{{대표자}}": data.get("vendor_ceo", ""),
            "{{주소}}": data.get("vendor_address", ""),
            
            "{{발주사항}}": data.get("po_title", ""),
            "{{발주일자}}": f"'{data.get('po_date', '')}",
            "{{세부내역}}": data.get("po_details", ""),
            "{{납기일자}}": f"'{data.get('due_date', '')}",
            
            "{{합계}}": f"'{data.get('total_amount', '')}",
            "{{관리번호}}": data.get("manage_no", ""),
            "{{첨부파일}}": data.get("attachment", ""),
            "{{결제조건}}": data.get("payment_condition", "")
        }
        
        for tag, value in replacements.items():
            replace_desc = sheet.createReplaceDescriptor()
            replace_desc.setSearchString(tag)
            replace_desc.setReplaceString(value)
            sheet.replaceAll(replace_desc)

        # ==========================================
        # 2. 동적 표 정렬 및 병합 (우측 정렬 강제 적용)
        # ==========================================
        po_items_raw = data.get("po_items", [])
        
        flat_items = []
        for group in po_items_raw:
            g_name = group.get("project_manage_no", group.get("group_name", ""))
            if "details" not in group:
                flat_items.append({
                    "group_name": g_name,
                    "name": group.get("model_no", ""),
                    "qty": group.get("qty", ""),
                    "price": group.get("price", "")
                })
            else:
                for index, item in enumerate(group.get("details", [])):
                    flat_items.append({
                        "group_name": g_name if index == 0 else "",
                        "name": item.get("name", ""),
                        "qty": item.get("qty", ""),
                        "price": item.get("price", "")
                    })
                
        total_items = len(flat_items)
        
        search_desc = sheet.createSearchDescriptor()
        search_desc.setSearchString("{{TABLE_START}}")
        found = sheet.findFirst(search_desc)
        
        if found and total_items > 0:
            start_row_idx = found.getCellAddress().Row
            current_row_idx = start_row_idx
            
            prev_group_name = None
            group_start_row = current_row_idx
            group_size = 0

            for i, item in enumerate(flat_items):
                current_g_name = item.get("group_name", "")
                
                # 새 그룹 시작 시 이전 그룹 병합 및 [가운데 정렬] 강제 적용
                if current_g_name != "" and current_g_name != prev_group_name:
                    if group_size > 1:
                        merge_range = sheet.getCellRangeByPosition(2, group_start_row, 3, group_start_row + group_size - 1)
                        merge_range.merge(True)
                        merge_range.HoriJustify = ALIGN_CENTER_HORI
                        merge_range.VertJustify = ALIGN_CENTER_VERT
                    
                    group_start_row = current_row_idx
                    group_size = 0
                    prev_group_name = current_g_name

                # [관리번호] 기입 및 가운데 정렬
                group_cell = sheet.getCellByPosition(2, current_row_idx)
                group_cell.String = current_g_name
                group_cell.HoriJustify = ALIGN_CENTER_HORI
                group_cell.VertJustify = ALIGN_CENTER_VERT

                # [부품명] 기입 (위아래만 가운데, 좌우는 엑셀 기본값)
                name_cell = sheet.getCellByPosition(4, current_row_idx)
                name_cell.String = item.get("name", "")
                name_cell.VertJustify = ALIGN_CENTER_VERT
                
                # [수량] 기입 및 가운데 정렬
                qty_cell = sheet.getCellByPosition(7, current_row_idx)
                qty_cell.String = item.get("qty", "")
                qty_cell.HoriJustify = ALIGN_CENTER_HORI
                qty_cell.VertJustify = ALIGN_CENTER_VERT

                # [가격] ★ 우측 정렬 및 세로 가운데 정렬 강제 ★
                price_cell = sheet.getCellByPosition(9, current_row_idx)
                price_cell.String = item.get("price", "")
                price_cell.HoriJustify = ALIGN_RIGHT_HORI
                price_cell.VertJustify = ALIGN_CENTER_VERT
                
                current_row_idx += 1
                group_size += 1

            # 마지막 그룹 병합 및 정렬 처리
            if group_size > 1:
                merge_range = sheet.getCellRangeByPosition(2, group_start_row, 3, group_start_row + group_size - 1)
                merge_range.merge(True)
                merge_range.HoriJustify = ALIGN_CENTER_HORI
                merge_range.VertJustify = ALIGN_CENTER_VERT
                
            # {{TABLE_START}} 텍스트 지우기
            sheet.getCellByPosition(2, start_row_idx).String = sheet.getCellByPosition(2, start_row_idx).String.replace("{{TABLE_START}}", "")

        # ==========================================
        # 3. PDF 추출
        # ==========================================
        output_pdf_url = file_url.replace(".ods", "_output.pdf")
        output_pdf_path = uno.fileUrlToSystemPath(output_pdf_url)
        
        filter_data = (PropertyValue(Name="FilterName", Value="calc_pdf_Export"),)
        doc.storeToURL(output_pdf_url, filter_data)
        doc.close(True)
        
        print(output_pdf_path)
        
    except Exception as e:
        print(f"ERROR: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("ERROR: No JSON path provided", file=sys.stderr)
        sys.exit(1)
    render(sys.argv[1])