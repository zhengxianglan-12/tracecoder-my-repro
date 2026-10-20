import pandas as pd
import glob
import os

# 找到所有 classeval 的文件
files = glob.glob('results/classeval*.csv')

# 用一个字典记录每道题在哪些文件里出现过
task_records = {}

for f in files:
    try:
        df = pd.read_csv(f)
        if 'task_id' not in df.columns:
            continue
        for _, row in df.iterrows():
            tid = row['task_id']
            if tid not in task_records:
                task_records[tid] = []
            
            # 记录：文件名 | 初始通过 | 最终通过 | 最终保留代码的长度
            task_records[tid].append({
                'file': os.path.basename(f),
                'init_pass': row.get('direct_gen_passed', False),
                'final_pass': row.get('final_passed', False),
                'final_len': len(str(row.get('final_code', '')))
            })
    except Exception as e:
        pass

# 找出那些被重测（出现超过1次）的题目
print('=== 被重测（出现多次）的任务清单 ===\n')
retested_count = 0
for tid in sorted(task_records.keys(), key=lambda x: int(x.split('_')[-1])):
    records = task_records[tid]
    if len(records) > 1:
        retested_count += 1
        print(f'任务 {tid} (共测了 {len(records)} 次):')
        for r in records:
            mark = '✅' if r['final_pass'] else '❌'
            print(f"  - 来源文件: {r['file']:<25} | 初始: {r['init_pass']} | 最终: {mark} | 最终代码长度: {r['final_len']}")
        print('-' * 50)

print(f'\n结论：共有 {retested_count} 道题经历了重测。')