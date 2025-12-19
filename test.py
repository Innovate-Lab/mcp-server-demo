from __future__ import annotations

import os
import asyncio
import logging
import base64
import time
import httpx
import re
from typing import Optional, List, Any, Dict

# --- CẤU HÌNH ---
OUTPUT_FOLDER = "Video_Results"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger(__name__)

# Danh sách Model (Ưu tiên Veo 3.1)
FALLBACK_MODELS = [
    "veo-3.0-fast-generate-001",
    "veo-3.1-fast-generate-001"
]
TIMEOUT_SECONDS = 600 
POLLING_INTERVAL = 10 

# --- HÀM LƯU FILE LOCAL ---
try:
    from src.storage import save_file_locally
except ImportError:
    async def save_file_locally(content: bytes, extension: str, filename_hint: str) -> dict:
        clean_name = re.sub(r'[^\w\-]', '_', filename_hint)
        timestamp = int(time.time())
        filename = f"{clean_name}_{timestamp}.{extension}"
        file_path = os.path.join(OUTPUT_FOLDER, filename)
        with open(file_path, "wb") as f:
            f.write(content)
        abs_path = os.path.abspath(file_path)
        logger.info(f"💾 Đã lưu file tại: {abs_path}")
        return {"url": abs_path, "gs_uri": ""}

# --- CÁC HÀM HỖ TRỢ API ---
def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in environment variables.")
    return genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})

async def _download_video_from_uri(uri: str) -> bytes:
    api_key = os.getenv("GEMINI_API_KEY")
    headers = {}
    if "googleapis.com" in uri and api_key:
        headers["x-goog-api-key"] = api_key

    async with httpx.AsyncClient() as client:
        logger.info(f"⬇️ Đang tải video từ: {uri}")
        response = await client.get(uri, headers=headers, follow_redirects=True)
        response.raise_for_status()
        return response.content

