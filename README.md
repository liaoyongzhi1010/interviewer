# 夜莺面试官

基于RAG的智能面试辅助平台，提供简历解析、智能题目生成、面试过程管理和AI评估报告等功能。

## 快速开始

### 本地开发

**环境要求**
- Python 3.11+
- pip

**安装步骤**

```bash
# 1. 克隆项目
git clone <repository-url>
cd interviewer

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填写必需的配置项

# 4. 执行数据库迁移（推荐）
alembic upgrade head

# 5. 启动应用
python -m backend
# 或
uvicorn backend.main:app --host 0.0.0.0 --port 8080 --reload
```

访问地址：`http://localhost:8080`

## 架构说明（FastAPI-first）

- 运行时统一为 FastAPI：`backend/main.py` 负责应用初始化与路由装配。
- `backend/main.py` 提供 FastAPI app factory 与 ASGI app，`backend/__main__.py` 作为本地运行入口。
- API 路由按领域拆分在 `backend/api/routers/`，`backend/api/routes.py` 仅做聚合装配。
- 页面渲染路由集中在 `backend/web/routes.py`。
- 数据模型按领域拆分在 `backend/models/`（`base.py / resume.py / interview.py / bootstrap.py`）。
- 数据库变更采用 Alembic 版本化迁移（`alembic/`），线上发布用 `alembic upgrade head` 管理 schema。
- 鉴权与资源所有权校验放在 `backend/api/deps.py`，避免业务逻辑散落在控制器装饰器中。
- 模板渲染使用 `backend/web/templates.py` 提供的 `url_for` 兼容层，前端模板无需大改即可迁移。

## 测试

```bash
python -m unittest tests/test_fastapi_smoke.py
```

## 配置说明

### 必需配置

在 `.env` 文件中配置以下参数：

```bash
# AI服务配置
QWEN_API_KEY=sk-xxx                    # 通义千问API密钥

# 应用配置
SECRET_KEY=your-random-secret-key      # 应用密钥
JWT_SECRET=your-jwt-secret             # JWT签名密钥（必须配置）

# MinerU配置
MINERU_API_KEY=your-mineru-key        # MinerU API密钥

# MinIO配置（可选）
MINIO_ENDPOINT=localhost:9000          # MinIO服务地址
MINIO_ACCESS_KEY=minioadmin           # MinIO访问密钥
MINIO_SECRET_KEY=minioadmin           # MinIO私钥
MINIO_BUCKET=yeying-interviewer       # 存储桶名称
```

### 可选配置

```bash
# 日志配置
LOG_LEVEL=INFO                        # 日志级别：DEBUG/INFO/WARNING/ERROR

# 调试模式
APP_DEBUG=false                       # 生产环境请设置为false

# 服务端口
APP_PORT=8080                         # 应用监听端口
```
