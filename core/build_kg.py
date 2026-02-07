import os
import glob
import json
import re
import time
import datetime
import pandas as pd
from tqdm import tqdm
from config_loader import get_config

from kg.prompts import (
    DIET_KG_EXTRACT_SCHEMA_PROMPT as DIET_SCHEMA_PROMPT,
    DIET_VALID_RELS,
    EXER_KG_EXTRACT_SCHEMA_PROMPT as EXER_SCHEMA_PROMPT,
    EXER_VALID_RELS
)

# Optional import for local model support
try:
    from core.llm import should_use_local, get_unified_llm
    HAS_UNIFIED_LLM = True
except ImportError:
    HAS_UNIFIED_LLM = False

# 处理 PDF 和 Word 的库
import pymupdf4llm
from docx import Document

# ================= 配置加载 =================
config = get_config()
API_MODEL = config.get("api_model", {})
DEEPSEEK_API_KEY = API_MODEL.get("api_key", config.get("deepseek", {}).get("api_key", ""))
DEEPSEEK_BASE_URL = API_MODEL.get("base_url", config.get("deepseek", {}).get("base_url", ""))
MODEL_NAME = API_MODEL.get("model", config.get("deepseek", {}).get("model", "deepseek-chat"))
LOCAL_MODEL_PATH = config.get("local_model_path")

# Determine LLM mode (use api_model by default, fallback to local only if configured)
USE_LOCAL = should_use_local() if HAS_UNIFIED_LLM and LOCAL_MODEL_PATH else False
print(f"[INFO] KG Builder LLM mode: {'local' if USE_LOCAL else 'api'}")
print(f"[INFO] API Model: {MODEL_NAME} @ {DEEPSEEK_BASE_URL}")

# ================= 核心配置区域 =================

# 知识图谱类型配置
KG_CONFIGS = {
    "diet": {
        "input_dir": "data/diet",
        "schema_prompt": DIET_SCHEMA_PROMPT,
        "valid_rels": DIET_VALID_RELS,
        "name": "饮食"
    },
    "exercise": {
        "input_dir": "data/exer",
        "schema_prompt": EXER_SCHEMA_PROMPT,
        "valid_rels": EXER_VALID_RELS,
        "name": "运动"
    }
}

# 结果保存的基础目录 (所有历史记录都会存在这个文件夹下)
OUTPUT_BASE_DIR = "output_history"

# 文本切分设置
CHUNK_SIZE = 1000
OVERLAP = 200

# ===============================================
def read_excel(file_path):
    """
    【新增】读取 Excel 并将每一行转化为自然语言句子
    """
    print(f"📊 正在解析 Excel: {os.path.basename(file_path)}")
    text_content = []
    try:
        # 读取所有工作表 (sheet_name=None 返回字典)
        dfs = pd.read_excel(file_path, sheet_name=None, engine='openpyxl')

        for sheet_name, df in dfs.items():
            if df.empty: continue

            # 1. 清洗表头 (转为字符串，去空格)
            headers = [str(col).strip().replace("\n", "") for col in df.columns]

            # 2. 遍历每一行
            # fillna('') 防止空值报错
            for _, row in df.fillna('').iterrows():
                row_parts = []
                for header, cell_value in zip(headers, row):
                    # 如果单元格不为空，就拼接 "表头是数值"
                    val_str = str(cell_value).strip().replace("\n", " ")
                    if val_str and val_str.lower() != 'nan':
                        row_parts.append(f"{header}是{val_str}")

                # 3. 组合成句子
                if row_parts:
                    # 例: "在表格Sheet1中，药物是二甲双胍，剂量是500mg。"
                    sentence = f"在数据表{sheet_name}中，" + "，".join(row_parts) + "。"
                    text_content.append(sentence)

        return "\n".join(text_content)

    except Exception as e:
        print(f"⚠️ Excel 读取失败 {file_path}: {e}")
        return ""

def read_docx(file_path):
    """ 提取 Word，含表格转自然语言逻辑 """
    try:
        doc = Document(file_path)
        text_content = []
        for para in doc.paragraphs:
            if para.text.strip():
                text_content.append(para.text)
        if doc.tables:
            for table in doc.tables:
                headers = [cell.text.strip().replace("\n", "") for cell in table.rows[0].cells]
                for row in table.rows[1:]:
                    row_cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                    row_parts = []
                    for i in range(len(row_cells)):
                        if i < len(headers) and row_cells[i]:
                            row_parts.append(f"{headers[i]}是{row_cells[i]}")
                    if row_parts:
                        text_content.append("，".join(row_parts) + "。")
        return "\n".join(text_content)
    except Exception as e:
        print(f"⚠️ Word 读取失败 {file_path}: {e}")
        return ""

def read_pdf(file_path):
    """ 提取 PDF (pymupdf4llm) """
    try:
        return pymupdf4llm.to_markdown(file_path)
    except Exception as e:
        print(f"⚠️ PDF 读取失败 {file_path}: {e}")
        return ""

