#!/bin/bash
# K8s Arthas 智能诊断平台 - 安装Arthas到Pod
#
# 使用方式：
#   ./install-arthas.sh <namespace> <pod-name> [container-name]
#
# 示例：
#   ./install-arthas.sh production my-app-pod-xxx
#   ./install-arthas.sh production my-app-pod-xxx my-container

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 参数检查
if [ $# -lt 2 ]; then
    echo -e "${RED}错误: 参数不足${NC}"
    echo "使用方式: $0 <namespace> <pod-name> [container-name]"
    echo "示例: $0 production my-app-pod-xxx"
    exit 1
fi

NAMESPACE=$1
POD_NAME=$2
CONTAINER_NAME=$3

# 工具目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(dirname "$SCRIPT_DIR")"
ARTHAS_JAR="$TOOLS_DIR/arthas/arthas-boot.jar"

# 检查arthas-boot.jar是否存在
if [ ! -f "$ARTHAS_JAR" ]; then
    echo -e "${YELLOW}arthas-boot.jar不存在，尝试从网络下载...${NC}"
    
    # 创建临时目录
    TMP_DIR=$(mktemp -d)
    trap "rm -rf $TMP_DIR" EXIT
    
    # 下载arthas-boot.jar
    echo -e "${GREEN}正在下载arthas-boot.jar...${NC}"
    if command -v wget &> /dev/null; then
        wget -q -O "$TMP_DIR/arthas-boot.jar" "https://arthas.aliyun.com/arthas-boot.jar"
    elif command -v curl &> /dev/null; then
        curl -sL -o "$TMP_DIR/arthas-boot.jar" "https://arthas.aliyun.com/arthas-boot.jar"
    else
        echo -e "${RED}错误: 无法下载arthas-boot.jar，请手动下载${NC}"
        echo "下载地址: https://arthas.aliyun.com/arthas-boot.jar"
        exit 1
    fi
    
    ARTHAS_JAR="$TMP_DIR/arthas-boot.jar"
fi

# 构建kubectl命令
KUBECTL_CMD="kubectl"
if [ -n "$CONTAINER_NAME" ]; then
    KUBECTL_CMD="kubectl -n $NAMESPACE exec -it $POD_NAME --container $CONTAINER_NAME --"
else
    KUBECTL_CMD="kubectl -n $NAMESPACE exec -it $POD_NAME --"
fi

# 检查Pod是否存在
echo -e "${GREEN}检查Pod状态...${NC}"
if ! kubectl -n $NAMESPACE get pod $POD_NAME &> /dev/null; then
    echo -e "${RED}错误: Pod $POD_NAME 不存在${NC}"
    exit 1
fi

# 检查Pod是否运行中
POD_STATUS=$(kubectl -n $NAMESPACE get pod $POD_NAME -o jsonpath='{.status.phase}')
if [ "$POD_STATUS" != "Running" ]; then
    echo -e "${RED}错误: Pod $POD_NAME 状态不是Running (当前: $POD_STATUS)${NC}"
    exit 1
fi

# 复制arthas-boot.jar到Pod
echo -e "${GREEN}正在复制arthas-boot.jar到Pod...${NC}"
kubectl -n $NAMESPACE cp "$ARTHAS_JAR" "$POD_NAME:/tmp/arthas-boot.jar"

# 检查Java是否可用
echo -e "${GREEN}检查Java环境...${NC}"
if ! $KUBECTL_CMD java -version &> /dev/null; then
    echo -e "${RED}错误: Pod中没有Java环境${NC}"
    exit 1
fi

# 启动Arthas
echo -e "${GREEN}正在启动Arthas...${NC}"
echo -e "${YELLOW}提示: Arthas启动后会在控制台显示，按Ctrl+C退出${NC}"
$KUBECTL_CMD java -jar /tmp/arthas-boot.jar
