import pandas as pd
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    df = pd.read_parquet('./data/classeval_test.parquet')
    problem = df.iloc[0].to_dict()
    
    # 你的 good_code
    good_code = '''
import logging
import datetime

class AccessGatewayFilter:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.current_user_info = None

    def filter(self, request):
        path = request.get('path', '')
        if path.startswith('/api') or path.startswith('/login'):
            return True
        if 'headers' not in request or 'Authorization' not in request['headers']:
            return False
        auth = request['headers']['Authorization']
        jwt = auth.get('jwt', '')
        user = auth.get('user', {})
        user_name = user.get('name', '')
        if not jwt.startswith(user_name):
            return None
        today_str = str(datetime.date.today())
        if jwt == user_name + today_str:
            self.set_current_user_info_and_log(user)
            return True
        if user.get('level', 0) <= 3:
            return False
        return True

    def is_start_with(self, request_uri):
        return request_uri.startswith('/api') or request_uri.startswith('/login')

    def get_jwt_user(self, request):
        if 'headers' not in request or 'Authorization' not in request['headers']:
            return None
        auth = request['headers']['Authorization']
        jwt = auth.get('jwt', '')
        user = auth.get('user', {})
        user_name = user.get('name', '')
        if not jwt.startswith(user_name):
            return None
        today_str = str(datetime.date.today())
        if jwt == user_name + today_str:
            return user
        return None

    def set_current_user_info_and_log(self, user):
        self.current_user_info = user
'''

    test_code = problem.get('test', '')
    full_code = good_code + "\n\n" + test_code
    print(test_code)
    # 直接 exec 合并后的代码
    exec_namespace = {}
    exec(full_code, exec_namespace, exec_namespace)
    
    # 找到 TestCase 并运行
    import unittest
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for name, obj in exec_namespace.items():
        if isinstance(obj, type) and issubclass(obj, unittest.TestCase) and obj is not unittest.TestCase:
            suite.addTests(loader.loadTestsFromTestCase(obj))
            
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print(f"\n通过: {result.testsRun - len(result.failures) - len(result.errors)} / {result.testsRun}")

if __name__ == '__main__':
    main()