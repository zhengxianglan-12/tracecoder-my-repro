import pandas as pd
import json

df1 = pd.read_csv('results/classeval_batch_0_9.csv')
df2 = pd.read_csv('results/classeval_batch_10_24.csv')
df = pd.concat([df1, df2], ignore_index=True)

failed_df = df[df['final_passed'] == False]

for _, row in failed_df.iterrows():
    print(f"\n====== 深度分析: {row['task_id']} ======")
    
    def get_score(eval_str):
        try:
            d = json.loads(eval_str) if isinstance(eval_str, str) else eval_str
            return f"{d.get('passed_count',0)}/{d.get('total_count',0)}"
        except: 
            return '?/?'
    
    print(f"初始得分: {get_score(row.get('direct_gen_eval'))}")
    print(f"最终得分: {get_score(row.get('final_eval'))}")
    
    try:
        final_eval = json.loads(row['final_eval']) if isinstance(row['final_eval'], str) else row['final_eval']
        failed_tests = final_eval.get('failed_tests', [])
        if failed_tests:
            print('最终失败的具体测试:')
            for ft in failed_tests:
                print(f"  - {ft['name']}: {ft['type']}")
    except Exception as e:
        print('解析具体测试失败:', e)

    print('修复轮次轨迹:')
    log_str = row.get('debug_session_log')
    if pd.isna(log_str) or not log_str:
        print('  无调试记录')
    else:
        try:
            log = json.loads(log_str) if isinstance(log_str, str) else log_str
            for attempt in log:
                a_num = attempt.get('attempt')
                a_eval = attempt.get('eval_result', {})
                a_score = a_eval.get('passed_count', 0)
                print(f"  - 第 {a_num} 轮尝试得分: {a_score} / {a_eval.get('total_count', 0)}")
        except Exception as e:
            print('  解析 log 失败:', e)