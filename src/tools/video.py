from __future__ import annotations
import asyncio
import time
import httpx
import os
from pathlib import Path

# Danh sách model theo thứ tự ưu tiên
FALLBACK_MODELS = [
    "veo-3.0-generate-001",
    "veo-3.0-fast-generate-001",
    "veo-3.1-generate-001",
    "veo-3.1-fast-generate-001",
    "veo-3.1-preview-001"
]

async def create_video(
    prompt: str,
    negative_prompt: str | None = None,
    aspect_ratio: str = "16:9",
    resolution: str = "720p",
    image_url: str | None = None,
    image_base64: str | None = None,
    image_mime_type: str | None = None,
    filename_hint: str | None = None,
) -> dict:
    
    # Tạo thư mục 'downloads' nếu chưa có để lưu file cục bộ
    download_dir = Path("downloads")
    download_dir.mkdir(exist_ok=True)
    
    last_error = None
    
    for model in FALLBACK_MODELS:
        try:
            print(f"Đang thử model: {model}...")
            
            # 1. Giả định gọi API Veo để lấy Task ID
            # task_id = await veo_client.create_task(model=model, ...)
            task_id = "mock_id" 

            # 2. Polling logic (Chờ video sẵn sàng trên server Google)
            timeout = 600  
            start_time = time.time()
            video_source_url = None
            
            while time.time() - start_time < timeout:
                # status_resp = await veo_client.check_status(task_id)
                status = "SUCCEEDED" # Mock
                
                if status == "SUCCEEDED":
                    video_source_url = "https://google.internal/temp_video.mp4" # URL tạm từ Google
                    break
                await asyncio.sleep(10)
            
            if not video_source_url:
                raise Exception("Timeout: Không nhận được phản hồi từ Google sau 10 phút")

            # 3. Tải video về RAM và ghi trực tiếp vào file cục bộ
            # Không sử dụng save_file_locally (để tránh upload GCS)
            local_filename = f"{filename_hint or 'video'}_{int(time.time())}.mp4"
            local_path = download_dir / local_filename

            async with httpx.AsyncClient() as client:
                response = await client.get(video_source_url)
                if response.status_code == 200:
                    # Ghi file ra ổ cứng local
                    with open(local_path, "wb") as f:
                        f.write(response.content)
                else:
                    raise Exception(f"Không thể tải video từ link Google: {response.status_code}")

            # 4. Trả về thông tin với URL và GS_URI để trống (hoặc để đường dẫn local)
            return {
                "prompt": prompt,
                "model": model,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "mime_type": "video/mp4",
                "url": str(local_path.absolute()), # Trả về đường dẫn file trên máy
                "gs_uri": None,                    # Tắt upload nên không có gs_uri
                "local_saved": True
            }

        except Exception as e:
            print(f"Lỗi với model {model}: {str(e)}")
            last_error = e
            continue

    raise Exception(f"Thất bại sau khi thử tất cả model. Lỗi cuối: {str(last_error)}")