def read_txt(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return ""

def clean_text(text):
    """Clean text by removing citations, page numbers, and other noise."""
    # Remove source citations (e.g., [1], [2,3])
    text = re.sub(r'\[\d+(?:,\s*\d+)*\]', '', text)
    # Remove page numbers (isolated numbers on their own line)
    text = re.sub(r'\n\s*\d+\s*\n', '\n', text)
    # Remove multiple consecutive empty lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def split_text_by_headers(text, chunk_size=CHUNK_SIZE):
    """Split text by Markdown headers (##) to keep sections together."""
    if not text: return []

    # Split by Markdown headers (##)
    sections = re.split(r'(^##\s+.*)', text, flags=re.MULTILINE)

    chunks = []
    current_chunk = ""

    for part in sections:
        if not part: continue

        # If adding this part exceeds limit, save current chunk
        if len(current_chunk) + len(part) > chunk_size:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = part
        else:
            current_chunk += part

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks

def split_text(text, chunk_size=CHUNK_SIZE, overlap=OVERLAP):
    """Legacy fallback: simple chunking by character limit."""
    if not text: return []
    chunks = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        if end < length:
            next_newline = text.find('\n', end, end + 100)
            if next_newline != -1:
                end = next_newline
        chunk = text[start:end]
        if len(chunk.strip()) > 20:
            chunks.append(chunk)
        start += (chunk_size - overlap)
    return chunks

def extract_triplets_with_llm(text_chunk, schema_prompt):
    """
    Extract triplets using LLM (API or local) with JSON Object response format.
    Prioritizes "triplets" key from the response.

    Args:
        text_chunk: Text to extract from
        schema_prompt: Schema prompt to use (DIET or EXER)
    """
    if len(text_chunk.strip()) < 10: return []

    prompt = f"{schema_prompt}\n\n## 待处理文本\n{text_chunk}"
    messages = [
        {"role": "system", "content": "You are a helpful medical assistant. Always output valid JSON."},
        {"role": "user", "content": prompt}
    ]

    try:
        if USE_LOCAL and HAS_UNIFIED_LLM:
            # Use unified LLM (local mode)
            result = get_unified_llm().chat_with_json(
                messages=messages,
                temperature=0.1
            )
            data = result if isinstance(result, dict) else {}
        else:
            # Use API mode
            from openai import OpenAI
            client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=0.1,
                stream=False,
                response_format={'type': 'json_object'}
            )
            content = response.choices[0].message.content.strip()
            data = json.loads(content)

        # Priority 1: Look for "triplets" key (required by new prompt)
        if isinstance(data, dict):
            if "triplets" in data and isinstance(data["triplets"], list):
                return data["triplets"]

            # Priority 2: Look for any list value as fallback
            for val in data.values():
                if isinstance(val, list):
                    return val

        # Priority 3: Direct list response
        elif isinstance(data, list):
            return data

        return []

    except json.JSONDecodeError as e:
        print(f"⚠️ JSON解析失败: {e}, 内容片段: {content[:100] if 'content' in dir() else 'N/A'}...")
        return []
    except Exception as e:
        print(f"❌ LLM 调用失败: {e}")
        time.sleep(2)
        return []

