import os
import base64
import io
import json
import requests
import concurrent.futures
from flask import Flask, request, jsonify
from flask_cors import CORS
from PIL import Image
from PIL import ImageDraw, ImageFont
import fitz # PyMuPDF

app = Flask(__name__)
CORS(app)

# 配置
API_KEY = os.environ.get("OPENAI_API_KEY") or os.environ.get("API_KEY") or ""
API_URL = os.environ.get("OPENAI_API_URL") or "https://api.apimart.ai/v1/responses"
# 按需求：使用 GPT-5.2 + thinking 模式
MODEL_NAME = os.environ.get("OPENAI_MODEL") or "gpt-5.2"

# 并发/超时配置（可按需要调整）
MAX_WORKERS_OCR = int(os.environ.get("MAX_WORKERS_OCR", "6"))
MAX_WORKERS_MARK = int(os.environ.get("MAX_WORKERS_MARK", "4"))
TIMEOUT_OCR_SECONDS = int(os.environ.get("TIMEOUT_OCR_SECONDS", "60"))
TIMEOUT_GRADE_SECONDS = int(os.environ.get("TIMEOUT_GRADE_SECONDS", "300"))
TIMEOUT_MARK_SECONDS = int(os.environ.get("TIMEOUT_MARK_SECONDS", "90"))

def _post_responses(payload: dict, timeout: int):
    if not API_KEY:
        raise RuntimeError("Missing API key. Please set OPENAI_API_KEY (or API_KEY).")
    res = requests.post(
        API_URL,
        json=payload,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        timeout=timeout,
    )
    res.raise_for_status()
    return res.json()

def _extract_text_from_responses(data: dict) -> str:
    """
    兼容多种返回结构，提取主要文本内容。
    """
    if isinstance(data, dict):
        if "output" in data and data["output"]:
            # OpenAI Responses 风格
            try:
                return data["output"][0]["content"][0]["text"]
            except Exception:
                pass
        if "choices" in data and data["choices"]:
            try:
                return data["choices"][0]["message"]["content"]
            except Exception:
                pass
        if "data" in data and isinstance(data["data"], dict) and "choices" in data["data"]:
            try:
                return data["data"]["choices"][0]["message"]["content"]
            except Exception:
                pass
    raise ValueError(f"API response format unknown: {data}")

def _safe_json_loads(s: str):
    """
    尝试把模型输出解析为 JSON（允许被 ```json 包裹）。
    """
    if not isinstance(s, str):
        raise TypeError("Expected string for JSON parsing.")
    text = s.strip()
    if text.startswith("```"):
        # strip fenced code block
        lines = text.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
            text = "\n".join(lines[1:-1]).strip()
    return json.loads(text)

def encode_image(image):
    """将 PIL Image 转为 Base64"""
    buffered = io.BytesIO()
    if image.mode != 'RGB':
        image = image.convert('RGB')
    # 质量 85，保证手写笔迹清晰
    image.save(buffered, format="JPEG", quality=85)
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

def process_single_page(page_image, page_num):
    """处理单页图片的函数"""
    print(f"Processing Page {page_num}...")
    try:
        base64_image = encode_image(page_image)
        
        prompt = f"""
        你是一位老师的助手。这是试卷的第 {page_num} 页。
        请帮我查看学生在这页上的作答情况。
        
        任务：
        1. 识别这页上的题目（如果有）。
        2. 识别学生的手写答案。
        3. 如果是空白页或无内容，请忽略。
        
        请输出纯文本内容，公式使用 LaTeX 格式。
        """

        payload = {
            "model": MODEL_NAME,
            # thinking 模式（Responses API 常见字段）
            "reasoning": {"effort": "high"},
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": f"data:image/jpeg;base64,{base64_image}"}
                    ]
                }
            ]
        }

        data = _post_responses(payload, timeout=TIMEOUT_OCR_SECONDS)
        content = _extract_text_from_responses(data)
        
        return f"--- 第 {page_num} 页内容 ---\n{content}\n"
    except Exception as e:
        print(f"Error on page {page_num}: {e}")
        return f"--- 第 {page_num} 页识别失败: {str(e)} ---\n"

