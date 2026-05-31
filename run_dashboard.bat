@echo off
timeout /t 5
cd /d "C:\Users\keede\Documents\Github\makermone_server"
"C:\Users\keede\AppData\Roaming\uv\bin\uv.exe" run streamlit run hitl_dashboard.py --server.port 8501 --server.headless true