# 1. 가장 가볍고 호환성 좋은 Python 3.9 슬림 버전
FROM python:3.9-slim

# 2. 작업 폴더 설정
WORKDIR /app

# 3. 필수 도구 업데이트
RUN pip install --no-cache-dir --upgrade pip

# 4. [핵심] 문제의 라이브러리 제거! 
# 'requests'는 절대 실패하지 않습니다.
RUN pip install --no-cache-dir Flask gunicorn requests

# 5. 내 코드 복사
COPY . .

# 6. 서버 실행
CMD ["gunicorn", "--bind", ":8080", "--workers", "1", "--threads", "8", "--timeout", "0", "main:app"]