def _build_grading_schema():
    """
    评分结构化输出：逐题（空白题=0），给最终总分，并提供错误点摘要。
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "exam_grading",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "subject": {"type": "string"},
                    "max_per_question": {"type": "number"},
                    "questions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "question_id": {"type": "string"},
                                "is_blank": {"type": "boolean", "description": "学生该题是否空白/无作答"},
                                "score": {"type": "number", "description": "该题得分；若 is_blank=true 则必须为 0"},
                                "max_score": {"type": "number"},
                                "mistakes": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "properties": {
                                            "summary": {"type": "string", "description": "错误点一句话"},
                                            "why_wrong": {"type": "string"},
                                            "correct_idea": {"type": "string"},
                                        },
                                        "required": ["summary"],
                                    },
                                },
                                "solution": {"type": "string", "description": "正确解法/要点（可含 LaTeX）"},
                            },
                            "required": ["question_id", "is_blank", "score", "max_score", "mistakes"],
                        },
                    },
                    "total_score": {"type": "number"},
                    "total_max_score": {"type": "number"},
                    "overall_feedback": {"type": "string"},
                },
                "required": ["subject", "max_per_question", "questions", "total_score", "total_max_score"],
            },
            "strict": True,
        },
    }

def _grading_json_to_markdown(grading: dict) -> str:
    subject = grading.get("subject", "")
    total = grading.get("total_score", 0)
    total_max = grading.get("total_max_score", 0)
    questions = grading.get("questions", []) or []
    lines = []
    lines.append(f"## 最终总分\n\n**{total} / {total_max}**\n")
    if subject:
        lines.append(f"**科目**：{subject}\n")
    if grading.get("overall_feedback"):
        lines.append("## 总评\n\n" + grading["overall_feedback"].strip() + "\n")
    lines.append("## 逐题评分\n")
    for q in questions:
        qid = q.get("question_id", "?")
        score = q.get("score", 0)
        max_score = q.get("max_score", 10)
        is_blank = q.get("is_blank", False)
        blank_tag = "（空白题：0分）" if is_blank else ""
        lines.append(f"### 题 {qid}\n\n**得分**：{score} / {max_score} {blank_tag}\n")
        mistakes = q.get("mistakes", []) or []
        if mistakes:
            lines.append("**失分点**：\n")
            for m in mistakes:
                summary = (m.get("summary") or "").strip()
                if not summary:
                    continue
                lines.append(f"- **错误**：{summary}")
                if m.get("why_wrong"):
                    lines.append(f"  - **原因**：{m['why_wrong'].strip()}")
                if m.get("correct_idea"):
                    lines.append(f"  - **正确思路**：{m['correct_idea'].strip()}")
            lines.append("")
        if q.get("solution"):
            lines.append("**参考解析/要点**：\n\n" + q["solution"].strip() + "\n")
    return "\n".join(lines).strip() + "\n"

def _build_marking_schema():
    """
    单页错误标注：返回 bbox（像素坐标）+ 标签。
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "page_error_annotations",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "page_num": {"type": "integer"},
                    "annotations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "question_id": {"type": "string"},
                                "label": {"type": "string", "description": "展示在图上的简短错误说明"},
                                "bbox": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "x": {"type": "integer"},
                                        "y": {"type": "integer"},
                                        "w": {"type": "integer"},
                                        "h": {"type": "integer"},
                                    },
                                    "required": ["x", "y", "w", "h"],
                                },
                            },
                            "required": ["label", "bbox"],
                        },
                    },
                },
                "required": ["page_num", "annotations"],
            },
            "strict": True,
        },
    }

