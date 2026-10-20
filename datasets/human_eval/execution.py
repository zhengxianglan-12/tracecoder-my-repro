from typing import Optional, Callable, Dict
import ast
import contextlib
import faulthandler
import io
import os
import multiprocessing
import platform
import signal
import tempfile


# ========== 原文件前面的辅助函数保持不变 ==========

def _get_total_test_cases(test_code: str, task_id_for_warning: str = "Unknown") -> int:
    try:
        tree = ast.parse(test_code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "check":
                assert_count = 0
                for sub_node in ast.walk(node):
                    if isinstance(sub_node, ast.Assert):
                        assert_count += 1
                return assert_count
        return 0
    except SyntaxError:
        print(
            f"Warning: SyntaxError parsing test code for task_id {task_id_for_warning} (static count). Assuming 0 test cases.")
        return 0


class AssertTransformer(ast.NodeTransformer):
    def __init__(self, passed_var: str, failed_var: str, total_executed_var: str):
        self.passed_var = passed_var
        self.failed_var = failed_var
        self.total_executed_var = total_executed_var


    def visit_Assert(self, node: ast.Assert) -> list:
        inc_total_stmt_str = f"globals()['{self.total_executed_var}'] += 1"
        inc_total_stmt = ast.parse(inc_total_stmt_str).body[0]
        pass_stmt_str = f"globals()['{self.passed_var}'] += 1"
        pass_stmt = ast.parse(pass_stmt_str).body[0]
        fail_stmt_str = f"globals()['{self.failed_var}'] += 1"
        fail_stmt = ast.parse(fail_stmt_str).body[0]
        try_body = [
            ast.Assert(test=node.test, msg=node.msg),
            pass_stmt
        ]
        except_handler = ast.ExceptHandler(
            type=ast.Name(id='AssertionError', ctx=ast.Load()),
            name=None,
            body=[fail_stmt]
        )
        try_node = ast.Try(body=try_body, handlers=[except_handler], orelse=[], finalbody=[])
        return [inc_total_stmt, try_node]


# ================================================
# ★ 关键修改：unsafe_execute 提到模块顶层，不再嵌套在 check_correctness 里
# ================================================
def _unsafe_execute(problem, PASSED_COUNTER, FAILED_COUNTER, TOTAL_EXECUTED_COUNTER,
                    defined_total_count, result_list_proxy):
    """在子进程中执行，评估生成代码——必须是模块顶层函数才能被 pickle"""
    exec_globals = {
        PASSED_COUNTER: 0,
        FAILED_COUNTER: 0,
        TOTAL_EXECUTED_COUNTER: 0,
        "__builtins__": __builtins__
    }

    with _create_tempdir():
        import os as _os_module
        import shutil as _shutil_module
        _original_os_chdir = _os_module.chdir
        _original_os_getcwd = _os_module.getcwd
        _original_os_rmdir = _os_module.rmdir
        _original_shutil_rmtree = _shutil_module.rmtree

        reliability_guard()

        try:
            test_ast = ast.parse(problem["test"])
            transformer = AssertTransformer(PASSED_COUNTER, FAILED_COUNTER, TOTAL_EXECUTED_COUNTER)
            transformed_test_ast = transformer.visit(test_ast)
            ast.fix_missing_locations(transformed_test_ast)
            compiled_transformed_test = compile(
                transformed_test_ast,
                filename=f"<transformed_test_{problem.get('task_id','Unknown')}>",
                mode="exec"
            )
        except Exception as e:
            result_list_proxy.append({
                "status": f"failed: AST transformation error: {type(e).__name__}: {e}",
                PASSED_COUNTER: 0,
                FAILED_COUNTER: defined_total_count,
                TOTAL_EXECUTED_COUNTER: 0
            })
            _os_module.chdir = _original_os_chdir
            _os_module.getcwd = _original_os_getcwd
            _os_module.rmdir = _original_os_rmdir
            _shutil_module.rmtree = _original_shutil_rmtree
            return

        program_to_run_entry_point = problem["prompt"] + problem["completion"]
        check_call_str = f"\ncheck({problem['entry_point']})"

        try:
            with _swallow_io():
                with _time_limit(problem.get("_timeout", 10)):
                    exec(program_to_run_entry_point, exec_globals)
                    exec(compiled_transformed_test, exec_globals)
                    exec(check_call_str, exec_globals)

            result_list_proxy.append({
                "status": "completed_execution",
                PASSED_COUNTER: exec_globals.get(PASSED_COUNTER, 0),
                FAILED_COUNTER: exec_globals.get(FAILED_COUNTER, 0),
                TOTAL_EXECUTED_COUNTER: exec_globals.get(TOTAL_EXECUTED_COUNTER, 0)
            })

        except _TimeoutException:
            result_list_proxy.append({
                "status": "timed out",
                PASSED_COUNTER: 0,
                FAILED_COUNTER: defined_total_count,
                TOTAL_EXECUTED_COUNTER: exec_globals.get(TOTAL_EXECUTED_COUNTER, 0)
            })
        except BaseException as e:
            err_type = type(e).__name__
            err_msg = str(e).replace('\n', ' ')
            result_list_proxy.append({
                "status": f"failed: {err_type}: {err_msg}",
                PASSED_COUNTER: 0,
                FAILED_COUNTER: defined_total_count,
                TOTAL_EXECUTED_COUNTER: exec_globals.get(TOTAL_EXECUTED_COUNTER, 0)
            })
        finally:
            _os_module.chdir = _original_os_chdir
            _os_module.getcwd = _original_os_getcwd
            _os_module.rmdir = _original_os_rmdir
            _shutil_module.rmtree = _original_shutil_rmtree


def check_correctness(problem: Dict, completion: str, timeout: float,
                      completion_id: Optional[int] = None) -> Dict:
    task_id = problem.get("task_id", "Unknown")
    problem = dict(problem)          # 不影响原 dict
    problem["completion"] = completion
    problem["_timeout"] = timeout

    defined_total_count = _get_total_test_cases(problem["test"], task_id_for_warning=task_id)

    PASSED_COUNTER = "_eval_passed_count"
    FAILED_COUNTER = "_eval_failed_count"
    TOTAL_EXECUTED_COUNTER = "_eval_total_executed_assertions"

    manager = multiprocessing.Manager()
    execution_result_details_list = manager.list()

    # ★ 现在 target 是模块顶层函数 _unsafe_execute，可以被 pickle
    p = multiprocessing.Process(
        target=_unsafe_execute,
        args=(problem, PASSED_COUNTER, FAILED_COUNTER, TOTAL_EXECUTED_COUNTER,
              defined_total_count, execution_result_details_list)
    )
    p.start()
    p.join(timeout=timeout + 1)

    passed_count = 0
    failed_count = 0
    final_result_str = "failed: unknown execution error"

    if p.is_alive():
        p.kill()
        if not execution_result_details_list:
            execution_result_details_list.append({
                "status": "timed out (killed)",
                PASSED_COUNTER: 0,
                FAILED_COUNTER: defined_total_count,
                TOTAL_EXECUTED_COUNTER: 0
            })

    if not execution_result_details_list:
        final_result_str = "failed: process terminated without result"
        failed_count = defined_total_count
    else:
        exec_details = execution_result_details_list[0]
        status = exec_details["status"]
        passed_count = exec_details[PASSED_COUNTER]
        failed_count_from_exec = exec_details[FAILED_COUNTER]

        if status == "completed_execution":
            if failed_count_from_exec == 0 and passed_count >= defined_total_count:
                final_result_str = "passed"
            elif passed_count > 0:
                final_result_str = f"passed_partial: {passed_count}/{defined_total_count} assertions passed"
            else:
                final_result_str = f"failed: 0/{defined_total_count} assertions passed"

            failed_count = failed_count_from_exec
        else:
            final_result_str = status
            passed_count = 0
            failed_count = defined_total_count

    return dict(
        task_id=task_id,
        passed=final_result_str == "passed",
        result=final_result_str,
        completion_id=completion_id,
        passed_count=passed_count,
        failed_count=failed_count,
        total_count=defined_total_count,
    )


# ========== 下方原有辅助函数不变 ==========

@contextlib.contextmanager
def _time_limit(seconds: float):
    if platform.system() == "Windows":
        yield
        return

    def signal_handler(signum, frame):
        raise _TimeoutException("Timed out!")

    signal.setitimer(signal.ITIMER_REAL, seconds)
    signal.signal(signal.SIGALRM, signal_handler)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


class _TimeoutException(Exception):
    pass


class WriteOnlyStringIO(io.StringIO):
    def read(self, *args, **kwargs): raise IOError
    def readline(self, *args, **kwargs): raise IOError
    def readlines(self, *args, **kwargs): raise IOError
    def readable(self, *args, **kwargs): return False


class _redirect_stdin(contextlib._RedirectStream):
    _stream = 'stdin'


@contextlib.contextmanager
def _swallow_io():
    stream = WriteOnlyStringIO()
    with contextlib.redirect_stdout(stream):
        with contextlib.redirect_stderr(stream):
            with _redirect_stdin(stream):
                yield


@contextlib.contextmanager
def _create_tempdir():
    with tempfile.TemporaryDirectory() as dirname:
        with _chdir(dirname):
            yield dirname


@contextlib.contextmanager
def _chdir(root):
    if root == ".":
        yield
        return
    cwd = os.getcwd()
    os.chdir(root)
    try:
        yield
    except BaseException as exc:
        raise exc
    finally:
        os.chdir(cwd)


def reliability_guard(maximum_memory_bytes: Optional[int] = None):
    if maximum_memory_bytes is not None:
        if platform.system() != "Windows":
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (maximum_memory_bytes, maximum_memory_bytes))
            resource.setrlimit(resource.RLIMIT_DATA, (maximum_memory_bytes, maximum_memory_bytes))
            if not platform.uname().system == 'Darwin':
                resource.setrlimit(resource.RLIMIT_STACK, (maximum_memory_bytes, maximum_memory_bytes))
    faulthandler.disable()
    import builtins
    builtins.exit = None
    builtins.quit = None
    import os as guarded_os, shutil as guarded_shutil, subprocess as guarded_subprocess, sys as guarded_sys
    guarded_os.environ['OMP_NUM_THREADS'] = '1'
    for module in [guarded_os, guarded_shutil, guarded_subprocess]:
        for attr in ['kill', 'system', 'putenv', 'remove', 'removedirs', 'rmdir', 'setuid',
                     'fork', 'forkpty', 'killpg', 'rename', 'renames', 'truncate', 'replace',
                     'unlink', 'fchmod', 'fchown', 'chmod', 'chown', 'chroot', 'lchflags',
                     'lchmod', 'lchown', 'getcwd', 'chdir', 'rmtree', 'move', 'Popen']:
            if hasattr(module, attr):
                setattr(module, attr, None)
    if isinstance(__builtins__, dict):
        __builtins__['help'] = None
    else:
        builtins.help = None
    for mod_name in ['ipdb', 'joblib', 'resource', 'psutil', 'tkinter']:
        guarded_sys.modules[mod_name] = None