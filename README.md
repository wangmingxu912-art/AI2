## AI 阅卷系统（GPT‑5.2 thinking 评分 + 错误标注图）

### 功能
- **GPT‑5.2 thinking 模式评分**：逐题给分、列失分点、输出最终总分
- **空白题规则**：遇到空白题直接 **0 分**
- **错误可视化**：把所有错误框画在从 PDF 提取的页面图片上并返回前端展示

### 本地运行（mac）
1) 双击运行 `run_mac.command`（或在终端执行它）  
2) 按提示粘贴 `OPENAI_API_KEY`（不会写入仓库文件）  
3) 浏览器打开的 `index.html` 里上传 PDF 开始批改

### 环境变量
- **OPENAI_API_KEY**：OpenAI API Key（必填）
- **OPENAI_API_URL**：可选，默认 `https://api.openai.com/v1/responses`
- **OPENAI_MODEL**：可选，默认 `gpt-5.2`