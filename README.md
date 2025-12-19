# MCP Server Demo

**Model Context Protocol (MCP)** sử dụng **FastMCP**, bao gồm 4 công cụ:

* `create_visualization`: Tạo ảnh từ text.
* `text_to_speech`: Tạo giọng nói từ text.
* `analyze_image`: Phân tích hình ảnh.
* `create_video`: Sinh video từ text hoặc ảnh.

---

## Yêu cầu

* Python **3.11+**
* Quản lý gói: **uv**
* API Key: `GEMINI_API_KEY` - Google Cloud API

---

## Cài đặt

### 1. Cài đặt

```bash
git clone https://github.com/Innovate-Lab/mcp-server-demo
cd MCP
uv sync

```

Tạo file cấu hình `.env`:

```bash
cp .env.example .env

```

### 2. Chạy Server

**Sử dụng Python**

```bash
uv run python -m src.main
# Server: http://localhost:8000 | Health: /health -> có thể thay BASE_URL trong file môi trường .env

```

---

## Hướng dẫn sử dụng (HTTP Transport)

Workflow: **Initialize** (Lấy Session ID) → **Notifications** → **Call Tools**.

### Bước 1: Khởi tạo & lấy Session ID

Gửi request `initialize` để nhận `mcp-session-id` từ server.

```bash
curl -i -s -X POST "http://localhost:8000/mcp" \
  -H "x-api-key: sk-1234" -H "Content-Type: application/json" \
  --data '{"jsonrpc":"2.0","id":"init","method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"0.1.0"}}}'

```

### Bước 2: Tool Call

Sử dụng `mcp-session-id` từ Bước 1 cho các request sau.

**Tạo ảnh (create_visualization):**

```bash
curl -s -X POST "http://localhost:8000/mcp" \
  -H "x-api-key: sk-1234" -H "mcp-session-id: <SESSION_ID>" \
  -H "Content-Type: application/json" \
  --data '{"jsonrpc":"2.0","id":"t1","method":"tools/call","params":{"name":"create_visualization","arguments":{"prompt":"A red ball on white floor","aspect_ratio":"1:1"}}}'

```

**Chuyển văn bản thành giọng nói (text_to_speech):**

```bash
curl -s -X POST "http://localhost:8000/mcp" \
  -H "x-api-key: sk-1234" -H "mcp-session-id: <SESSION_ID>" \
  -H "Content-Type: application/json" \
  --data '{"jsonrpc":"2.0","id":"tts1","method":"tools/call","params":{"name":"text_to_speech","arguments":{"prompt":"Hello world!","voice_name":"Kore"}}}'

```

**Tạo video (create_video):**

```bash
curl -s -X POST "http://localhost:8000/mcp" \
  -H "x-api-key: sk-1234" -H "mcp-session-id: <SESSION_ID>" \
  -H "Content-Type: application/json" \
  --data '{"jsonrpc":"2.0","id":"vid1","method":"tools/call","params":{"name":"create_video","arguments":{"prompt":"A cat running, cinematic","filename_hint":"cat_video"}}}'

```

---

## Cấu hình lưu trữ

Kết quả (URL) trả về phụ thuộc vào biến môi trường `GCS_BUCKET`:

1. **Local (Mặc định):** File lưu tại `./static/`.
* URL: `http://localhost:8000/static/<filename>`


2. **GCS (Nếu set GCS_BUCKET):** File upload lên Google Cloud Storage. -> **CHƯA SETUP**
* URL: `https://storage.googleapis.com/<bucket>/<object>`



---

## Cấu trúc dự án

```
MCP/
 ├── src/
 │   ├── main.py        # Entry point, transports
 │   ├── auth.py        # Middleware xác thực
 │   ├── tools/         # Logic xử lý (image, audio, video)
 │   └── storage.py     # Xử lý upload local/GCS
 └── static/            # Thư mục chứa file (lưu trữ self-hosted)

```

## Intern Team
- **Phan Minh Hoài** - *Intake 2025* - University of Science, VNUHCM (HCMUS)
- **Trần Hữu Vũ Phương** - *Intake 2025* - Vietnamese-German University (VGU)
- **Nguyễn Khánh Tài** - *Intake 2025* - University of Information Technology, VNUHCM (UIT)

*Thứ tự các thành viên sắp xếp theo thứ tự bảng chữ cái theo tên*
