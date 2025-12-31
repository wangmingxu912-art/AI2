import os
import base64
import io
import requests
import concurrent.futures
from flask import Flask, request, jsonify
from flask_cors import CORS
from PIL import Image
import fitz # PyMuPDF

app = Flask(__name__)
CORS(app)

# 配置
API_KEY = "sk-DBXiFUezyFVsgyfP8heTHjWXiwQRLuf29WOv1CR5VcLo33EM"
API_URL = "https://api.apimart.ai/v1/responses"
MODEL_NAME = "gpt-4o"

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

        # 单页超时 60秒
        response = requests.post(API_URL, json=payload, headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }, timeout=60)
        
        data = response.json()
        
        content = ""
        # 兼容各种 API 返回格式
        if 'output' in data and data['output']:
            content = data['output'][0]['content'][0]['text']
        elif 'choices' in data and data['choices']:
            content = data['choices'][0]['message']['content']
        elif 'data' in data and 'choices' in data['data']:
            content = data['data']['choices'][0]['message']['content']
        else:
            print(f"Page {page_num} API response format unknown: {data}")
            return f"--- 第 {page_num} 页无有效内容 ---\n"
        
        return f"--- 第 {page_num} 页内容 ---\n{content}\n"
    except Exception as e:
        print(f"Error on page {page_num}: {e}")
        return f"--- 第 {page_num} 页识别失败: {str(e)} ---\n"

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
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
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
        
        # 4. 汇总评分
        print("3. Starting Final Grading (Reasoning)... This may take a while.")
        grading_prompt = f"""
        你是一位{subject}阅卷组长。以下是试卷所有页面的识别内容汇总（共 {total_pages} 页）。
        
        {full_ocr_text}
        
        请根据上下文逻辑，将分散在各页的内容整合，进行最终批改。
        
        **要求：**
        1. **自动拼接**：如果一道大题跨了两页，请自动将其合并分析。
        2. **逐题评分**：共有约 9 道大题，请逐一评分（满分10分）。
        3. **深度解析**：详细列出失分点、错误原因和正确解析。
        4. 使用 Markdown 格式输出。
        """
        
        final_payload = {
            "model": MODEL_NAME,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": grading_prompt}]
                }
            ]
        }
        
        # 【修改点】最终汇总的 Token 数很多，超时时间设为 300秒 (5分钟)
        final_res = requests.post(API_URL, json=final_payload, headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }, timeout=300) 
        
        final_data = final_res.json()
        
        final_markdown = "评分生成失败"
        if 'output' in final_data and final_data['output']:
            final_markdown = final_data['output'][0]['content'][0]['text']
        elif 'choices' in final_data and final_data['choices']:
            final_markdown = final_data['choices'][0]['message']['content']
        elif 'data' in final_data and 'choices' in final_data['data']:
            final_markdown = final_data['data']['choices'][0]['message']['content']

        print("Done!")
        return jsonify({
            "ocr_text": full_ocr_text,
            "grading_result": final_markdown
        })

    except Exception as e:
        print(f"Critical Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)