def _annotate_image_with_errors(image: Image.Image, annotations: list) -> Image.Image:
    """
    在页面图片上画出错误框（红色）并写 label。
    """
    if image.mode != "RGBA":
        base = image.convert("RGBA")
    else:
        base = image.copy()

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w_img, h_img = base.size

    # 尽量用默认字体（环境未必有中文字体）
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    for ann in annotations or []:
        bbox = ann.get("bbox") or {}
        x = int(bbox.get("x", 0))
        y = int(bbox.get("y", 0))
        w = int(bbox.get("w", 0))
        h = int(bbox.get("h", 0))
        label = (ann.get("label") or "").strip()
        if w <= 0 or h <= 0:
            continue

        # clamp
        x1 = max(0, min(x, w_img - 1))
        y1 = max(0, min(y, h_img - 1))
        x2 = max(0, min(x + w, w_img - 1))
        y2 = max(0, min(y + h, h_img - 1))
        if x2 <= x1 or y2 <= y1:
            continue

        # semi-transparent fill + outline
        draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0, 255), width=4)
        draw.rectangle([x1, y1, x2, y2], fill=(255, 0, 0, 40))

        if label:
            # label background
            pad = 4
            try:
                text_w, text_h = draw.textbbox((0, 0), label, font=font)[2:]
            except Exception:
                text_w, text_h = (len(label) * 7, 14)
            tx1 = x1
            ty1 = max(0, y1 - (text_h + pad * 2))
            tx2 = min(w_img - 1, tx1 + text_w + pad * 2)
            ty2 = min(h_img - 1, ty1 + text_h + pad * 2)
            draw.rectangle([tx1, ty1, tx2, ty2], fill=(255, 0, 0, 220))
            draw.text((tx1 + pad, ty1 + pad), label, fill=(255, 255, 255, 255), font=font)

    merged = Image.alpha_composite(base, overlay)
    return merged.convert("RGB")

def _get_page_error_annotations(page_image: Image.Image, page_num: int, subject: str, grading_json: dict, page_ocr_text: str):
    """
    让模型在该页图上定位所有错误点，返回 bbox 列表。
    """
    base64_image = encode_image(page_image)
    grading_compact = json.dumps(grading_json, ensure_ascii=False)

    prompt = f"""
你是一位{subject}阅卷老师助手。现在需要把“所有错误”标注到该页试卷图片上。

输入信息：
1) 全卷评分结果（JSON）：{grading_compact}
2) 本页 OCR 文字（可能不完整）：{page_ocr_text}
3) 本页试卷图片

任务：
- 找出本页中学生的**所有错误/失分点对应的位置**（包括算式、结论、单位、符号、关键步骤等）。
- 对每个错误返回一个矩形框 bbox（像素坐标，左上角为(0,0)，bbox = x,y,w,h，必须落在图像范围内）。
- label 要简短，便于直接画在图上（例如：\"题2：受力方向错\"、\"题5：单位漏写\"）。
- 如果某题空白（评分里 is_blank=true），且本页对应区域没有作答内容，则不要乱画框。

只输出符合 schema 的 JSON。
"""

    payload = {
        "model": MODEL_NAME,
        "reasoning": {"effort": "high"},
        "response_format": _build_marking_schema(),
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": f"data:image/jpeg;base64,{base64_image}"},
                ],
            }
        ],
    }

    data = _post_responses(payload, timeout=TIMEOUT_MARK_SECONDS)
    text = _extract_text_from_responses(data)
    parsed = _safe_json_loads(text)
    return parsed

