## AI 阅卷系统（GPT‑5.2 thinking 评分 + 错误标注图）

### 功能
- **GPT‑5.2 thinking 模式评分**：逐题给分、列失分点、输出最终总分
- **空白题规则**：遇到空白题直接 **0 分**
- **错误可视化**：把所有错误框画在从 PDF 提取的页面图片上并返回前端展示

### 本地运行（mac）
1) 双击运行 `run_mac.command`（或在终端执行它）  
2) 按提示粘贴 `OPENAI_API_KEY`（不会写入仓库文件）  
3) 浏览器打开的 `index.html` 里上传 PDF 开始批改

### 打包成 mac 可执行文件（不依赖你本机 Python 环境来运行）
> 说明：我在 Linux 云环境里无法直接产出 mac 二进制，但你在 mac 上运行打包脚本即可生成 `dist/AIGrader`。

1) 先在 mac 上打包：
- 运行 `build_mac_pyinstaller.command`

2) 运行打包后的可执行文件：
- 运行 `run_mac_dist.command`

### 生成可双击运行的 mac `.app`（不打开终端）
1) 在 mac 上执行：
- `./build_mac_app.command`

2) 然后双击：
- `dist/AIGrader.app`

应用启动后会：
- 如未设置 `OPENAI_API_KEY`，弹窗输入（不保存到磁盘）
- 自动打开浏览器 `http://127.0.0.1:5000/`

### 不想折腾 Python：用 Docker（mac 上只要装 Docker Desktop）
- 运行 `run_mac_docker.command`

### 环境变量
- **OPENAI_API_KEY**：OpenAI API Key（必填）
- **OPENAI_API_URL**：可选，默认 `https://api.openai.com/v1/responses`
- **OPENAI_MODEL**：可选，默认 `gpt-5.2`