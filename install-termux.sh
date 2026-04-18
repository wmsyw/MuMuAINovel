#!/bin/bash
# MuMuAINovel Termux 一键安装脚本
# 用法: curl -fsSL <url> | bash
# 或者: bash install-termux.sh
set -e

INSTALL_DIR="$HOME/MuMuAINovel"
DATA_DIR="$HOME/mumuainovel/data"
LOG_DIR="$HOME/mumuainovel/logs"
REPO="https://github.com/xiamuceer-j/MuMuAINovel.git"

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
err()   { echo -e "${RED}[✗]${NC} $1"; }
step()  { echo -e "\n${CYAN}[$1/$2]${NC} $3"; }

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   📚 MuMuAINovel Termux 一键安装         ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""

TOTAL=9

# ──────────────────────────────────────────
step 1 $TOTAL "检查环境"
# ──────────────────────────────────────────
if [ ! -d "/data/data/com.termux" ]; then
    err "未检测到 Termux 环境，请在 Termux 中运行"
    exit 1
fi
info "Termux 环境检测通过"

# ──────────────────────────────────────────
step 2 $TOTAL "安装系统依赖"
# ──────────────────────────────────────────
pkg install -y python nodejs git > /dev/null 2>&1
info "python/nodejs/git 已安装"

# ──────────────────────────────────────────
step 3 $TOTAL "克隆项目"
# ──────────────────────────────────────────
if [ -d "$INSTALL_DIR" ]; then
    warn "检测到旧安装，清理中..."
    rm -rf "$INSTALL_DIR"
fi
git clone "$REPO" "$INSTALL_DIR"
info "项目已就位: $INSTALL_DIR"

BACKEND="$INSTALL_DIR/backend"
FRONTEND="$INSTALL_DIR/frontend"
PYTHON="$BACKEND/venv/bin/python"

# ──────────────────────────────────────────
step 4 $TOTAL "应用 Termux 补丁"
# ──────────────────────────────────────────

# 4a. Patch memory_service.py - 让 chromadb/sentence_transformers 缺失不崩溃
MEM_FILE="$BACKEND/app/services/memory_service.py"
python3 << PYEOF
import os
f = os.path.expanduser("~/MuMuAINovel/backend/app/services/memory_service.py")
with open(f) as fh:
    c = fh.read()

# 替换顶层 import
c = c.replace(
    "import chromadb\nfrom sentence_transformers import SentenceTransformer",
    """try:
    import chromadb
    from sentence_transformers import SentenceTransformer
    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False
    chromadb = None
    SentenceTransformer = None"""
)

# 在 __init__ 的 _initialized 检查后加 MEMORY_AVAILABLE 保护
old_init = """    def __init__(self):
        \"\"\"初始化ChromaDB和Embedding模型\"\"\"
        if self._initialized:
            return
            
        try:"""
new_init = """    def __init__(self):
        \"\"\"初始化ChromaDB和Embedding模型\"\"\"
        if self._initialized:
            return

        if not MEMORY_AVAILABLE:
            self.client = None
            self.model = None
            self.collection = None
            self._initialized = True
            logger.warning("⚠️ 向量记忆功能不可用（缺少 chromadb/sentence-transformers）")
            return

        try:"""
c = c.replace(old_init, new_init, 1)

with open(f, "w") as fh:
    fh.write(c)
print("  ✅ memory_service.py 已修补")
PYEOF
info "memory_service.py 已修补"

# 4b. Patch API files - memory_service 导入改为 try/except
python3 << 'PYEOF'
import os
home = os.path.expanduser("~")
files = [
    f"{home}/MuMuAINovel/backend/app/api/chapters.py",
    f"{home}/MuMuAINovel/backend/app/api/memories.py",
    f"{home}/MuMuAINovel/backend/app/api/outlines.py",
    f"{home}/MuMuAINovel/backend/app/api/projects.py",
    f"{home}/MuMuAINovel/backend/app/services/foreshadow_service.py",
]
old = 'from app.services.memory_service import memory_service'
new = 'try:\n    from app.services.memory_service import memory_service\nexcept ImportError:\n    memory_service = None'
count = 0
for f in files:
    if not os.path.exists(f): continue
    with open(f) as fh: c = fh.read()
    if old in c:
        c = c.replace(old, new)
        with open(f, 'w') as fh: fh.write(c)
        count += 1
