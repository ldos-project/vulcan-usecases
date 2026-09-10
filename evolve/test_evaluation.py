"""
Tester script to check if the evaluation functions are working as expected.
"""
from pprint import pprint
import sys
import evaluator

if __name__ == "__main__":
    test_program = sys.argv[1] if len(sys.argv) > 1 else "init_programs/init_simple.cpp"
    print(f"Testing evaluation with program: {test_program}")
    
    eval_result, mongo_result = evaluator.evaluate_internal(
        test_program, insert_into_mongo=False
    )
    
    print("Evaluation Metrics:")
    pprint(eval_result.metrics)

    print("\nEvaluation Artifacts:")
    pprint(eval_result.artifacts)

    print("\nMongo Result Dict:")
    pprint(mongo_result)