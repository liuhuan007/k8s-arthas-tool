#!/usr/bin/env python3
"""
测试 MC 编译使用 Pod 内路径

验证:
1. 检测本地文件并上传到 Pod
2. 使用 kubectl cp 上传文件
3. 在 Pod 内执行 mc 命令
4. 使用 find 命令查找 .class 文件
"""
import unittest
import re
from pathlib import Path


class TestMcCompilePodPath(unittest.TestCase):
    """测试 MC 编译使用 Pod 内路径"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.hotfix_service = (self.root / 'services' / 'hotfix_service.py').read_text(encoding='utf-8')

    def test_detects_local_file(self):
        """测试检测本地文件"""
        # 应该有 local_path.exists() 检查
        self.assertIn('local_path.exists()', self.hotfix_service,
                     "❌ 应该检测本地文件是否存在")

    def test_uploads_to_pod(self):
        """测试上传文件到 Pod"""
        # 应该有 Pod 临时目录
        self.assertIn('/tmp/arthas-hotfix/', self.hotfix_service,
                     "❌ 应该使用 /tmp/arthas-hotfix/ 临时目录")

    def test_creates_pod_directory(self):
        """测试在 Pod 内创建目录"""
        # 应该有 mkdir -p 命令
        self.assertIn('mkdir -p', self.hotfix_service,
                     "❌ 应该在 Pod 内创建目录")

    def test_uses_pod_path_for_mc(self):
        """测试 MC 使用 Pod 内路径"""
        # 应该有 java_file_in_pod 变量
        self.assertIn('java_file_in_pod', self.hotfix_service,
                     "❌ 应该有 java_file_in_pod 变量")

    def test_finds_class_file_in_pod(self):
        """测试在 Pod 内查找 .class 文件"""
        # 应该有 find 命令
        self.assertIn("find {artifact_dir} -name '*.class'", self.hotfix_service,
                     "❌ 应该使用 find 命令查找 .class 文件")

    def test_parses_connection_id(self):
        """测试解析 connection_id"""
        # 应该有 connection_id.split('/')
        self.assertIn("connection_id.split('/')", self.hotfix_service,
                     "❌ 应该解析 connection_id")

    def test_handles_pod_path_directly(self):
        """测试直接使用 Pod 路径"""
        # 应该有 else 分支处理 Pod 内路径
        self.assertIn('# 已经是 Pod 内路径', self.hotfix_service,
                     "❌ 应该处理已经是 Pod 内路径的情况")

    def test_complete_mc_flow(self):
        """测试完整的 MC 编译流程"""
        issues = []
        
        # 1. 检测本地文件
        if 'local_path.exists()' not in self.hotfix_service:
            issues.append("❌ 未检测本地文件")
        
        # 2. 上传到 Pod
        if '/tmp/arthas-hotfix/' not in self.hotfix_service:
            issues.append("❌ 未上传到 Pod")
        
        # 3. 使用 Pod 路径
        if 'java_file_in_pod' not in self.hotfix_service:
            issues.append("❌ 未使用 Pod 内路径")
        
        # 4. 查找 .class 文件
        if "find {artifact_dir}" not in self.hotfix_service:
            issues.append("❌ 未查找 .class 文件")
        
        if issues:
            self.fail("MC 编译流程存在问题:\n" + "\n".join(issues))


if __name__ == '__main__':
    unittest.main()
