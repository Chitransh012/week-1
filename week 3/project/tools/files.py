import os
import sys
import json
import glob as glob_module
from openai import OpenAI
from dotenv import load_dotenv
import uuid
from datetime import datetime, timezone
load_dotenv()

WORKSPACE_ROOT=os.path.abspath(os.environ.get("WORKSPACE_ROOT","."))
SESSION_DIRS=os.path.join(WORKSPACE_ROOT,".agent/sessions")
AGENTS_PATHS = ("AGENTS.md", ".agent/AGENTS.md")
MAX_ITERATIONS=10
MAX_READ_CHARS=12_000


client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)
MODEL = "openrouter/free"

BASE_PROMPT = "You are Research Desk, a helpful research assistant."

def resolve_path(path:str)->str:
    full_path=os.path.abspath(os.path.join(WORKSPACE_ROOT,path))
    if not full_path.startswith(WORKSPACE_ROOT):
        raise PermissionError("path escaped workspace root")
    return full_path

def read_file(path:str,start_line:int=1,read_lines:int=200)->dict:
    try:
        full_path=resolve_path(path)
        if not os.path.exists(full_path):
            return {"error":f"some error in finding full path"}
        with open(full_path,"r",encoding="utf-8") as f:
            lines=f.readlines()
        total_lines=len(lines)
        if start_line<1 or start_line>total_lines and total_lines>0:
            return {"error": f"Invalid start_line {start_line}. File has {total_lines} lines."}
        window=lines[start_line-1:start_line-1+read_lines]
        has_more=(start_line-1+read_lines)<total_lines
        content_lines=[]
        chars_read=0
        for idx,line in enumerate(window):
            line_num=start_line+idx
            formatted_line=f"{line_num}|{line}"
            chars_read+=len(formatted_line)
            if chars_read>MAX_READ_CHARS:
                content_lines.append(f"... Truncated after exceeding character safety cap ...")
                has_more = True
                break
            content_lines.append(formatted_line)
        return {
            "content": "".join(content_lines),
            "start_line": start_line,
            "total_lines": total_lines,
            "has_more": has_more
        }
    except Exception as e:
        return {"error": str(e)}

def write_file(path:str,content:str)->dict:
    full_path=resolve_path(path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    if not os.path.exists(full_path):
        return {"error":f"error occured in finding path"}
    try:
        with open(full_path,"w",encoding="utf-8") as f:
            f.write(content)
            return {"content": f"Successfully wrote file to {path}."}
    except Exception as e:
        return {"error":f"error occured :{str(e)}"}
    
def edit_file(
    path: str,
    operation: str,
    start_line: int,
    end_line: int | None = None,
    content: str | None = None,
) -> dict:
    full_path=resolve_path(path)
    if not os.path.exists(full_path):
        return {"error":f"error occured in finding path"}
    try:
        with open(full_path,"r",encoding="utf-8") as f:
            lines=f.readlines()
        orig_lines=list(lines)
        op=operation.lower()
        new_lines = content.splitlines(keepends=True) if content else []
        if new_lines and not new_lines[-1].endswith('\n'):
            new_lines[-1] += '\n'
        if op=="replace":
            if end_line is None:
                return {"error":"end line not specified"}
            lines[start_line-1:end_line]=new_lines
        elif op=="delete":
            if end_line is None:
                return {"error":"end line not specified"}
            lines[start_line-1:end_line]=[]
        elif op=="append":
            lines[start_line:start_line]=new_lines
        else:
            return {"error":"unknown operation passed {op}"}
        with open(full_path,"w",encoding="utf-8") as f:
            f.writelines(lines)
        return {
            "content": f"Surgically applied '{op}' edit on {path}.",
            "diff_preview": f"Original line count: {len(orig_lines)}\n+++ Updated line count: {len(lines)}"
        }
    except Exception as e:
        return {"error": str(e)}
    
def list_files(path:str=".",pattern:str="*")->dict:
    full_path=resolve_path(path)
    if not os.path.exists(full_path):
        return {"error":f"error occured in finding path"}
    try:
        search_pattern=os.path.join(full_path,pattern)
        matches=glob_module.glob(search_pattern,recursive=True)
        file_list=[]
        for m in matches:
            if os.path.isfile(m):
                rel_path=os.path.relpath(m,WORKSPACE_ROOT)
                file_list.append(rel_path)
        return {"content": json.dumps(file_list, indent=2)}
    except Exception as e:
        return {"error": str(e)}
    
if __name__ == "__main__":
    print("--- Running Local File Tools Sanity Check ---")
    
    # 1. Test Write
    test_note = "notes/test_memo.md"
    print(write_file(test_note, "Line 1: Hello World\nLine 2: AI Research Agent\nLine 3: End of file\n"))
    
    # 2. Test Read with numbered pagination lines
    print("\nReading File:")
    print(read_file(test_note, start_line=1, read_lines=5))
    
    # 3. Test Surgical Line Replacement Patch
    print("\nModifying Line 2:")
    print(edit_file(test_note, operation="replace", start_line=2, end_line=2, content="Line 2: Upgraded Memory Layer\n"))
    
    # 4. Read again to verify changes applied cleanly
    print("\nVerifying Updated File:")
    print(read_file(test_note, start_line=1, read_lines=5))
    
    # Clean up test artifact safely
    if os.path.exists(test_note):
        os.remove(test_note)