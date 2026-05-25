#!/bin/bash
# K8s Arthas 智能诊断平台 - 安装Agent SDK
#
# 使用方式：
#   ./setup-agent-sdk.sh [sdk-type]
#
# 参数：
#   sdk-type: codebuddy (默认) 或 claude
#
# 示例：
#   ./setup-agent-sdk.sh              # 安装CodeBuddy Agent SDK
#   ./setup-agent-sdk.sh codebuddy    # 安装CodeBuddy Agent SDK
#   ./setup-agent-sdk.sh claude       # 安装Claude Agent SDK

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 参数
SDK_TYPE=${1:-codebuddy}

# 工具目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(dirname "$SCRIPT_DIR")"
AGENT_SDK_DIR="$TOOLS_DIR/agent-sdk"

# 检查Python环境
echo -e "${GREEN}检查Python环境...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: Python3未安装${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}Python版本: $PYTHON_VERSION${NC}"

# 检查pip
if ! command -v pip3 &> /dev/null; then
    echo -e "${RED}错误: pip3未安装${NC}"
    exit 1
fi

# 创建虚拟环境
echo -e "${GREEN}创建虚拟环境...${NC}"
VENV_DIR="$AGENT_SDK_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}虚拟环境创建完成: $VENV_DIR${NC}"
fi

# 激活虚拟环境
echo -e "${GREEN}激活虚拟环境...${NC}"
source "$VENV_DIR/bin/activate" || source "$VENV_DIR/Scripts/activate" 2>/dev/null

# 安装SDK
case $SDK_TYPE in
    codebuddy)
        echo -e "${GREEN}安装CodeBuddy Agent SDK...${NC}"
        pip install codebuddy-agent-sdk
        echo -e "${GREEN}CodeBuddy Agent SDK安装完成${NC}"
        ;;
    claude)
        echo -e "${GREEN}安装Claude Agent SDK...${NC}"
        pip install claude-agent-sdk
        echo -e "${GREEN}Claude Agent SDK安装完成${NC}"
        ;;
    *)
        echo -e "${RED}错误: 不支持的SDK类型: $SDK_TYPE${NC}"
        echo "支持的类型: codebuddy, claude"
        exit 1
        ;;
esac

# 验证安装
echo -e "${GREEN}验证安装...${NC}"
case $SDK_TYPE in
    codebuddy)
        python3 -c "from codebuddy_agent_sdk import query; print('CodeBuddy Agent SDK导入成功')"
        ;;
    claude)
        python3 -c "from claude_agent_sdk import query; print('Claude Agent SDK导入成功')"
        ;;
esac

# 创建配置文件模板
echo -e "${GREEN}创建配置文件模板...${NC}"
cat > "$TOOLS_DIR/config/agent-sdk-config.json" << EOF
{
    "sdk_type": "$SDK_TYPE",
    "model": "deepseek-v3.1",
    "permission_mode": "bypassPermissions",
    "api_key": "YOUR_API_KEY_HERE",
    "base_url": "YOUR_BASE_URL_HERE"
}
EOF

echo -e "${GREEN}配置文件已创建: $TOOLS_DIR/config/agent-sdk-config.json${NC}"

# 完成
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Agent SDK安装完成!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}下一步:${NC}"
echo "1. 编辑配置文件: $TOOLS_DIR/config/agent-sdk-config.json"
echo "2. 设置API密钥"
echo "3. 运行诊断测试"
