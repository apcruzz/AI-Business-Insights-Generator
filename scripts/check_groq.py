"""Test Groq from the terminal holding the API key, using fictional data only.

Run from the project directory: .venv/bin/python -m scripts.check_groq
"""
import sys

import pandas as pd

from backend.analyst_agent import analyze_question
from backend.analyst_datasets import DATASETS
from backend.config import GROQ_MODEL
from backend.groq_client import GroqError, configured
from backend.normalizer import normalize


def main():
    if not configured():
        print('GROQ_API_KEY is not set in this terminal. Set it locally before running this check.')
        return 1
    # Exercise the actual analyst loop, including a query and explanation, without a user's file.
    source = pd.DataFrame({'Hour': [9, 10, 10], 'Revenue': [12, 20, 30]})
    mapping = {'Hour': 'Hour', 'Net_Sales': 'Revenue'}
    normalized = normalize(source, mapping, 'Cafe', 'USD')
    normalized['filename'] = 'fictional_connection_check.csv'
    dataset_id = DATASETS.put(source, normalized, mapping)
    print('Testing GPT-OSS 120B using three fictional rows. No uploaded files or key values are printed.', flush=True)
    try:
        result = analyze_question({'provider': 'groq', 'model': GROQ_MODEL, 'datasetId': dataset_id,
                                   'question': 'Which hour has the highest net sales? Include the hour and revenue.'})
    except GroqError as error:
        print(str(error))
        if error.diagnostic:
            print('Groq diagnostic:', error.diagnostic)
        return 1
    except (ValueError, OSError):
        print('The check could not complete. Verify the backend environment and internet connection.')
        return 1
    print('Status:', result['status'])
    print('Answer:', result['answer'])
    print('Expected result: hour 10, USD 50.00.')
    print('Supporting calculations:', len(result.get('evidence', [])))
    return 0 if result['status'] == 'answered' and result.get('evidence') else 1


if __name__ == '__main__':
    sys.exit(main())
