#!/usr/bin/env python3
"""
统一异常处理模块

功能:
- 全局异常拦截器
- 异常分类和错误码定义
- 标准化错误响应格式
- 异常日志记录
"""

import logging
from functools import wraps
from flask import jsonify, request

log = logging.getLogger(__name__)


# ── 错误码定义 ──────────────────────────────────────────────────────────────

class ErrorCode:
    """错误码枚举"""
    
    # 通用错误 (1xxx)
    SUCCESS = 0
    UNKNOWN_ERROR = 1000
    INVALID_REQUEST = 1001
    METHOD_NOT_ALLOWED = 1002
    NOT_FOUND = 1003
    
    # 认证错误 (2xxx)
    AUTH_REQUIRED = 2000
    AUTH_FAILED = 2001
    TOKEN_EXPIRED = 2002
    PERMISSION_DENIED = 2003
    
    # 连接错误 (3xxx)
    CONNECTION_FAILED = 3000
    POD_NOT_FOUND = 3001
    ARTHAS_NOT_READY = 3002
    PORT_FORWARD_FAILED = 3003
    CONNECTION_TIMEOUT = 3004
    
    # 执行错误 (4xxx)
    COMMAND_FAILED = 4000
    COMMAND_TIMEOUT = 4001
    EXEC_FAILED = 4002
    
    # 资源错误 (5xxx)
    FILE_NOT_FOUND = 5000
    FILE_UPLOAD_FAILED = 5001
    DISK_FULL = 5002
    
    # 业务错误 (6xxx)
    INVALID_PARAMS = 6000
    RESOURCE_BUSY = 6001
    OPERATION_NOT_ALLOWED = 6002


# ── 异常类定义 ──────────────────────────────────────────────────────────────

class AppException(Exception):
    """应用基础异常"""
    
    def __init__(self, message, error_code=ErrorCode.UNKNOWN_ERROR, status_code=500, details=None):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details
        super().__init__(self.message)


class AuthException(AppException):
    """认证异常"""
    
    def __init__(self, message, error_code=ErrorCode.AUTH_FAILED, status_code=401, details=None):
        super().__init__(message, error_code, status_code, details)


class PermissionException(AppException):
    """权限异常"""
    
    def __init__(self, message, error_code=ErrorCode.PERMISSION_DENIED, status_code=403, details=None):
        super().__init__(message, error_code, status_code, details)


class NotFoundException(AppException):
    """资源未找到异常"""
    
    def __init__(self, message, error_code=ErrorCode.NOT_FOUND, status_code=404, details=None):
        super().__init__(message, error_code, status_code, details)


class BadRequestException(AppException):
    """请求参数错误异常"""
    
    def __init__(self, message, error_code=ErrorCode.INVALID_PARAMS, status_code=400, details=None):
        super().__init__(message, error_code, status_code, details)


class ConnectionException(AppException):
    """连接异常"""
    
    def __init__(self, message, error_code=ErrorCode.CONNECTION_FAILED, status_code=503, details=None):
        super().__init__(message, error_code, status_code, details)


class TimeoutException(AppException):
    """超时异常"""
    
    def __init__(self, message, error_code=ErrorCode.CONNECTION_TIMEOUT, status_code=504, details=None):
        super().__init__(message, error_code, status_code, details)


# ── 错误响应格式化 ─────────────────────────────────────────────────────────

def format_error_response(exception, include_stack_trace=False):
    """
    格式化错误响应
    
    Args:
        exception: 异常对象
        include_stack_trace: 是否包含堆栈跟踪 (仅开发环境)
    
    Returns:
        dict: 标准化错误响应
    """
    response = {
        'ok': False,
        'error_code': getattr(exception, 'error_code', ErrorCode.UNKNOWN_ERROR),
        'message': str(exception),
        'path': request.path,
        'method': request.method,
    }
    
    # 添加详细信息
    if hasattr(exception, 'details') and exception.details:
        response['details'] = exception.details
    
    # 开发环境添加堆栈跟踪
    if include_stack_trace:
        import traceback
        response['stack_trace'] = traceback.format_exc()
    
    return response


# ── 全局异常处理器 ──────────────────────────────────────────────────────────