print(f"  ✅ API 文件已修补（{count} 个）")
PYEOF
info "API 文件已修补"

# 4c. 创建 .env
mkdir -p "$DATA_DIR" "$LOG_DIR"
cat > "$BACKEND/.env" << 'ENVEOF'
# MuMuAINovel Termux 配置
APP_NAME=MuMuAINovel
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=false
TZ=Asia/Shanghai

# SQLite 数据库（替代 PostgreSQL）
DATABASE_URL=sqlite+aiosqlite:///data/data/com.termux/files/home/mumuainovel/data/ai_story.db

# 日志
LOG_LEVEL=INFO
LOG_TO_FILE=true
LOG_FILE_PATH=/data/data/com.termux/files/home/mumuainovel/logs/app.log
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5

# CORS
CORS_ORIGINS=["http://localhost:8000","http://127.0.0.1:8000"]

# ⚠️ 请填入你的 API Key
OPENAI_API_KEY=sk-your-key-here
OPENAI_BASE_URL=https://api.openai.com/v1

DEFAULT_AI_PROVIDER=openai
DEFAULT_MODEL=gpt-4o-mini
DEFAULT_TEMPERATURE=0.7
DEFAULT_MAX_TOKENS=4096

# 本地登录账号
LOCAL_AUTH_USERNAME=admin
LOCAL_AUTH_PASSWORD=admin123
LOCAL_AUTH_DISPLAY_NAME=管理员
ENVEOF

# 修正 DATABASE_URL 路径（替换占位符为实际路径）
sed -i "s|/data/data/com.termux/files/home|$HOME|g" "$BACKEND/.env"
sed -i "s|LOG_FILE_PATH=.*|LOG_FILE_PATH=$LOG_DIR/app.log|" "$BACKEND/.env"
info ".env 已创建（SQLite + admin/admin123）"

# ──────────────────────────────────────────
step 5 $TOTAL "安装 Python 依赖"
# ──────────────────────────────────────────
if [ ! -d "$BACKEND/venv" ]; then
    python -m venv "$BACKEND/venv"
fi
PIP="$BACKEND/venv/bin/pip"

$PIP install --upgrade pip setuptools wheel -q

# 精简依赖（跳过 Termux 不兼容的包）
cat > "$BACKEND/requirements-lite.txt" << 'REQEOF'
fastapi==0.121.0
uvicorn==0.38.0
python-multipart==0.0.20
sqlalchemy==2.0.36
alembic==1.14.0
aiosqlite==0.22.1
pydantic==2.12.4
pydantic-settings==2.11.0
openai==2.7.0
anthropic==0.72.0
httpx==0.28.1
python-dotenv==1.1.0
aiosmtplib==4.0.2
mcp==1.22.0
greenlet>=3.0
REQEOF

$PIP install -r "$BACKEND/requirements-lite.txt" -q
info "Python 依赖已安装"

# ──────────────────────────────────────────
step 6 $TOTAL "数据库迁移"
# ──────────────────────────────────────────
export DATABASE_URL="sqlite+aiosqlite:///$DATA_DIR/ai_story.db"
cd "$BACKEND"
"$BACKEND/venv/bin/python" -m alembic -c alembic-sqlite.ini upgrade head || {
    warn "alembic 迁移失败，尝试修复后重试..."
    "$BACKEND/venv/bin/pip" install --force-reinstall alembic==1.14.0 -q
    "$BACKEND/venv/bin/python" -m alembic -c alembic-sqlite.ini upgrade head || {
        err "数据库迁移失败，请手动运行: cd $BACKEND && python -m alembic -c alembic-sqlite.ini upgrade head"
        exit 1
    }
}
info "SQLite 数据库已初始化"

