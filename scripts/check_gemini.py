"""Optional LIVE check: sends only fictional data to Gemini and uses API quota."""
import argparse
import sys
import pandas as pd

from backend.analyst_agent import analyze_overview
from backend.analyst_datasets import DATASETS
from backend.gemini_client import GEMINI_MODEL, GEMINI_MODELS, GeminiError, configured
from backend.normalizer import normalize


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=tuple(GEMINI_MODELS), default=GEMINI_MODEL)
    args = parser.parse_args(argv)
    if not configured():
        print('GEMINI_API_KEY is not set in this terminal. No request was sent.')
        return 1
    source = pd.DataFrame({'Date': ['2026-01-01', '2026-01-02', '2026-01-02'],
                           'Product': ['Tea', 'Coffee', 'Tea'], 'Revenue': [12, 20, 30]})
    mapping = {'Date': 'Date', 'Product_Name': 'Product', 'Net_Sales': 'Revenue'}
    normalized = normalize(source, mapping, 'Cafe', 'USD')
    normalized['filename'] = 'fictional_gemini_connection_check.csv'
    dataset_id = DATASETS.put(source, normalized, mapping)
    print(f'LIVE Gemini check using {args.model} and fictional data only. This uses your API project quota.', flush=True)
    try:
        result = analyze_overview({'provider': 'gemini', 'model': args.model, 'datasetId': dataset_id, 'filters': {}})
    except (GeminiError, ValueError) as error:
        print(str(error))
        return 1
    if result['status'] != 'answered':
        print('The connection responded, but a checked overview could not be completed.')
        return 1
    print('PASS: Gemini returned an overview with supporting calculations. No uploaded files were used.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
