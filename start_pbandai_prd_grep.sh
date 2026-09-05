python3 -m pip install --quiet --user torch transformers sentencepiece opencc-python-reimplemented 2>&1 | tail -5; python3 -c "import torch, transformers, sentencepiece, opencc; print('torch', torch.__version__); print('transformers', transformers.__version__)"
python3 pbandai_scraper_v2.py