# ──────────────────────────────────────────
step 7 $TOTAL "安装前端依赖"
# ──────────────────────────────────────────
cd "$FRONTEND"
npm install --include=dev
info "前端依赖已安装"

# ──────────────────────────────────────────
step 8 $TOTAL "构建前端"
# ──────────────────────────────────────────
# Termux 下 npm 的符号链接可能失效，用 node 直接调用
node "$FRONTEND/node_modules/typescript/bin/tsc" -b 2>/dev/null || warn "TypeScript 有类型警告（已跳过）"
node "$FRONTEND/node_modules/vite/bin/vite.js" build || {
    err "前端构建失败"
    exit 1
}
info "前端已构建 → $BACKEND/static/"

# ──────────────────────────────────────────
step 9 $TOTAL "创建启动脚本"
# ──────────────────────────────────────────
cat > "$HOME/mumuainovel-start.sh" << STARTEOF
#!/bin/bash
# MuMuAINovel Termux 启动脚本
set -e

BACKEND="$BACKEND"
PYTHON="\$BACKEND/venv/bin/python"
DATA_DIR="$DATA_DIR"
LOG_DIR="$LOG_DIR"

mkdir -p "\$DATA_DIR" "\$LOG_DIR"
export DATABASE_URL="sqlite+aiosqlite:///\$DATA_DIR/ai_story.db"
cd "\$BACKEND"

if [ "\$1" = "--bg" ]; then
    echo "🚀 后台启动 MuMuAINovel (端口 8000)..."
    nohup "\$PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 \\
        > "\$LOG_DIR/app.log" 2>&1 &
    echo \$! > "$HOME/mumuainovel.pid"
    sleep 2
    if kill -0 \$(cat "$HOME/mumuainovel.pid") 2>/dev/null; then
        echo "✅ 已启动, PID: \$(cat $HOME/mumuainovel.pid)"
    else
        echo "❌ 启动失败，查看日志: \$LOG_DIR/app.log"
        exit 1
    fi
else
    echo "🚀 启动 MuMuAINovel (端口 8000, Ctrl+C 停止)..."
    exec "\$PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
fi
STARTEOF
chmod +x "$HOME/mumuainovel-start.sh"
info "启动脚本已创建: ~/mumuainovel-start.sh"

# ──────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  🎉 MuMuAINovel 安装完成！                   ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║                                              ║${NC}"
echo -e "${GREEN}║  前台运行（Ctrl+C 停止）:                     ║${NC}"
echo -e "${GREEN}║    bash ~/mumuainovel-start.sh                ║${NC}"
echo -e "${GREEN}║                                              ║${NC}"
echo -e "${GREEN}║  后台运行:                                    ║${NC}"
echo -e "${GREEN}║    bash ~/mumuainovel-start.sh --bg           ║${NC}"
echo -e "${GREEN}║                                              ║${NC}"
echo -e "${GREEN}║  停止后台:                                    ║${NC}"
echo -e "${GREEN}║    kill \\\$(cat ~/mumuainovel.pid)             ║${NC}"
echo -e "${GREEN}║                                              ║${NC}"
echo -e "${GREEN}║  查看日志:                                    ║${NC}"
echo -e "${GREEN}║    tail -f ~/mumuainovel/logs/app.log         ║${NC}"
echo -e "${GREEN}║                                              ║${NC}"
echo -e "${GREEN}║  🌐 访问: http://127.0.0.1:8000               ║${NC}"
echo -e "${GREEN}║  🔑 账号: admin / admin123                    ║${NC}"
echo -e "${GREEN}║                                              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}  ⚠️  首次使用前请编辑 API Key:${NC}"
echo -e "     nano $BACKEND/.env"
echo -e "     修改 OPENAI_API_KEY 和 OPENAI_BASE_URL"
echo ""