async def _poll_operation_via_rest(operation_name: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    start_time = time.time()
    base_url = "https://generativelanguage.googleapis.com/v1alpha"
    url = operation_name if operation_name.startswith("http") else f"{base_url}/{operation_name}"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    logger.info(f"⏳ Bắt đầu theo dõi tiến trình: {url}")
    async with httpx.AsyncClient() as http_client:
        while True:
            if int(time.time() - start_time) > TIMEOUT_SECONDS:
                raise TimeoutError("Quá thời gian chờ.")
            try:
                response = await http_client.get(url, headers=headers)
                if response.status_code != 200:
                    await asyncio.sleep(POLLING_INTERVAL)
                    continue
                data = response.json()
                if data.get("done", False):
                    if "error" in data: raise RuntimeError(data['error'])
                    payload = data.get("response") or data.get("result") or data
                    
                    if "generateVideoResponse" in payload:
                        val = payload["generateVideoResponse"]
                        if "generatedSamples" in val: return val["generatedSamples"][0]["video"]["uri"]
                    if "generatedSamples" in payload: return payload["generatedSamples"][0]["video"]["uri"]
                    if "generatedVideos" in payload: return payload["generatedVideos"][0]["video"]["uri"]
                    if "generated_videos" in payload: return payload["generated_videos"][0]["video"]["uri"]
                    
                    logger.error(f"Unknown Payload: {payload}")
                    raise ValueError("Không tìm thấy URI video.")
            except Exception:
                pass
            await asyncio.sleep(POLLING_INTERVAL)

async def _prepare_inputs(prompt: str, image_url: str | None, image_base64: str | None) -> Optional[types.Image]:
    """
    [CẬP NHẬT] Sử dụng types.Image với image_bytes (Raw) và mime_type.
    SDK sẽ tự động chuyển Raw Bytes thành Base64 khi gửi đi.
    """
    image_bytes = None
    if image_url:
        logger.info(f"📥 Đang tải ảnh từ URL: {image_url}")
        async with httpx.AsyncClient() as client:
            resp = await client.get(image_url, follow_redirects=True)
            if resp.status_code != 200:
                raise ValueError(f"Lỗi tải ảnh: {resp.status_code}")
            image_bytes = resp.content
    elif image_base64:
        image_bytes = base64.b64decode(image_base64)
    
    if image_bytes:
        # Quan trọng: Cung cấp cả image_bytes (Raw) và mime_type
        # SDK sẽ map image_bytes -> bytesBase64Encoded trong JSON request
        return types.Image(
            image_bytes=image_bytes, 
            mime_type="image/jpeg" # Hoặc image/png, Veo sẽ tự xử lý
        )
    
    return None

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
    
    try:
        client = _get_client()
    except Exception as e:
        return {"error": str(e)}

    # Chuẩn bị Image Input (types.Image)
    image_input = None
    try:
        image_input = await _prepare_inputs(prompt, image_url, image_base64)
    except Exception as e:
        return {"error": f"Input Error: {str(e)}"}

    generation_config = {"aspectRatio": aspect_ratio, "durationSeconds": 8}
    if negative_prompt: generation_config["negativePrompt"] = negative_prompt

    last_error = None
    saved_video_info = None
    used_model = None

    for model_name in FALLBACK_MODELS:
        try:
            logger.info(f"🚀 Model: {model_name}")
            
            # Sử dụng cú pháp tham số image=... VÀ prompt=String
            if image_input:
                logger.info("ℹ️ Mode: Image-to-Video (types.Image)")
                response = await client.aio.models.generate_videos(
                    model=model_name,
                    prompt=prompt,       # String
                    image=image_input,   # types.Image
                    config=generation_config
                )
            else:
                logger.info("ℹ️ Mode: Text-to-Video")
                response = await client.aio.models.generate_videos(
                    model=model_name,
                    prompt=prompt,
                    config=generation_config
                )

            op_name = response.name if hasattr(response, 'name') else str(response)
            logger.info(f"📡 Op ID: {op_name}")
            
            video_uri = await _poll_operation_via_rest(op_name)
            video_bytes = await _download_video_from_uri(video_uri)
            
            saved = await save_file_locally(video_bytes, "mp4", filename_hint or "veo_generated")
            saved_video_info = saved
            used_model = model_name
            break 

        except Exception as e:
            logger.warning(f"❌ {model_name} Failed: {str(e)}")
            last_error = e
            continue

    if not saved_video_info:
        return {"error": f"Failed: {str(last_error)}", "prompt": prompt, "model": "failed"}

    return {
        "prompt": prompt,
        "model": used_model,
        "url": saved_video_info["url"],
        "gs_uri": saved_video_info.get("gs_uri", "")
    }

if __name__ == "__main__":
    async def main():
        print("\n--- FINAL TEST (VEO 3.0 Corrected) ---")
        
        target_image_url = "https://imgs.search.brave.com/pYaCqSFk0YB33dVMPQRjzbyNs37L5xq9usgq-5rauTE/rs:fit:860:0:0:0/g:ce/aHR0cHM6Ly9jZG4x/MS5iaWdjb21tZXJj/ZS5jb20vcy1hMzFj/OC9pbWFnZXMvc3Rl/bmNpbC82MDB4NjAw/L3Byb2R1Y3RzLzMw/NjUyLzM0MjQ5LzQ1/NzMxMDI2MTMyODhf/Xzk5OTIzLjE2OTcy/OTE4NDcuanBnP2M9/Mg"
        
        result = await create_video(
            prompt="Cinematic shot, cậu bé chạy vui vẻ, 4k resolution",
            filename_hint="veo3_correct",
            image_url=target_image_url
        )
        
        if "error" in result:
            print(f"\n❌ ERROR: {result['error']}")
        else:
            print(f"\n✅ SUCCESS: {result['url']}")
            
    asyncio.run(main())