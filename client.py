import asyncio
import sys
from mcp import ClientSession
from mcp.client.sse import SseClientTransport

async def main():
    # Dựa vào log của bạn: http://0.0.0.0:8000/mcp
    # Client kết nối tới localhost
    server_url = "http://localhost:8000/mcp"

    print(f"🔄 Đang thử kết nối tới: {server_url} ...")

    try:
        # Kết nối qua SSE Transport
        async with SseClientTransport(server_url) as transport:
            async with ClientSession(transport) as session:
                
                print("🤝 Đang khởi tạo session (Initialize)...")
                # Bước 1: Initialize
                await session.initialize()
                print("✅ Kết nối và khởi tạo thành công!")

                # Bước 2: Lấy danh sách Tools
                print("\n🔍 Đang gọi list_tools()...")
                result = await session.list_tools()

                if not result.tools:
                    print("⚠️ Server không trả về tool nào.")
                else:
                    print(f"🎉 Tìm thấy {len(result.tools)} tools:")
                    print("=" * 40)
                    for tool in result.tools:
                        print(f"🛠️  Tên: {tool.name}")
                        print(f"📝 Mô tả: {tool.description}")
                        print(f"📋 Input Schema: {tool.inputSchema}")
                        print("-" * 40)
                        
    except Exception as e:
        print("\n❌ KẾT NỐI THẤT BẠI!")
        print(f"Lỗi chi tiết: {e}")
        print("-" * 40)
        print("💡 Gợi ý debug:")
        print("1. Nếu lỗi là 405 Method Not Allowed: Server của bạn chỉ nhận POST, trong khi Client SSE dùng GET.")
        print("2. Nếu lỗi 404: Kiểm tra lại đường dẫn '/mcp' trong main.py.")
        print("3. Nếu lỗi Connection Refused: Server chưa chạy hoặc firewall chặn port 8000.")

if __name__ == "__main__":
    # Fix lỗi event loop trên Windows nếu cần
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())