import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from tavily import TavilyClient 
from dotenv import load_dotenv
load_dotenv()

tavily_api_key = os.getenv("TAVILY_API_KEY")
tavily_client = TavilyClient(api_key=tavily_api_key) if tavily_api_key else None

def search_tavily_context(query: str) -> str:
    """
    Dùng Tavily để lấy thông tin đã được làm sạch và tối ưu cho LLM.
    """
    if not tavily_client:
        return "Lỗi: Chưa cấu hình TAVILY_API_KEY."
        
    try:
        # search_depth="advanced" giúp lấy nội dung sâu, chất lượng hơn
        # include_answer=True để Tavily tự trả lời ngắn gọn trước
        response = tavily_client.search(
            query=query,
            search_depth="advanced",
            max_results=3,
            include_answer=True,
            include_raw_content=False
        )
        
        context_parts = []
        
        # 1. Câu trả lời trực tiếp từ Tavily (nếu có)
        if response.get('answer'):
            context_parts.append(f"--- TÓM TẮT NHANH (Tavily) ---\n{response['answer']}")
            
        # 2. Nội dung chi tiết từ các trang web
        context_parts.append("\n--- CHI TIẾT CÁC NGUỒN WEB ---")
        for res in response.get('results', []):
            title = res.get('title', 'No Title')
            content = res.get('content', '') # Đây là text sạch Tavily đã crawl
            url = res.get('url', '')
            context_parts.append(f"Nguồn: {title} ({url})\nNội dung: {content}\n")
            
        return "\n".join(context_parts)
        
    except Exception as e:
        print(f"Tavily Error: {e}")
        return ""

import wikipedia
wikipedia.set_lang("vi")

def search_wikipedia(query: str) -> str:
    try:
        results = wikipedia.search(query)
        if not results: return ""
        page = wikipedia.page(results[0])
        return f"--- NGUỒN WIKIPEDIA: {page.title} ---\n{page.content[:2000]}...\n"
    except Exception:
        return ""

async def get_web_context(query: str) -> str:
    """Tổng hợp thông tin: Ưu tiên Tavily + Wikipedia bổ trợ."""
    loop = asyncio.get_running_loop()
    
    with ThreadPoolExecutor() as pool:
        # Chạy song song Wiki và Tavily
        wiki_future = loop.run_in_executor(pool, search_wikipedia, query)
        tavily_future = loop.run_in_executor(pool, search_tavily_context, query)
        
        wiki_res, tavily_res = await asyncio.gather(wiki_future, tavily_future)
    
    # Kết hợp kết quả
    full_context = ""
    
    if tavily_res:
        full_context += tavily_res + "\n\n"
        
    if wiki_res:
        full_context += wiki_res
    
    if not full_context:
        return "Không tìm thấy thông tin online. Hãy trả lời dựa trên kiến thức có sẵn."
        
    return full_context
    