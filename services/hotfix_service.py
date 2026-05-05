#!/usr/bin/env python3
"""热更新服务 — jad → 编辑/上传 → mc → redefine → 验证完整链路"""
import hashlib
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from backend.core.arthas_executor import ArthasCommandExecutor

log = logging.getLogger(__name__)


class HotfixService:
    """热更新服务 — 管理 jad/mc/redefine 完整生命周期"""

    # redefine 8 项技术限制
    REDEFINE_LIMITATIONS = [
        {
            "id": "method_signature",
            "title": "方法签名修改",
            "description": "不能增减参数、修改返回值类型",
            "action": "redefine 前检查 class 字节码,拒绝不兼容变更"
        },
        {
            "id": "field_change",
            "title": "字段变更",
            "description": "不能增加、删除或修改字段",
            "action": "检查 class 字段列表,拒绝变更"
        },
        {
            "id": "parent_interface",
            "title": "父类/接口修改",
            "description": "不能修改父类或实现的接口",
            "action": "检查 class 继承关系,拒绝变更"
        },
        {
            "id": "annotation_change",
            "title": "注解修改",
            "description": "不能增加、删除或修改注解",
            "action": "检查 class 注解,拒绝变更"
        },
        {
            "id": "spring_bean",
            "title": "Spring Bean",
            "description": "redefine 不更新 Spring AOP 代理和依赖注入",
            "action": "提示'需重启 Pod 生效'"
        },
        {
            "id": "jdk_version",
            "title": "JDK 版本",
            "description": "JDK 8 支持较好,JDK 17+ 可能受限",
            "action": "连接建立时检测 JDK 版本,展示兼容性提示"
        },
        {
            "id": "custom_classloader",
            "title": "自定义类加载器",
            "description": "某些自定义类加载器可能不支持 redefine",
            "action": "提示'可能失败,请准备回滚方案'"
        },
        {
            "id": "static_init",
            "title": "静态初始化",
            "description": "不能重新执行静态初始化块",
            "action": "提示'静态代码不会重新执行'"
        }
    ]

    def __init__(self, output_base: str = "profiler_output/hotfix"):
        self.output_base = Path(output_base)
        self.output_base.mkdir(parents=True, exist_ok=True)

    def _get_artifact_dir(self, connection_id: str, timestamp: Optional[str] = None) -> Path:
        """获取产物目录: profiler_output/hotfix/{connection_id}/{timestamp}/"""
        if not timestamp:
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        artifact_dir = self.output_base / connection_id / timestamp
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return artifact_dir

    def _calculate_sha256(self, file_path: Path) -> str:
        """计算文件 SHA256"""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

    # ── jad: 查看源码 ───────────────────────────────────────────────────────

    def execute_jad(
        self,
        connection,
        class_name: str,
        connection_id: str,
        user_id: int
    ) -> Dict[str, Any]:
        """一键查看目标类源码

        Args:
            connection: ArthasConnection 实例
            class_name: 完整类名 (如 com.example.UserService)
            connection_id: 连接 ID
            user_id: 用户 ID

        Returns:
            {
                "ok": bool,
                "source_code": str,
                "artifact_path": str,
                "timestamp": str,
                "error": str (可选)
            }
        """
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        artifact_dir = self._get_artifact_dir(connection_id, timestamp)
        
        # ✅ 从完整类名提取简单类名 (如 com.example.UserService -> UserService)
        simple_class_name = class_name.split('.')[-1]
        source_file = artifact_dir / f"{simple_class_name}.java"

        try:
            # 执行 jad 命令
            command = f"jad {class_name}"
            result = ArthasCommandExecutor.execute(connection, command)

            if result.get('state') in ('SUCCEEDED', 'succeeded'):
                # 从 body 中提取源码
                body = result.get('body', {})
                source_code = ''
                
                # Arthas jad 输出可能在 body.results 或 body 字符串中
                if isinstance(body, dict):
                    results = body.get('results', [])
                    if results and len(results) > 0:
                        # 从 results 提取
                        source_code = results[0].get('java_class', '')
                        if not source_code:
                            source_code = results[0].get('source', '')
                elif isinstance(body, str):
                    source_code = body
                
                if not source_code:
                    source_code = result.get('message', '')
                
                # 保存源码文件
                source_file.write_text(source_code, encoding='utf-8')

                log.info("jad success: %s -> %s", class_name, source_file)
                return {
                    "ok": True,
                    "source_code": source_code,
                    "artifact_path": str(source_file),
                    "timestamp": timestamp
                }
            else:
                error_msg = result.get('message', 'jad command failed')
                log.error("jad failed: %s - %s", class_name, error_msg)
                return {
                    "ok": False,
                    "error": error_msg,
                    "timestamp": timestamp
                }

        except Exception as e:
            log.error("jad exception: %s - %s", class_name, str(e))
            return {
                "ok": False,
                "error": str(e),
                "timestamp": timestamp
            }

    # ── upload: 上传文件 ────────────────────────────────────────────────────

    def upload_file(
        self,
        connection_id: str,
        file_content: bytes,
        filename: str,
        user_id: int
    ) -> Dict[str, Any]:
        """上传 .java 或 .class 文件到受控目录

        Args:
            connection_id: 连接 ID
            file_content: 文件内容
            filename: 文件名 (必须为 .java 或 .class)
            user_id: 用户 ID

        Returns:
            {
                "ok": bool,
                "file_path": str,
                "file_type": str,
                "sha256": str,
                "timestamp": str,
                "error": str (可选)
            }
        """
        # 验证文件类型
        if not filename.endswith(('.java', '.class')):
            return {
                "ok": False,
                "error": "Only .java or .class files are allowed"
            }

        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        artifact_dir = self._get_artifact_dir(connection_id, timestamp)
        file_path = artifact_dir / filename

        try:
            # 保存文件
            file_path.write_bytes(file_content)
            sha256 = self._calculate_sha256(file_path)
            file_type = 'java' if filename.endswith('.java') else 'class'

            log.info("upload success: %s -> %s (sha256: %s)", filename, file_path, sha256[:16])
            return {
                "ok": True,
                "file_path": str(file_path),
                "file_type": file_type,
                "sha256": sha256,
                "timestamp": timestamp
            }

        except Exception as e:
            log.error("upload exception: %s - %s", filename, str(e))
            return {
                "ok": False,
                "error": str(e),
                "timestamp": timestamp
            }

    # ── save-edit: 保存在线编辑内容 ─────────────────────────────────────────

    def save_edit_content(
        self,
        connection,
        file_path: str,
        content: str,
        connection_id: str,
        user_id: int
    ) -> Dict[str, Any]:
        """保存在线编辑的 Java 源码到文件

        Args:
            connection: ArthasConnection 实例
            file_path: 目标文件路径
            content: Java 源码内容
            connection_id: 连接 ID
            user_id: 用户 ID

        Returns:
            {
                "ok": bool,
                "file_path": str,
                "file_size": int,
                "sha256": str,
                "error": str (可选)
            }
        """
        try:
            path = Path(file_path)
            
            # 确保文件存在
            if not path.exists():
                return {
                    "ok": False,
                    "error": f"文件不存在: {file_path}"
                }
            
            # 写入内容
            path.write_text(content, encoding='utf-8')
            
            # 计算 SHA256
            sha256 = self._calculate_sha256(path)
            file_size = path.stat().st_size
            
            log.info("save edit success: %s (%d bytes, sha256: %s)", file_path, file_size, sha256[:16])
            
            return {
                "ok": True,
                "file_path": str(path),
                "file_size": file_size,
                "sha256": sha256
            }
            
        except Exception as e:
            log.error("save edit exception: %s - %s", file_path, str(e))
            return {
                "ok": False,
                "error": str(e)
            }

    # ── compile: mc 编译 ────────────────────────────────────────────────────

    def execute_mc(
        self,
        connection,
        java_file_path: str,
        connection_id: str,
        user_id: int
    ) -> Dict[str, Any]:
        """对 .java 执行 Arthas mc 编译

        Args:
            connection: ArthasConnection 实例
            java_file_path: .java 文件路径
            connection_id: 连接 ID
            user_id: 用户 ID

        Returns:
            {
                "ok": bool,
                "class_file_path": str,
                "output": str,
                "timestamp": str,
                "error": str (可选)
            }
        """
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        
        try:
            # ✅ 判断文件是在本地还是 Pod 内
            local_path = Path(java_file_path)
            
            # 如果是本地路径,需要先上传到 Pod
            if local_path.exists():
                log.info("[MC] 检测到本地文件,上传到 Pod: %s", java_file_path)
                
                # ✅ 提前解析连接信息和集群配置 (用于后续的目录创建和文件上传)
                parts = connection_id.split('/')
                if len(parts) < 3:
                    return {
                        "ok": False,
                        "error": f"无效的连接 ID: {connection_id}"
                    }
                
                cluster_name = parts[0]  # 集群显示名称 (如 "性能环境")
                namespace = parts[1]
                pod_name = parts[2]
                container = connection.pod_conn.target.container if connection.pod_conn else ''
                
                # ✅ 从 clusters.json 查找实际的 kubectl context 和 kubeconfig
                import json
                from backend.config import Config
                context_name = cluster_name  # 默认使用集群名称
                kubeconfig_path = None  # kubeconfig 文件路径
                
                try:
                    clusters_file = Path(Config.CLUSTERS_FILE)
                    if clusters_file.exists():
                        with open(clusters_file, 'r', encoding='utf-8') as f:
                            clusters = json.load(f)
                        
                        # 查找匹配的集群
                        for cluster in clusters:
                            if cluster.get('name') == cluster_name:
                                # 使用实际的 context 名称
                                context_name = cluster.get('context', cluster_name)
                                # 获取 kubeconfig 文件路径
                                kubeconfig_path = cluster.get('kubeconfig')
                                log.info("[MC] 找到集群 context: %s -> %s, kubeconfig: %s", 
                                        cluster_name, context_name, kubeconfig_path or '默认')
                                break
                except Exception as e:
                    log.warning("[MC] 读取 clusters.json 失败: %s, 使用默认集群名称", e)
                
                # 生成 Pod 内临时路径
                pod_tmp_dir = f"/tmp/arthas-hotfix/{timestamp}"
                pod_java_file = f"{pod_tmp_dir}/{local_path.name}"
                
                # 1. 在 Pod 内创建目录 (使用 kubectl exec)
                log.info("[MC] 在 Pod 内创建目录: %s", pod_tmp_dir)
                
                # 构建 kubectl exec 命令
                import subprocess
                mkdir_cmd = ['kubectl', 'exec']
                
                # 添加 kubeconfig 和 context
                if kubeconfig_path:
                    mkdir_cmd.extend(['--kubeconfig', kubeconfig_path])
                if context_name and context_name != 'default':
                    mkdir_cmd.extend(['--context', context_name])
                if namespace:
                    mkdir_cmd.extend(['-n', namespace])
                
                # 添加容器参数
                if container:
                    mkdir_cmd.extend(['-c', container])
                
                # 添加 Pod 名称和命令
                mkdir_cmd.extend([pod_name, '--', 'mkdir', '-p', pod_tmp_dir])
                
                log.info("[MC] 执行 mkdir: %s", ' '.join(mkdir_cmd))
                mkdir_result = subprocess.run(
                    mkdir_cmd,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    timeout=10
                )
                
                if mkdir_result.returncode != 0:
                    log.error("[MC] 创建目录失败: %s", mkdir_result.stderr)
                    return {
                        "ok": False,
                        "error": f"在 Pod 内创建目录失败: {mkdir_result.stderr}"
                    }
                
                log.info("[MC] 目录创建成功: %s", pod_tmp_dir)
                
                # 2. 上传文件到 Pod (直接使用 kubectl cp 命令)
                # 执行 kubectl cp
                import subprocess
                cp_cmd = ['kubectl', 'cp']
                
                # ✅ 添加 kubeconfig 参数 (必须! context 在这个文件中定义)
                if kubeconfig_path:
                    cp_cmd.extend(['--kubeconfig', kubeconfig_path])
                
                # 添加 context 参数
                if context_name and context_name != 'default':
                    cp_cmd.extend(['--context', context_name])
                
                # ✅ 添加 namespace 参数
                if namespace:
                    cp_cmd.extend(['-n', namespace])
                
                # 源文件 -> 目标Pod:目标路径
                cp_cmd.extend([
                    java_file_path,
                    f"{pod_name}:{pod_java_file}"  # ✅ 不再包含 namespace
                ])
                
                # 容器参数
                if container:
                    cp_cmd.extend(['-c', container])
                
                log.info("[MC] 上传文件到 Pod: %s", ' '.join(cp_cmd))
                # ✅ 修复: 使用 encoding='utf-8' 避免 Windows GBK 编码错误
                result = subprocess.run(
                    cp_cmd,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',  # ✅ 明确指定 UTF-8 编码
                    timeout=30
                )
                
                if result.returncode != 0:
                    log.error("[MC] 上传失败: %s", result.stderr)
                    return {
                        "ok": False,
                        "error": f"上传文件到 Pod 失败: {result.stderr}"
                    }
                
                log.info("[MC] 文件上传成功: %s", pod_java_file)
                
                # 使用 Pod 内路径
                artifact_dir = pod_tmp_dir
                java_file_in_pod = pod_java_file
            else:
                # 已经是 Pod 内路径
                log.info("[MC] 使用 Pod 内路径: %s", java_file_path)
                artifact_dir = str(Path(java_file_path).parent)
                java_file_in_pod = java_file_path
            
            # ✅ 在 Pod 内执行 mc 命令
            # ✅ 关键: 需要指定 ClassLoader,否则无法找到依赖的类
            # 1. 获取应用的 ClassLoader hash (使用 classloader 命令)
            log.info("[MC] 获取 ClassLoader hash...")
            
            # 策略 A: 先尝试查找目标类的 ClassLoader
            class_name = local_path.stem  # 例如: JacksonRedisSerializer
            sc_cmd = f"sc -d *{class_name} 2>/dev/null | grep 'classLoaderHash' | head -1 | awk '{{print $2}}'"
            sc_result = ArthasCommandExecutor.execute(connection, sc_cmd, timeout_ms=10000)
            
            class_loader_hash = ""
            if sc_result.get('state') in ('SUCCEEDED', 'succeeded'):
                sc_output = sc_result.get('message', '')
                import re
                match = re.search(r'([0-9a-f]{8,16})', sc_output)
                if match:
                    class_loader_hash = match.group(1)
                    log.info("[MC] 从目标类找到 ClassLoader hash: %s", class_loader_hash)
            
            # 策略 B: 如果找不到,尝试多种 Spring Boot ClassLoader
            if not class_loader_hash:
                log.info("[MC] 目标类未加载,尝试查找应用 ClassLoader")
                
                # 尝试多种可能的 ClassLoader 名称
                classloader_names = [
                    'LaunchedURLClassLoader',  # Spring Boot 2.x
                    'RestartClassLoader',      # Spring Boot DevTools
                    'TomcatEmbeddedWebappClassLoader',  # Tomcat
                    'ParallelWebappClassLoader',  # 其他容器
                ]
                
                for cl_name in classloader_names:
                    cl_cmd = f"classloader | grep '{cl_name}' | head -1 | awk '{{print $1}}'"
                    cl_result = ArthasCommandExecutor.execute(connection, cl_cmd, timeout_ms=10000)
                    
                    if cl_result.get('state') in ('SUCCEEDED', 'succeeded'):
                        cl_output = cl_result.get('message', '').strip()
                        if cl_output:
                            first_line = cl_output.split('\n')[0].strip()
                            match = re.search(r'^([0-9a-fA-F]+)', first_line)
                            if match:
                                class_loader_hash = match.group(1)
                                log.info("[MC] 使用 %s hash: %s", cl_name, class_loader_hash)
                                break
                            else:
                                log.info("[MC] classloader 输出: %s", first_line)
            
            # 策略 C: 直接获取所有 ClassLoader,使用第一个非系统 ClassLoader
            if not class_loader_hash:
                log.info("[MC] 尝试获取所有 ClassLoader 列表")
                all_cl_cmd = "classloader | head -20"
                all_cl_result = ArthasCommandExecutor.execute(connection, all_cl_cmd, timeout_ms=10000)
                
                if all_cl_result.get('state') in ('SUCCEEDED', 'succeeded'):
                    all_cl_output = all_cl_result.get('message', '')
                    log.info("[MC] 所有 ClassLoader:\n%s", all_cl_output[:500])
                    
                    # 提取所有 hash,跳过系统 ClassLoader
                    lines = all_cl_output.strip().split('\n')
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        # 跳过系统 ClassLoader
                        if any(skip in line for skip in ['BootstrapClassLoader', 'sun.misc.Launcher', 'jdk.internal']):
                            continue
                        
                        # 提取 hash
                        match = re.search(r'^([0-9a-fA-F]+)', line)
                        if match:
                            class_loader_hash = match.group(1)
                            log.info("[MC] 使用应用 ClassLoader: %s (%s)", class_loader_hash, line)
                            break
            
            # 策略 D: 从 Spring Boot 主类提取 ClassLoader
            if not class_loader_hash:
                log.info("[MC] 尝试从 Spring Boot 主类提取 ClassLoader")
                # 常见 Spring Boot 主类
                main_classes = [
                    'org.springframework.boot.SpringApplication',
                    'com.seeyon.boot.Application',  # 致远特定
                    'org.springframework.boot.loader.Launcher',
                ]
                
                for main_class in main_classes:
                    sc_main_cmd = f"sc -d {main_class} 2>/dev/null | grep 'classLoaderHash' | head -1 | awk '{{print $2}}'"
                    sc_main_result = ArthasCommandExecutor.execute(connection, sc_main_cmd, timeout_ms=10000)
                    
                    if sc_main_result.get('state') in ('SUCCEEDED', 'succeeded'):
                        sc_main_output = sc_main_result.get('message', '')
                        match = re.search(r'([0-9a-fA-F]{8,16})', sc_main_output)
                        if match:
                            class_loader_hash = match.group(1)
                            log.info("[MC] 从 %s 找到 ClassLoader: %s", main_class, class_loader_hash)
                            break
            
            # 策略 E: 最后兜底
            if not class_loader_hash:
                log.warning("[MC] 未找到应用 ClassLoader,使用默认 (可能缺少依赖)")
                log.warning("[MC] 建议: 在 Pod 内执行 'classloader' 命令手动查找 hash")
            
            # 2. 构建 MC 命令 (如果有 ClassLoader hash,使用 -c 参数)
            # ✅ 关键修复: 验证文件是否存在于 Pod 中
            log.info("[MC] 验证文件是否存在: %s", java_file_in_pod)
            check_cmd = f"test -f {java_file_in_pod} && echo EXISTS || echo NOT_FOUND"
            check_result = ArthasCommandExecutor.execute(connection, check_cmd, timeout_ms=5000)
            log.info("[MC] 文件检查: %s", check_result.get('message', ''))
            
            if class_loader_hash:
                command = f"mc -c {class_loader_hash} -d {artifact_dir} {java_file_in_pod}"
            else:
                command = f"mc -d {artifact_dir} {java_file_in_pod}"
            
            log.info("[MC] 执行命令: %s", command)
            
            result = ArthasCommandExecutor.execute(connection, command, timeout_ms=60000)
            
            log.info("[MC] 响应: state=%s, message=%s", result.get('state'), result.get('message', '')[:200])
            # ✅ 输出完整的 body 结构,帮助诊断
            body = result.get('body', {})
            log.info("[MC] body 类型: %s, keys: %s", type(body).__name__, list(body.keys()) if isinstance(body, dict) else 'N/A')
            if isinstance(body, dict):
                results = body.get('results', [])
                if results:
                    log.info("[MC] results[0] keys: %s", list(results[0].keys()) if isinstance(results[0], dict) else 'N/A')
                    log.info("[MC] results[0] 内容: %s", str(results[0])[:500])
                else:
                    log.warning("[MC] body.results 为空!")

            if result.get('state') in ('SUCCEEDED', 'succeeded'):
                output = result.get('message', '')
                
                # 从 body.results 提取详细输出 (body 已在上面定义)
                if isinstance(body, dict):
                    results = body.get('results', [])
                    if results:
                        # ✅ 修复: 从 results[0].message 提取错误信息
                        result_msg = results[0].get('message', '')
                        if result_msg and ('error' in result_msg.lower() or 'Error' in result_msg):
                            # 编译错误,提取详细错误信息
                            output = result_msg
                            log.warning("[MC] 编译错误: %s", result_msg[:500])
                        else:
                            # 成功,提取 java_class 或 source
                            output = results[0].get('java_class', '') or results[0].get('source', '') or output
                
                # ✅ 在 Pod 内查找生成的 .class 文件 (使用 kubectl exec)
                log.info("[MC] 查找 .class 文件: %s", artifact_dir)
                find_cmd_list = ['kubectl', 'exec']
                
                if kubeconfig_path:
                    find_cmd_list.extend(['--kubeconfig', kubeconfig_path])
                if context_name and context_name != 'default':
                    find_cmd_list.extend(['--context', context_name])
                if namespace:
                    find_cmd_list.extend(['-n', namespace])
                if container:
                    find_cmd_list.extend(['-c', container])
                
                find_cmd_list.extend([
                    pod_name, '--',
                    'find', artifact_dir, '-name', '*.class', '-type', 'f'
                ])
                
                log.info("[MC] 执行 find: %s", ' '.join(find_cmd_list))
                find_result = subprocess.run(
                    find_cmd_list,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    timeout=10
                )
                
                class_file_path = ""
                if find_result.returncode == 0 and find_result.stdout.strip():
                    class_file_path = find_result.stdout.strip().split('\n')[0]
                    log.info("[MC] 找到 .class 文件: %s", class_file_path)
                else:
                    log.warning("[MC] 未找到 .class 文件, stdout: %s, stderr: %s", 
                               find_result.stdout.strip(), find_result.stderr.strip())
                    # 返回详细的 MC 输出,帮助用户诊断
                    if output:
                        log.warning("[MC] 编译输出: %s", output[:500])
                    
                    # ✅ 检查目录内容,帮助诊断
                    try:
                        ls_cmd = ['kubectl', 'exec']
                        if kubeconfig_path:
                            ls_cmd.extend(['--kubeconfig', kubeconfig_path])
                        if context_name and context_name != 'default':
                            ls_cmd.extend(['--context', context_name])
                        if namespace:
                            ls_cmd.extend(['-n', namespace])
                        if container:
                            ls_cmd.extend(['-c', container])
                        ls_cmd.extend([pod_name, '--', 'ls', '-la', artifact_dir])
                        
                        ls_result = subprocess.run(
                            ls_cmd, capture_output=True, text=True, encoding='utf-8', timeout=10
                        )
                        log.warning("[MC] 目录内容: %s", ls_result.stdout.strip()[:500])
                    except Exception as e:
                        log.warning("[MC] 无法列出目录内容: %s", e)
                
                log.info("mc success: %s -> %s", java_file_path, class_file_path)
                
                # ✅ 如果没有找到 .class 文件,返回错误而不是成功
                if not class_file_path:
                    error_msg = "MC 编译失败,未生成 .class 文件\n\n"
                    
                    # 提取编译错误信息
                    if output and ('error' in output.lower() or 'Error' in output):
                        error_msg += "**编译错误:**\n"
                        # 提取前 5 行错误信息
                        error_lines = output.split('\n')[:10]
                        error_msg += '\n'.join(error_lines) + '\n\n'
                    
                    error_msg += "**可能原因:**\n"
                    error_msg += "1. 源码有语法错误\n"
                    error_msg += "2. 缺少依赖类 (需要使用 -classpath 指定依赖 JAR)\n"
                    error_msg += "3. 文件路径不正确\n\n"
                    
                    error_msg += "**解决方案:**\n"
                    error_msg += "• 检查源码语法是否正确\n"
                    error_msg += "• 确保所有依赖的类都在 classpath 中\n"
                    error_msg += "• 或先编译整个项目,再使用 redefine 命令\n"
                    
                    if output:
                        error_msg += f"\n**完整输出:**\n{output[:1000]}"
                    
                    log.error("[MC] %s", error_msg)
                    return {
                        "ok": False,
                        "error": error_msg,
                        "timestamp": timestamp
                    }
                
                return {
                    "ok": True,
                    "class_file": class_file_path,
                    "class_file_path": class_file_path,
                    "output": output,
                    "timestamp": timestamp
                }
            else:
                error_msg = result.get('message', 'mc command failed')
                log.error("mc failed: %s - %s", java_file_path, error_msg)
                return {
                    "ok": False,
                    "error": error_msg,
                    "timestamp": timestamp
                }

        except Exception as e:
            log.error("mc exception: %s - %s", java_file_path, str(e))
            return {
                "ok": False,
                "error": str(e),
                "timestamp": timestamp
            }

    # ── redefine: 热更新 ────────────────────────────────────────────────────

    def execute_redefine(
        self,
        connection,
        class_file_path: str,
        connection_id: str,
        user_id: int
    ) -> Dict[str, Any]:
        """对 .class 执行 Arthas redefine

        Args:
            connection: ArthasConnection 实例
            class_file_path: .class 文件路径
            connection_id: 连接 ID
            user_id: 用户 ID

        Returns:
            {
                "ok": bool,
                "output": str,
                "sha256": str,
                "timestamp": str,
                "error": str (可选)
            }
        """
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')

        try:
            # 计算 class SHA256
            sha256 = self._calculate_sha256(Path(class_file_path))

            # 执行 redefine 命令
            command = f"redefine {class_file_path}"
            result = ArthasCommandExecutor.execute(connection, command)

            if result.get('state') in ('SUCCEEDED', 'succeeded'):
                output = result.get('message', '')
                log.info("redefine success: %s (sha256: %s)", class_file_path, sha256[:16])
                return {
                    "ok": True,
                    "output": output,
                    "sha256": sha256,
                    "timestamp": timestamp
                }
            else:
                error_msg = result.get('error', 'redefine command failed')
                log.error("redefine failed: %s - %s", class_file_path, error_msg)
                return {
                    "ok": False,
                    "error": error_msg,
                    "sha256": sha256,
                    "timestamp": timestamp
                }

        except Exception as e:
            log.error("redefine exception: %s - %s", class_file_path, str(e))
            return {
                "ok": False,
                "error": str(e),
                "timestamp": timestamp
            }

    # ── artifacts: 查询产物 ─────────────────────────────────────────────────

    def list_artifacts(
        self,
        connection_id: str,
        limit: int = 20
    ) -> Dict[str, Any]:
        """查看当前连接最近的源码、class、编译输出和 redefine 输出文件

        Args:
            connection_id: 连接 ID
            limit: 返回数量限制

        Returns:
            {
                "ok": bool,
                "artifacts": [
                    {
                        "timestamp": str,
                        "dir_path": str,
                        "files": [
                            {"name": str, "size": int, "type": str}
                        ]
                    }
                ]
            }
        """
        connection_dir = self.output_base / connection_id

        if not connection_dir.exists():
            return {
                "ok": True,
                "artifacts": []
            }

        artifacts = []
        # 按时间倒序排列
        timestamp_dirs = sorted(
            [d for d in connection_dir.iterdir() if d.is_dir()],
            key=lambda x: x.name,
            reverse=True
        )[:limit]

        for ts_dir in timestamp_dirs:
            files = []
            for f in ts_dir.iterdir():
                if f.is_file():
                    file_type = 'java' if f.suffix == '.java' else \
                               'class' if f.suffix == '.class' else \
                               'report' if f.suffix == '.md' else 'other'
                    files.append({
                        "name": f.name,
                        "size": f.stat().st_size,
                        "type": file_type
                    })

            artifacts.append({
                "timestamp": ts_dir.name,
                "dir_path": str(ts_dir),
                "files": files
            })

        return {
            "ok": True,
            "artifacts": artifacts
        }

    # ── verification: 生成验证报告 ──────────────────────────────────────────

    def generate_verification_report(
        self,
        connection_id: str,
        timestamp: str,
        class_name: str,
        old_source: str,
        new_source: str,
        redefine_output: str
    ) -> Dict[str, Any]:
        """生成验证报告 Markdown

        Args:
            connection_id: 连接 ID
            timestamp: 时间戳
            class_name: 类名
            old_source: 修改前源码
            new_source: 修改后源码
            redefine_output: redefine 输出

        Returns:
            {
                "ok": bool,
                "report_path": str,
                "report_content": str
            }
        """
        artifact_dir = self._get_artifact_dir(connection_id, timestamp)
        report_file = artifact_dir / "verification-report.md"

        try:
            # 生成 Markdown 报告
            report_content = f"""# 热更新验证报告

## 基本信息
- **类名**: {class_name}
- **时间**: {timestamp}
- **连接 ID**: {connection_id}

## redefine 结果
```
{redefine_output}
```

## 修改对比
### 修改前
```java
{old_source[:500]}...
```

### 修改后
```java
{new_source[:500]}...
```

## 验证步骤
- [ ] 执行 `jad {class_name}` 确认源码已更新
- [ ] 执行 `trace {class_name}` 验证方法调用链
- [ ] 执行 `watch {class_name}` 验证输入输出
- [ ] 执行业务验证命令

## 回滚指引
如需回滚:
1. 上传旧版本 `.class` 文件
2. 执行 `redefine <old_class_file>`
3. 重新验证功能

## redefine 技术限制
以下修改**不支持** redefine:
- 方法签名修改(增减参数、修改返回值)
- 字段变更(增加、删除、修改)
- 父类/接口修改
- 注解修改
- Spring Bean(AOP 代理不会更新)
- JDK 版本差异(JDK 17+ 可能受限)
- 自定义类加载器(可能不支持)
- 静态初始化(不会重新执行)
"""

            report_file.write_text(report_content, encoding='utf-8')
            log.info("verification report generated: %s", report_file)

            return {
                "ok": True,
                "report_path": str(report_file),
                "report_content": report_content
            }

        except Exception as e:
            log.error("generate report exception: %s", str(e))
            return {
                "ok": False,
                "error": str(e)
            }

    # ── 工具方法 ────────────────────────────────────────────────────────────

    def get_redefine_limitations(self) -> list:
        """获取 redefine 8 项技术限制"""
        return self.REDEFINE_LIMITATIONS
