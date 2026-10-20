import sys
import time
import datetime
import json
import os
import logging
from itertools import islice
from tqdm import tqdm

# Import our split-out modules
from config import setup_arg_parser, DATASET_PATHS
from reporting import save_results, print_summary
# Import process_problem and _load_check_correctness_func from problem_processor
from problem_processor import process_problem, _load_check_correctness_func
from src.dataset_loader import load_dataset


def main():
    # 新增：配置全局日志，自动保存到 results/run_logs/ 目录
    os.makedirs('results/run_logs', exist_ok=True)
    log_filename = f"results/run_logs/terminal_output_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    # 配置 logging，同时输出到终端和文件
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s', # 只输出信息本身
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'), # 写入文件
            logging.StreamHandler(sys.stdout)                    # 输出到终端
        ]
    )
    
    # 把 print 替换成 logging.info (这样以后代码里所有的 print 都会自动落盘)
    global print
    print = logging.info
    
    print(f"✅ 本次运行日志将自动保存至: {log_filename}")

    # 1. Setup and parse arguments
    parser = setup_arg_parser()
    args = parser.parse_args()

    # 2. Generate experiment ID and output filename
    run_time = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    EXPERIMENT_ID = f"{args.dataset}_{args.model.replace('/', '_')}_{run_time}"
    OUTPUT_CSV_FILENAME = args.output_file or f"results/experiment_{EXPERIMENT_ID}.csv"
    
    # 新增：自动保存运行元数据（溯源信息）
    run_meta = {
        "run_timestamp": run_time,
        "command_args": sys.argv,
        "model": args.model,
        "dataset": args.dataset,
        "git_commit": "未配置Git，无法记录"
    }
    meta_path = f'results/run_logs/run_meta_{EXPERIMENT_ID}.json'
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(run_meta, f, indent=4, ensure_ascii=False)
    print(f"✅ 运行元数据已成功保存至: {meta_path}")

    # 3. Load the dataset
    if args.dataset not in DATASET_PATHS:
        print(f"Error: Path for dataset '{args.dataset}' is not defined in config.py.")
        sys.exit(1)

    try:
        actual_dataset_path = DATASET_PATHS[args.dataset]["data_path"]
        datasets = load_dataset(args.dataset, actual_dataset_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error loading dataset: {e}")
        sys.exit(1)
    except KeyError:
        print(f"Error: The configuration for dataset '{args.dataset}' is missing 'data_path'. Please check config.py.")
        sys.exit(1)

    try:
        check_correctness_func = _load_check_correctness_func(args.dataset)
    except (ValueError, ImportError) as e:
        print(f"Error loading the evaluation function check_correctness: {e}")
        sys.exit(1)

    print(f"--- Experiment Start: {EXPERIMENT_ID} ---")
    print(f"Arguments: {vars(args)}")

    # 4. Set up the problem iterator
    problem_keys = list(datasets.keys())
    start_index = args.start_index
    max_problems = len(problem_keys) if args.max_problems == -1 else args.max_problems
    end_index = min(start_index + max_problems, len(problem_keys))

    problem_iterator = islice(problem_keys, start_index, end_index)

    results_data = []

    # 5. Main loop
    try:
        for task_id in tqdm(problem_iterator, total=(end_index - start_index), desc="Processing problems"):
            problem_result = process_problem(datasets[task_id], task_id, args, check_correctness_func)
            results_data.append(problem_result)
    except KeyboardInterrupt:
        print("\nManual interruption detected. Saving existing results...")
    finally:
        # 6. Save results and print summary
        save_results(results_data, OUTPUT_CSV_FILENAME)
        print_summary(results_data)


if __name__ == '__main__':
    main()