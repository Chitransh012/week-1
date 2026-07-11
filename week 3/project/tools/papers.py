import os
import re
import requests
from dotenv import load_dotenv
load_dotenv()
HF_TOKEN = os.environ.get("HF_TOKEN", "")
MAX_CONTENT_CHARS = 15_000
def clean_arxiv_id(raw_id:str)->str:
    match=re.search(r'(\d{4}\.\d{4,5})', raw_id)
    if match:
        return match.group(1)
    return raw_id.strip()
def get_headers()->dict:
    headers = {}
    if HF_TOKEN:
        headers["Authorization"] = f"Bearer {HF_TOKEN}"
    return headers
def paper_search(query:str)->dict:
    url = "https://huggingface.co/api/papers/search"
    params = {"q": query}
    try:
        response=requests.get(url,params=params,headers=get_headers(),timeout=10)
        if response.status_code !=200:
            return {"error":f"hugging face api gave error {response.status_code}"}
        results=response.json()
        parsed_papers=[]
        for item in results:
            paper_data = item.get("paper", item) if isinstance(item, dict) else item
            parsed_papers.append({
            "id": paper_data.get("id", "unknown id"),
            "title": paper_data.get("title", "unknown title"),
            "summary": paper_data.get("summary", "")[:300] + "..."
            })
        return {"results": parsed_papers[:8]}
    except Exception as e:
        return {"error": f"Failed to perform academic search: {str(e)}"}
def read_paper(arxiv_id:str)->dict:
    clean_id = clean_arxiv_id(arxiv_id)
    meta_url = f"https://huggingface.co/api/papers/{clean_id}"
    md_url = f"https://huggingface.co/papers/{clean_id}.md" 
    output = {"id": clean_id, "title": "Unknown Title", "abstract": "", "content": ""}
    try:
        meta_res=requests.get(meta_url,headers=get_headers(),timeout=10)
        if meta_res.status_code==200:
            meta_data = meta_res.json()
            output["title"]=meta_data.get("title", output["title"])
            output["abstract"]=meta_data.get("summary","")
    except Exception:
        pass
    try:
        md_res=requests.get(md_url,headers=get_headers(),timeout=10)
        if md_res.status_code == 200:
            md_text=md_res.text
            if len(md_text)>MAX_CONTENT_CHARS:
                output["content"]=md_text[:MAX_CONTENT_CHARS] + "\n\n... [Truncated due to context engine length safety limits] ..."
            else:
                output["content"]=md_text
        elif md_res.status_code == 404:
            return {
                "error": f"Paper {clean_id} is not fully indexed on Hugging Face repository mirrors yet.",
                "fallback_instruction": f"Please fall back and collect data by calling web_fetch('https://arxiv.org/abs/{clean_id}') instead."
            }
        else:
            output["content"] = f"Failed to retrieve markdown body content. Status Code: {md_res.status_code}"
    except Exception as e:
        output["content"] = f"Error reading markdown stream: {str(e)}"
        
    return output
if __name__ == "__main__":
    # Quick execution validation check
    print("--- Testing HF Paper Search ---")
    search_test = paper_search("FlashAttention")
    print(search_test)
    
    print("\n--- Testing HF Paper Read ---")
    # Pulling down FlashAttention sequence records
    read_test = read_paper("2205.14135")
    print(f"Title: {read_test['title']}")
    print(f"Content Length: {len(read_test['content'])} characters collected.")
        