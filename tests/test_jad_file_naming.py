#!/usr/bin/env python3
"""
测试 JAD 文件命名使用实际类名

验证:
1. JAD 保存的文件名从类名提取 (如 JacksonRedisSerializer.java)
2. 不再使用固定的 jad.java
"""
import unittest
import re
from pathlib import Path


class TestJadFileNaming(unittest.TestCase):
    """测试 JAD 文件命名"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.hotfix_service_py = (self.root / 'services' / 'hotfix_service.py').read_text(encoding='utf-8')

    def test_jad_uses_simple_class_name(self):
        """测试 JAD 使用简单类名作为文件名"""
        # 应该从类名提取简单类名
        self.assertIn("simple_class_name = class_name.split('.')[-1]", self.hotfix_service_py,
                     "❌ 应该从完整类名提取简单类名")
        
        # 应该使用简单类名作为文件名
        self.assertIn('f"{simple_class_name}.java"', self.hotfix_service_py,
                     "❌ 应该使用简单类名作为文件名")

    def test_jad_not_using_fixed_name(self):
        """测试 JAD 不再使用固定的 jad.java"""
        # 不应该有固定的 "jad.java"
        if 'artifact_dir / "jad.java"' in self.hotfix_service_py:
            self.fail("❌ 仍在使用固定的 jad.java 文件名")

    def test_jad_file_naming_logic(self):
        """测试 JAD 文件命名逻辑"""
        # 应该提取简单类名
        self.assertIn("class_name.split('.')[-1]", self.hotfix_service_py,
                     "❌ 应该使用 split('.')[-1] 提取简单类名")
        
        # 应该使用 f-string 构建文件名
        self.assertIn('f"{simple_class_name}.java"', self.hotfix_service_py,
                     "❌ 应该使用 f-string 构建文件名")

    def test_example_class_name_extraction(self):
        """测试类名提取逻辑 (模拟)"""
        # 模拟类名提取
        test_cases = [
            ("com.seeyon.boot.starter.cache.JacksonRedisSerializer", "JacksonRedisSerializer.java"),
            ("com.example.UserService", "UserService.java"),
            ("org.apache.commons.lang3.StringUtils", "StringUtils.java"),
            ("SimpleClass", "SimpleClass.java"),
        ]
        
        for full_name, expected_file in test_cases:
            simple_name = full_name.split('.')[-1]
            actual_file = f"{simple_name}.java"
            self.assertEqual(actual_file, expected_file,
                           f"❌ 类名 {full_name} 应该提取为 {expected_file}, 实际为 {actual_file}")

    def test_complete_jad_naming_flow(self):
        """测试完整的 JAD 文件命名流程"""
        issues = []
        
        # 1. 应该提取简单类名
        if "simple_class_name = class_name.split('.')[-1]" not in self.hotfix_service_py:
            issues.append("❌ 未提取简单类名")
        
        # 2. 应该使用简单类名作为文件名
        if 'f"{simple_class_name}.java"' not in self.hotfix_service_py:
            issues.append("❌ 未使用简单类名作为文件名")
        
        # 3. 不应该使用固定的 jad.java
        if 'artifact_dir / "jad.java"' in self.hotfix_service_py:
            issues.append("❌ 仍在使用固定的 jad.java")
        
        if issues:
            self.fail("JAD 文件命名流程存在问题:\n" + "\n".join(issues))


if __name__ == '__main__':
    unittest.main()