def build_knowledge_graph(kg_type: str, config: dict) -> dict:
    """
    Build knowledge graph for a specific type (diet or exercise).

    Args:
        kg_type: Type of knowledge graph ('diet' or 'exercise')
        config: Configuration dict with schema_prompt, valid_rels, name, input_dir

    Returns:
        Dict with stats about the build
    """
    schema_prompt = config["schema_prompt"]
    valid_rels = config["valid_rels"]
    kg_name = config["name"]
    input_dir = config["input_dir"]

    # 检查输入文件夹
    if not os.path.exists(input_dir):
        os.makedirs(input_dir)
        print(f"[{kg_name} KG] 请创建 {input_dir} 并放入文件")
        return {"status": "skipped", "reason": "input_dir_not_found", "triplets": 0}

    # 生成本次运行的输出文件夹
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    current_output_dir = os.path.join(OUTPUT_BASE_DIR, f"{kg_type.capitalize()}_{timestamp}")

    # 创建文件夹
    os.makedirs(current_output_dir, exist_ok=True)
    print(f"📂 [{kg_name} KG] 本次结果将保存在: {current_output_dir}")

    # 扫描文件
    files = glob.glob(os.path.join(input_dir, "*.pdf")) + \
        glob.glob(os.path.join(input_dir, "*.docx")) + \
        glob.glob(os.path.join(input_dir, "*.txt")) + \
        glob.glob(os.path.join(input_dir, "*.xlsx"))

    if not files:
        print(f"⚠️ [{kg_name} KG] '{input_dir}' 文件夹为空，没有找到文件。")
        return {"status": "skipped", "reason": "no_files", "triplets": 0}

    print(f"🔍 [{kg_name} KG] 发现 {len(files)} 个文件，准备开始提取...")

    all_triplets = []
    seen_hashes = set()
    processed_files_log = []
    start_time = time.time()

    # 循环处理
    for file_path in tqdm(files, desc=f"{kg_name} KG 进度"):
        file_name = os.path.basename(file_path)
        processed_files_log.append(file_name)

        ext = file_path.lower()
        if ext.endswith(".pdf"): content = read_pdf(file_path)
        elif ext.endswith(".docx"): content = read_docx(file_path)
        elif ext.endswith(".xlsx"): content = read_excel(file_path)
        else: content = read_txt(file_path)

        if not content: continue

        # Clean text and split by headers
        cleaned_content = clean_text(content)
        chunks = split_text_by_headers(cleaned_content)

        for chunk in tqdm(chunks, desc=f"解析 {file_name[:10]}", leave=False):
            triplets = extract_triplets_with_llm(chunk, schema_prompt)

            for t in triplets:
                if "head" in t and "relation" in t and "tail" in t:
                    if t['relation'] in valid_rels:
                        t_hash = f"{t['head']}_{t['relation']}_{t['tail']}"
                        if t_hash not in seen_hashes:
                            seen_hashes.add(t_hash)
                            t["source"] = file_name
                            all_triplets.append(t)

                time.sleep(0.1)

    # 保存结果
    duration = time.time() - start_time

    output_json_path = os.path.join(current_output_dir, f"{kg_type}_triplets.json")
    output_csv_path = os.path.join(current_output_dir, f"{kg_type}_triplets.csv")
    log_path = os.path.join(current_output_dir, "process_log.txt")

    print("-" * 40)
    print(f"✅ [{kg_name} KG] 提取完成！耗时: {duration:.2f}秒")
    print(f"🕸️  共获得 {len(all_triplets)} 个唯一三元组。")

    # 保存 JSON
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(all_triplets, f, indent=4, ensure_ascii=False)

    # 保存 CSV
    df = pd.DataFrame(all_triplets)
    if not df.empty:
        cols = ["head", "relation", "tail", "source"]
        existing = [c for c in cols if c in df.columns]
        df = df[existing]
        df.to_csv(output_csv_path, index=False, encoding='utf_8_sig')

    # 保存日志
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write(f"运行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"知识图谱类型: {kg_name}\n")
        f.write(f"耗时: {duration:.2f} 秒\n")
        f.write(f"提取三元组数量: {len(all_triplets)}\n")
        f.write(f"输入目录: {input_dir}\n")
        f.write("\n处理的文件列表:\n")
        for fname in processed_files_log:
            f.write(f"- {fname}\n")

    print(f"💾 [{kg_name} KG] 结果已保存至: {current_output_dir}")

    return {
        "status": "success",
        "kg_type": kg_type,
        "kg_name": kg_name,
        "triplets": len(all_triplets),
        "duration": duration,
        "output_dir": current_output_dir
    }


def main():
    """Build both diet and exercise knowledge graphs by default."""
    # 检查命令行参数
    kg_types_to_build = None
    for arg in sys.argv[1:]:
        if arg.startswith("--kg="):
            kg_types_to_build = [arg.replace("--kg=", "").lower()]
            break
        elif arg in ["-h", "--help"]:
            print("""
用法: python -m core.build_kg [选项]

选项:
  --kg=diet      只构建饮食知识图谱
  --kg=exercise  只构建运动知识图谱
  --kg=all       构建饮食和运动知识图谱（默认行为）
  -h, --help     显示此帮助信息

默认行为:
  如果没有指定选项，则同时构建饮食和运动知识图谱。
            """)
            return

    # 如果没有指定，默认构建两种 KG
    if kg_types_to_build is None or kg_types_to_build[0] == "all":
        kg_types_to_build = ["diet", "exercise"]

    print("=" * 50)
    print(f"🚀 开始构建知识图谱...")
    print(f"📋 类型: {', '.join(kg_types_to_build)}")
    print("=" * 50)

    total_stats = {
        "total_triplets": 0,
        "total_duration": 0,
        "results": []
    }

    for kg_type in kg_types_to_build:
        if kg_type in KG_CONFIGS:
            print()
            stats = build_knowledge_graph(kg_type, KG_CONFIGS[kg_type])
            total_stats["results"].append(stats)
            total_stats["total_triplets"] += stats.get("triplets", 0)
            total_stats["total_duration"] += stats.get("duration", 0)
        else:
            print(f"⚠️ 未知知识图谱类型: {kg_type}")

    # 汇总
    print()
    print("=" * 50)
    print("📊 知识图谱构建汇总")
    print("=" * 50)
    print(f"总三元组数量: {total_stats['total_triplets']}")
    print(f"总耗时: {total_stats['total_duration']:.2f}秒")
    print()

    # 显示每个 KG 的状态
    for stats in total_stats["results"]:
        status = "✅" if stats.get("status") == "success" else "⚠️"
        print(f"  {status} {stats.get('kg_name', 'Unknown')} KG: {stats.get('triplets', 0)} 三元组")

    print()
    print("📌 文件位置:")
    for stats in total_stats["results"]:
        if stats.get("output_dir"):
            print(f"  - {stats.get('kg_name', '')}: {stats['output_dir']}")


import sys

if __name__ == "__main__":
    main()