def register_error_handlers(app):
    """
    注册全局异常处理器
    
    Args:
        app: Flask 应用实例
    """
    
    # 判断是否为开发环境
    is_debug = app.debug or app.config.get('DEBUG', False)
    
    @app.errorhandler(AppException)
    def handle_app_exception(e):
        """处理应用自定义异常"""
        log.warning(f"AppException: {e.error_code} - {e.message}")
        response = format_error_response(e, include_stack_trace=is_debug)
        return jsonify(response), e.status_code
    
    @app.errorhandler(AuthException)
    def handle_auth_exception(e):
        """处理认证异常"""
        log.warning(f"AuthException: {e.message}")
        response = format_error_response(e, include_stack_trace=is_debug)
        return jsonify(response), e.status_code
    
    @app.errorhandler(PermissionException)
    def handle_permission_exception(e):
        """处理权限异常"""
        log.warning(f"PermissionException: {e.message}")
        response = format_error_response(e, include_stack_trace=is_debug)
        return jsonify(response), e.status_code
    
    @app.errorhandler(NotFoundException)
    def handle_not_found_exception(e):
        """处理资源未找到异常"""
        log.warning(f"NotFoundException: {e.message}")
        response = format_error_response(e, include_stack_trace=is_debug)
        return jsonify(response), e.status_code
    
    @app.errorhandler(BadRequestException)
    def handle_bad_request_exception(e):
        """处理请求参数错误异常"""
        log.warning(f"BadRequestException: {e.message}")
        response = format_error_response(e, include_stack_trace=is_debug)
        return jsonify(response), e.status_code
    
    @app.errorhandler(404)
    def handle_404(e):
        """处理 404 错误"""
        log.warning(f"404 Not Found: {request.path}")
        response = {
            'ok': False,
            'error_code': ErrorCode.NOT_FOUND,
            'message': '资源未找到',
            'path': request.path,
            'method': request.method,
        }
        return jsonify(response), 404
    
    @app.errorhandler(405)
    def handle_405(e):
        """处理 405 错误"""
        log.warning(f"405 Method Not Allowed: {request.path}")
        response = {
            'ok': False,
            'error_code': ErrorCode.METHOD_NOT_ALLOWED,
            'message': '请求方法不允许',
            'path': request.path,
            'method': request.method,
        }
        return jsonify(response), 405
    
    @app.errorhandler(500)
    def handle_500(e):
        """处理 500 错误"""
        log.error(f"Internal Server Error: {request.path}", exc_info=True)
        response = {
            'ok': False,
            'error_code': ErrorCode.UNKNOWN_ERROR,
            'message': '服务器内部错误' if not is_debug else str(e),
            'path': request.path,
            'method': request.method,
        }
        if is_debug:
            import traceback
            response['stack_trace'] = traceback.format_exc()
        return jsonify(response), 500
    
    @app.errorhandler(Exception)
    def handle_general_exception(e):
        """处理未捕获的异常"""
        log.error(f"Unhandled Exception: {request.path}", exc_info=True)
        response = {
            'ok': False,
            'error_code': ErrorCode.UNKNOWN_ERROR,
            'message': '未知错误' if not is_debug else str(e),
            'path': request.path,
            'method': request.method,
        }
        if is_debug:
            import traceback
            response['stack_trace'] = traceback.format_exc()
        return jsonify(response), 500
    
    log.info("Global exception handlers registered")


# ── 装饰器 ──────────────────────────────────────────────────────────────────

def handle_exceptions(f):
    """
    异常处理装饰器
    
    用法:
        @app.route('/api/example')
        @handle_exceptions
        def example():
            # 业务逻辑
            pass
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except AppException:
            # 自定义异常直接抛出,由全局处理器捕获
            raise
        except Exception as e:
            # 未捕获异常转换为 AppException
            log.error(f"Exception in {f.__name__}: {e}", exc_info=True)
            raise AppException(
                message=str(e),
                error_code=ErrorCode.UNKNOWN_ERROR,
                status_code=500
            )
    return decorated_function


# ── 请求验证装饰器 ──────────────────────────────────────────────────────────

def validate_request(required_fields):
    """
    请求参数验证装饰器
    
    Args:
        required_fields: 必填字段列表
    
    用法:
        @app.route('/api/example', methods=['POST'])
        @validate_request(['cluster_name', 'namespace', 'pod_name'])
        def example():
            data = request.get_json()
            # 业务逻辑
            pass
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            data = request.get_json(silent=True) or {}
            
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                raise BadRequestException(
                    message=f"缺少必填参数: {', '.join(missing_fields)}",
                    error_code=ErrorCode.INVALID_PARAMS,
                    details={'missing_fields': missing_fields}
                )
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
