import os
import glob
import json
import re
import time
import datetime
import pandas as pd
from openai import OpenAI
from tqdm import tqdm
from ..agents.diet.prompts import (
    DIET_KG_EXTRACT_SCHEMA_PROMPT as SCHEMA_PROMPT,
    DIET_VALID_RELS
)

# 处理 PDF 和 Word 的库
import pymupdf4llm
from docx import Document

# ================= 配置加载 =================
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

DEEPSEEK_API_KEY = config["deepseek"]["api_key"]
DEEPSEEK_BASE_URL = config["deepseek"]["base_url"]
MODEL_NAME = config["deepseek"]["model"]

# ================= 核心配置区域 =================
# 1. 待处理文献路径
INPUT_DIR = "data"

# 2. 结果保存的基础目录 (所有历史记录都会存在这个文件夹下)
OUTPUT_BASE_DIR = "output_history"

# 4. 文本切分设置
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

def extract_triplets_with_deepseek(client, text_chunk):
    """
    Extract triplets using DeepSeek with JSON Object response format.
    Prioritizes "triplets" key from the response.
    """
    if len(text_chunk.strip()) < 10: return []

    prompt = f"{SCHEMA_PROMPT}\n\n## 待处理文本\n{text_chunk}"

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a helpful medical assistant. Always output valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            stream=False,
            response_format={'type': 'json_object'}
        )
        content = response.choices[0].message.content.strip()

        try:
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
            print(f"⚠️ JSON解析失败: {e}, 内容片段: {content[:100]}...")
            return []

    except Exception as e:
        print(f"❌ API 调用失败: {e}")
        time.sleep(2)
        return []

def main():
    # 1. 检查输入文件夹
    if not os.path.exists(INPUT_DIR):
        os.makedirs(INPUT_DIR)
        print(f"请创建 {INPUT_DIR} 并放入文件")
        return

    # 2. 生成本次运行的输出文件夹 (格式: Output_History/Run_20231223_143005)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    current_output_dir = os.path.join(OUTPUT_BASE_DIR, f"Run_{timestamp}")

    # 创建文件夹
    os.makedirs(current_output_dir, exist_ok=True)
    print(f"📂 本次结果将保存在: {current_output_dir}")

    # 3. 初始化客户端
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

    # 4. 扫描文件
    files = glob.glob(os.path.join(INPUT_DIR, "*.pdf")) + \
        glob.glob(os.path.join(INPUT_DIR, "*.docx")) + \
        glob.glob(os.path.join(INPUT_DIR, "*.txt")) + \
        glob.glob(os.path.join(INPUT_DIR, "*.xlsx"))

    if not files: 
        print(f"⚠️ '{INPUT_DIR}' 文件夹为空，没有找到文件。")
        return

    print(f"🔍 发现 {len(files)} 个文件，准备开始提取...")

    all_triplets = []
    seen_hashes = set()
    processed_files_log = [] # 记录处理了哪些文件
    start_time = time.time()

    valid_rels = DIET_VALID_RELS

    # 5. 循环处理
    for file_path in tqdm(files, desc="总进度"):
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
            triplets = extract_triplets_with_deepseek(client, chunk)

            for t in triplets:
                if "head" in t and "relation" in t and "tail" in t:
                    if t['relation'] in valid_rels:
                        t_hash = f"{t['head']}_{t['relation']}_{t['tail']}"
                        if t_hash not in seen_hashes:
                            seen_hashes.add(t_hash)
                            t["source"] = file_name
                            all_triplets.append(t)

                time.sleep(0.1)

    # 6. 保存结果到新创建的文件夹
    duration = time.time() - start_time

    # 定义新路径
    output_json_path = os.path.join(current_output_dir, "kg_triplets.json")
    output_csv_path = os.path.join(current_output_dir, "kg_triplets.csv")
    log_path = os.path.join(current_output_dir, "process_log.txt")

    print("-" * 40)
    print(f"✅ 提取完成！耗时: {duration:.2f}秒")
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

    # 保存日志 (方便你以后知道这个文件夹里是哪些数据跑出来的)
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write(f"运行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"耗时: {duration:.2f} 秒\n")
        f.write(f"提取三元组数量: {len(all_triplets)}\n")
        f.write("\n处理的文件列表:\n")
        for fname in processed_files_log:
            f.write(f"- {fname}\n")

    print(f"💾 结果已保存至文件夹: {current_output_dir}")

if __name__ == "__main__":
    main()