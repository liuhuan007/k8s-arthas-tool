#!/bin/bash
# K8s Arthas 智能诊断平台 - 启动Tunnel Server
#
# 使用方式：
#   ./start-tunnel-server.sh [port]
#
# 示例：
#   ./start-tunnel-server.sh          # 使用默认端口7777
#   ./start-tunnel-server.sh 8888     # 使用自定义端口

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 参数
PORT=${1:-7777}

# 工具目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(dirname "$SCRIPT_DIR")"
TUNNEL_JAR="$TOOLS_DIR/arthas/arthas-tunnel-server.jar"

# 检查arthas-tunnel-server.jar是否存在
if [ ! -f "$TUNNEL_JAR" ]; then
    echo -e "${RED}错误: arthas-tunnel-server.jar不存在${NC}"
    echo "请从GitHub下载: https://github.com/alibaba/arthas/releases"
    echo "文件名: arthas-tunnel-server-*-fatjar.jar"
    exit 1
fi

# 检查Java是否可用
if ! command -v java &> /dev/null; then
    echo -e "${RED}错误: Java环境不可用${NC}"
    exit 1
fi

# 检查端口是否被占用
if lsof -i :$PORT &> /dev/null; then
    echo -e "${YELLOW}警告: 端口$PORT已被占用${NC}"
    lsof -i :$PORT
    echo -e "${YELLOW}是否继续启动？(y/n)${NC}"
    read -r response
    if [ "$response" != "y" ] && [ "$response" != "Y" ]; then
        echo -e "${RED}已取消启动${NC}"
        exit 1
    fi
fi

# 启动Tunnel Server
echo -e "${GREEN}正在启动Tunnel Server...${NC}"
echo -e "${GREEN}端口: $PORT${NC}"
echo -e "${GREEN}WebSocket: ws://127.0.0.1:$PORT/ws${NC}"
echo -e "${GREEN}Web控制台: http://127.0.0.1:$PORT${NC}"
echo -e "${YELLOW}提示: 按Ctrl+C停止服务${NC}"
echo ""

java -jar "$TUNNEL_JAR" --server.port=$PORT
