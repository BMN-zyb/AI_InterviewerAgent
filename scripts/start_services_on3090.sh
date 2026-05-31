

#!/usr/bin/env bash

# 一键启动所有服务（本地开发环境，不使用 docker）
set -e  # 遇到错误时退出

# python --version
# conda deactivate
# conda deactivate

source venv/bin/activate
python --version

echo "🚀 启动 InterviewAgent..."

# 检查 Weaviate 是否运行（假设用 weaviate 二进制本地运行）
if ! curl -s http://localhost:8080/v1/.well-known/ready > /dev/null; then
  echo "⚠️  Weaviate 未运行，请启动：/opt/weaviate/weaviate --host 0.0.0.0 --port 8080 --scheme http"
fi

# 检查 Redis
if ! redis-cli ping > /dev/null 2>&1; then
  echo "⚠️  Redis 未运行，请启动：sudo systemctl start redis"
fi

# 检查 MySQL
if ! mysqladmin ping -u root > /dev/null 2>&1; then
  echo "⚠️  MySQL 未运行，请启动：sudo systemctl start mysql"
fi

# 初始化数据库
# python scripts/init_db.py  # 如果数据库已初始化，再次运行会提示已存在表，可以安全忽略

# 构建 RAG 索引（可选，如已构建可注释）
# python scripts/build_index.py

# 启动 FastAPI
echo "🌐 启动 Web 服务..."
# python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
# python -m cli.main serve --host 0.0.0.0 --port 8000

python -m cli.main interview --jd "岗位职责:
1、基于大模型技术 (如Qwen、DeepSeek、GPT、Kimi等)，主导Agent、 RAG (RetrievalAugmented Generation) 及知识库系统的架构设计与开发，构建包含Planning、Memory、Tool Use、Reflection等能力的Agent系统，推动Al产品在复杂业
务场景中的高效落地2、负责大模型Agent的全流程工作，包括但不限于数据处理、模型训练/微调(SFTLoRA等)、效果评估(oftine/online evaI)、优化和部署，形成数据闭环持续迭代能力
3、集成和部署A模型服务APl，设计高并发、低延迟的推理服务架构(如基于vLLM等推理引擎)，确保系统的高性能、高可用性和可扩展性
4、持续关注LLM及Agent方向的最新进展(如Multi-Agent、Tool Calling、复杂工作流编排等)，结合业务场景提出优化方案并推动落地" --resume ./resume.pdf --total 1