@app.route('/analyze', methods=['POST'])
def analyze_pdf():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    subject = request.form.get('subject', '通用')
    
    try:
        print("1. Reading PDF with PyMuPDF...")
        file_stream = file.read()
        doc = fitz.open(stream=file_stream, filetype="pdf")
        
        images = []
        # 【修改点】解除限制，处理所有页面
        total_pages = len(doc)
        print(f"PDF detected with {total_pages} pages. Processing ALL pages...")
        
        for i in range(total_pages):
            page = doc.load_page(i)
            # scale=2.0 保证清晰度
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2)) 
            img_data = pix.tobytes("jpeg")
            img = Image.open(io.BytesIO(img_data))
            images.append(img)

        print(f"Converted {len(images)} pages successfully.")

        # 3. 并发处理每一页
        # 如果 20 页并发太高导致报错，可以将 max_workers 改为 3 或 4
        ocr_results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS_OCR) as executor:
            future_to_page = {executor.submit(process_single_page, img, i+1): i for i, img in enumerate(images)}
            
            results_map = {}
            for future in concurrent.futures.as_completed(future_to_page):
                page_idx = future_to_page[future]
                try:
                    data = future.result()
                    results_map[page_idx] = data
                except Exception as exc:
                    results_map[page_idx] = f"Page {page_idx+1} exception: {exc}"
            
            # 按顺序重组结果
            for i in range(len(images)):
                ocr_results.append(results_map[i])

        full_ocr_text = "\n".join(ocr_results)
        
        # 4. 汇总评分（GPT-5.2 thinking 模式 + JSON 输出）
        print("3. Starting Final Grading (GPT-5.2 thinking)... This may take a while.")
        grading_prompt = f"""
        你是一位{subject}阅卷组长。以下是试卷所有页面的识别内容汇总（共 {total_pages} 页）。
        
        {full_ocr_text}
        
        请根据上下文逻辑，将分散在各页的内容整合，进行最终批改。
        
        **要求：**
        1. **自动拼接**：如果一道大题跨了两页，请自动将其合并分析。
        2. **逐题评分**：请逐题评分（每题默认满分10分，除非题面明确不同；需要给出 max_score）。
        3. **空白题规则**：如果遇到空白的题目（无作答/只写题号/无有效内容），该题 **直接给0分**，并在 is_blank=true。
        4. **错误点**：列出每题所有主要失分点（mistakes），并给出正确思路与参考解析（solution）。
        5. **总分**：输出 total_score / total_max_score。
        
        只输出符合 schema 的 JSON（不要输出 Markdown，不要输出额外文本）。
        """
        
        final_payload = {
            "model": MODEL_NAME,
            "reasoning": {"effort": "high"},
            "response_format": _build_grading_schema(),
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": grading_prompt}]
                }
            ]
        }
        
        final_data = _post_responses(final_payload, timeout=TIMEOUT_GRADE_SECONDS)
        final_text = _extract_text_from_responses(final_data)
        grading_json = _safe_json_loads(final_text)

        # 兜底：强制空白题=0
        for q in grading_json.get("questions", []) or []:
            if q.get("is_blank") is True:
                q["score"] = 0

        grading_markdown = _grading_json_to_markdown(grading_json)

        # 5. 把所有错误标注到每页图片上
        print("4. Marking all errors on extracted images...")
        page_ocr_map = {i + 1: ocr_results[i] for i in range(len(ocr_results))}

        annotated_images = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS_MARK) as executor:
            future_to_page = {
                executor.submit(
                    _get_page_error_annotations,
                    images[i],
                    i + 1,
                    subject,
                    grading_json,
                    page_ocr_map.get(i + 1, ""),
                ): i
                for i in range(len(images))
            }

            annotations_map = {}
            for future in concurrent.futures.as_completed(future_to_page):
                page_idx = future_to_page[future]
                page_num = page_idx + 1
                try:
                    annotations_map[page_num] = future.result()
                except Exception as exc:
                    print(f"Marking error on page {page_num}: {exc}")
                    annotations_map[page_num] = {"page_num": page_num, "annotations": []}

        for i, img in enumerate(images):
            page_num = i + 1
            ann_obj = annotations_map.get(page_num, {"page_num": page_num, "annotations": []})
            anns = ann_obj.get("annotations", []) or []
            marked = _annotate_image_with_errors(img, anns)
            annotated_images.append(
                {
                    "page_num": page_num,
                    "image_base64": encode_image(marked),
                    "annotations": anns,
                }
            )

        print("Done!")
        return jsonify({
            "ocr_text": full_ocr_text,
            "grading_result": grading_markdown,
            "final_score": grading_json.get("total_score", 0),
            "final_max_score": grading_json.get("total_max_score", 0),
            "grading_json": grading_json,
            "annotated_images": annotated_images,
        })

    except Exception as e:
        print(f"Critical Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)