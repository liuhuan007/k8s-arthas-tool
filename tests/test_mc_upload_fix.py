#!/usr/bin/env python3
"""
测试 MC 编译文件上传修复

验证:
1. 不创建 KubectlExecutor (避免 kubeconfig 错误)
2. 使用正确的属性名 pod_conn (而非 pod_connection)
3. 直接从 pod_conn.target 获取 container
"""
import unittest
from pathlib import Path


class TestMcUploadFix(unittest.TestCase):
    """测试 MC 编译文件上传修复"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.hotfix_service = (self.root / 'services' / 'hotfix_service.py').read_text(encoding='utf-8')

    def test_no_kubectl_executor_init(self):
        """测试不创建 KubectlExecutor 实例"""
        # 不应有 executor = KubectlExecutor()
        self.assertNotIn('executor = KubectlExecutor()', self.hotfix_service,
                        "❌ 不应创建 KubectlExecutor 实例")
        
        # 不应有 KubectlExecutor() 调用
        self.assertNotIn('KubectlExecutor()', self.hotfix_service,
                        "❌ 不应调用 KubectlExecutor()")

    def test_uses_correct_attribute_pod_conn(self):
        """测试使用正确的属性名 pod_conn"""
        # 应使用 pod_conn 而非 pod_connection
        self.assertIn('connection.pod_conn', self.hotfix_service,
                     "❌ 应使用 connection.pod_conn")
        
        # 不应使用 pod_connection
        self.assertNotIn('connection.pod_connection', self.hotfix_service,
                        "❌ 不应使用 connection.pod_connection")

    def test_gets_container_from_target(self):
        """测试从 target 获取 container"""
        # 应从 pod_conn.target 获取 container
        self.assertIn('pod_conn.target.container', self.hotfix_service,
                     " 应从 pod_conn.target.container 获取容器名")
        
    def test_looks_up_context_from_clusters_json(self):
        """测试从 clusters.json 查找实际的 kubectl context"""
        # 应读取 clusters.json
        self.assertIn('clusters.json', self.hotfix_service,
                     " 应读取 clusters.json 文件")
            
        # 应使用 cluster.get('context') 获取实际 context
        self.assertIn("cluster.get('context'", self.hotfix_service,
                     " 应使用 cluster.get('context') 获取实际 context")
            
        # 应有日志输出 context 映射
        self.assertIn('找到集群 context', self.hotfix_service,
                     " 应有日志输出 context 映射关系")
            
        # ✅ 应获取 kubeconfig 文件路径
        self.assertIn("cluster.get('kubeconfig'", self.hotfix_service,
                     " 应获取 kubeconfig 文件路径")
            
        # 应使用 --kubeconfig 参数
        self.assertIn("['--kubeconfig', kubeconfig_path]", self.hotfix_service,
                     " 应使用 --kubeconfig 参数")

    def test_direct_kubectl_cp_usage(self):
        """测试直接使用 kubectl cp 命令"""
        # 应有 subprocess.run 直接执行 kubectl cp
        self.assertIn("subprocess.run(", self.hotfix_service,
                     " 应直接使用 subprocess.run 执行 kubectl cp")
            
        # 应有 kubectl cp 命令构建
        self.assertIn("cp_cmd = ['kubectl', 'cp']", self.hotfix_service,
                     " 应构建 kubectl cp 命令")
            
        # 应有 namespace 参数
        self.assertIn("cp_cmd.extend(['-n', namespace])", self.hotfix_service,
                     " 应添加 -n namespace 参数")
            
        # 不应在 Pod 名称中包含 namespace
        self.assertNotIn("namespace}/{pod_name}", self.hotfix_service,
                        " 不应在 Pod 名称中包含 namespace")
        
    def test_uses_utf8_encoding(self):
        """测试使用 UTF-8 编码避免 Windows GBK 错误"""
        # 应指定 encoding='utf-8'
        self.assertIn("encoding='utf-8'", self.hotfix_service,
                     " 应指定 UTF-8 编码避免 Windows GBK 错误")

    def test_no_kubeconfig_error(self):
        """测试不会触发 kubeconfig 错误"""
        # 不应有 KubectlExecutor 初始化 (会导致 kubeconfig 错误)
        if 'KubectlExecutor()' in self.hotfix_service:
            self.fail("❌ 仍在使用 KubectlExecutor(),会导致 kubeconfig 错误")

    def test_complete_upload_flow(self):
        """测试完整的文件上传流程"""
        issues = []
        
        # 1. 不创建 KubectlExecutor
        if 'KubectlExecutor()' in self.hotfix_service:
            issues.append("❌ 创建了 KubectlExecutor 实例")
        
        # 2. 使用正确的属性名
        if 'connection.pod_connection' in self.hotfix_service:
            issues.append("❌ 使用了错误的属性名 pod_connection")
        
        # 3. 从 target 获取 container
        if 'pod_conn.target.container' not in self.hotfix_service:
            issues.append("❌ 未从 pod_conn.target.container 获取容器名")
        
        # 4. 直接使用 subprocess
        if 'subprocess.run(' not in self.hotfix_service:
            issues.append("❌ 未使用 subprocess.run 执行命令")
        
        # 5. 使用 UTF-8 编码
        if "encoding='utf-8'" not in self.hotfix_service:
            issues.append("❌ 未指定 UTF-8 编码,会导致 Windows GBK 错误")
        
        # 6. 从 clusters.json 查找 context
        if 'clusters.json' not in self.hotfix_service:
            issues.append("❌ 未从 clusters.json 查找实际的 kubectl context")
        
        if 'cluster.get' not in self.hotfix_service:
            issues.append("❌ 未使用 cluster.get('context') 获取实际 context")
        
        # 7. 使用 namespace 参数
        if "['-n', namespace]" not in self.hotfix_service:
            issues.append("❌ 未添加 -n namespace 参数")
        
        # 8. 不应在 Pod 名称中包含 namespace
        if 'namespace}/{pod_name}' in self.hotfix_service:
            issues.append("❌ 在 Pod 名称中包含了 namespace (应使用 -n 参数)")
        
        if issues:
            self.fail("文件上传流程存在问题:\n" + "\n".join(issues))


if __name__ == '__main__':
    unittest.main()
