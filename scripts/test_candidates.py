import subprocess

candidates = [
    'LeadGrowGTM/reddit-find',
    'avisangle/reddit_agent',
    'dialog-tools/reddit-research-mcp',
    'gguyon0925/n8n-reddit-scraper',
    'nama1arpit/reddit-streaming-pipeline',
    'netto14cr/reddit_sentiment_analysis',
    'lh1207/reddit-kb-mcp-server',
    'DaveOkpare/multimodal-search',
    'marta-baratto/Reddit_sentiment',
    'nssharmaofficial/reddit-hole',
    'lancedb/vectordb-recipes',
    'KritBlade/VectFox'
]

print("Verificando accesibilidad de repositorios candidatos...")
for c in candidates:
    url = f"https://github.com/{c}.git"
    try:
        res = subprocess.run(["git", "ls-remote", "--heads", url], capture_output=True, text=True, timeout=10)
        status = "OK" if res.returncode == 0 else f"FAIL: {res.stderr.strip()[:60]}"
    except Exception as e:
        status = f"ERROR: {e}"
    print(f"[{status}] {c}")
