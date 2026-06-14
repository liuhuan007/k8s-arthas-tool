"""
脚本执行引擎 — 支持 Shell/Python/Binary，支持 Node/Pod/Pods/NS 目标
"""
import subprocess
import logging
import os
import tempfile
from typing import Tuple, Optional
from pathlib import Path

log = logging.getLogger(__name__)


class ScriptExecutor:
    """执行脚本，支持多种运行时和目标类型"""

    def execute(self, script_content: str, runtime: str, target_type: str,
                target_config: dict, timeout: int = 300,
                env_vars: dict = None) -> Tuple[int, str, str]:
        """
        执行脚本，返回 (exit_code, stdout, stderr)
        """
        if target_type == 'node':
            return self._execute_on_node(script_content, runtime, timeout, env_vars)
        elif target_type in ('pod', 'pods', 'namespace'):
            return self._execute_in_pod(script_content, runtime, target_type, target_config, timeout, env_vars)
        else:
            return -1, '', f'不支持的 target_type: {target_type}'

    def _execute_on_node(self, script_content: str, runtime: str,
                         timeout: int, env_vars: dict = None) -> Tuple[int, str, str]:
        """在服务器本机执行脚本"""
        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)

        with tempfile.NamedTemporaryFile(mode='w', suffix=self._get_suffix(runtime),
                                         delete=False, encoding='utf-8') as f:
            f.write(script_content)
            tmp_path = f.name

        try:
            if runtime == 'shell':
                cmd = ['bash', tmp_path]
            elif runtime == 'python':
                cmd = ['python3', tmp_path]
            else:
                cmd = [tmp_path]

            log.info("Executing on node: %s", " ".join(cmd))
            r = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env)
            stdout = r.stdout.decode('utf-8', errors='replace') if r.stdout else ''
            stderr = r.stderr.decode('utf-8', errors='replace') if r.stderr else ''
            return r.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            return -1, '', f'执行超时 ({timeout}s)'
        except FileNotFoundError:
            return -1, '', f'运行时 {runtime} 未找到'
        except Exception as e:
            return -1, '', str(e)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _execute_in_pod(self, script_content: str, runtime: str, target_type: str,
                        target_config: dict, timeout: int,
                        env_vars: dict = None) -> Tuple[int, str, str]:
        """在 K8s Pod 中执行脚本"""
        namespace = target_config.get('namespace', 'default')
        pod_name = target_config.get('pod_name', '')
        kubeconfig = target_config.get('kubeconfig', '')
        context = target_config.get('context', '')

        if not pod_name:
            return -1, '', '未指定 Pod 名称'

        # 构建 kubectl exec 命令
        cmd = ['kubectl', '-n', namespace, 'exec', pod_name, '--']

        if runtime == 'shell':
            cmd.extend(['bash', '-c', script_content])
        elif runtime == 'python':
            cmd.extend(['python3', '-c', script_content])
        else:
            cmd.extend(['sh', '-c', script_content])

        if kubeconfig:
            cmd.insert(1, '--kubeconfig')
            cmd.insert(2, kubeconfig)
        if context:
            cmd.insert(1, '--context')
            cmd.insert(2, context)

        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)

        try:
            log.info("Executing in pod %s/%s: %s", namespace, pod_name, " ".join(cmd[:6]))
            r = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env)
            stdout = r.stdout.decode('utf-8', errors='replace') if r.stdout else ''
            stderr = r.stderr.decode('utf-8', errors='replace') if r.stderr else ''
            return r.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            return -1, '', f'Pod 执行超时 ({timeout}s)'
        except FileNotFoundError:
            return -1, '', 'kubectl 未找到'
        except Exception as e:
            return -1, '', str(e)

    def _get_suffix(self, runtime: str) -> str:
        return {'.sh', '.py', '.bin'}.get(runtime, '.sh') if runtime in ('shell', 'python', 'binary') else '.sh'
