Cách chạy:
1. Tạo các file .env (ở thư mục gốc), .env (ở thư mục frontend). Nội dung các file gửi trên nhóm Messenger
2. Cài môi trường: python -m pip install -r requirements.txt
3. Backend: python -X utf8 -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8001
4. Frontend: npm run dev