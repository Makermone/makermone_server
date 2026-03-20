import os
import json
import tempfile
import subprocess
from flask import Flask, request, send_file, jsonify

app = Flask(__name__)

# ==========================================
# [메이커몬 손발] 문서 자동화 렌더링 팩토리 라우터
# ==========================================
@app.route('/api/v1/generate/po', methods=['POST'])
def generate_po():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "데이터가 전달되지 않았습니다."}), 400

        print(f"📦 [수신 완료] 렌더링 요청 수신: {data.get('doc_no')} / {data.get('clientCode')}")

        template_path = os.path.join(os.getcwd(), "assets", "templates", "template_po.ods")
        data["_template_path"] = template_path

        temp_json_fd, temp_json_path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(temp_json_fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

        lo_python_exe = r"C:\Program Files\LibreOffice\program\python.exe"
        worker_script = os.path.join(os.getcwd(), "render_worker.py")

        print("⚙️ 렌더링 워커 가동 중... (DLL 격리 환경)")
        result = subprocess.run(
            [lo_python_exe, worker_script, temp_json_path],
            capture_output=True, text=True, check=True
        )

        os.remove(temp_json_path)
        pdf_result_path = result.stdout.strip()
        print(f"✅ 렌더링 완료! PDF 추출 성공: {pdf_result_path}")

        return send_file(
            pdf_result_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{data.get('doc_no', 'PO')}.pdf"
        )

    except subprocess.CalledProcessError as e:
        print(f"❌ 워커 실행 에러: {e.stderr}")
        return jsonify({"error": "렌더링 팩토리 워커 에러", "details": e.stderr}), 500
    except Exception as e:
        print(f"❌ 시스템 통신 에러: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("🏭 [메이커몬 손발] 렌더링 팩토리 서버 가동 (Port 5000)")
    app.run(host='0.0.0.0', port=5000)