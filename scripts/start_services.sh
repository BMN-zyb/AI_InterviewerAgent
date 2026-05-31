#!/usr/bin/env bash
# 一键启动所有服务（本地开发环境，不使用 docker）
set -e

echo "🚀 启动 InterviewAgent..."

# 检查 Weaviate 是否运行（假设用 weaviate 二进制本地运行）
if ! curl -s http://localhost:8080/v1/.well-known/ready > /dev/null; then
  echo "⚠️  Weaviate 未运行，请启动：weaviate --host 0.0.0.0 --port 8080 --scheme http"
fi

# 检查 Redis
if ! redis-cli ping > /dev/null 2>&1; then
  echo "⚠️  Redis 未运行，请启动：redis-server"
fi

# 检查 MySQL
if ! mysqladmin ping -u root > /dev/null 2>&1; then
  echo "⚠️  MySQL 未运行，请启动：systemctl start mysql"
fi

# 初始化数据库
python scripts/init_db.py

# 构建 RAG 索引（可选，如已构建可注释）
# python scripts/build_index.py

# 启动 FastAPI
echo "🌐 启动 Web 服务..."
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
