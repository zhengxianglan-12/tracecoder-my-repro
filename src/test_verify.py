import sys
sys.path.insert(0, '.')

from traceRunner import execute_code_and_capture_prints_last

# 验证1：明确正确的实现
code_pass = '''
def add(a, b):
    return a + b

import unittest
class TestAdd(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(1, 2), 3)
'''

print("=== 验证1：明确正确的实现 ===")
result = execute_code_and_capture_prints_last(code_pass)
print(result['display_output'])
print("\n\n")

# 验证2：明确错误的实现
code_fail = '''
def add(a, b):
    return a - b  # 故意写错

import unittest
class TestAdd(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(1, 2), 3)
'''

print("=== 验证2：明确错误的实现 ===")
result = execute_code_and_capture_prints_last(code_fail)
print(result['display_output'])
print("\n\n")

# 验证3：抛出异常的实现
code_error = '''
def divide(a, b):
    return a / b  # b=0 会抛 ZeroDivisionError

import unittest
class TestDivide(unittest.TestCase):
    def test_divide_by_zero(self):
        self.assertEqual(divide(1, 0), 0)
'''

print("=== 验证3：抛出异常的实现 ===")
result = execute_code_and_capture_prints_last(code_error)
print(result['display_output'])