"""Upload data_july_2026.csv directly to Google Sheet."""
import sys, os
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Import upload function from upload_to_sheet
import importlib.util
spec = importlib.util.spec_from_file_location("uts", "upload_to_sheet.py")
uts  = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uts)

uts.upload_csv_to_sheet("data_july_2026.csv")
