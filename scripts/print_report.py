import json

with open(r"F:\reddit_intelligence_radar\logs\integrity_audit.json", encoding="utf-8") as f:
    d = json.load(f)

for b in ["Lote 1", "Lote 2"]:
    print(f"\n{'='*20} {b} ({d['batch_1']['total'] if b=='Lote 1' else d['batch_2']['total']} repos) {'='*20}")
    for r in d["repositories"]:
        if r["batch"] == b:
            print(f"{r['id']:<38} | HEAD: {r['git_head']} | Archivos: {r['file_count']:>5} | {r['size_mb']:>7.2f} MB | Claves: {r['key_files_ok']}/{r['key_files_total']} OK")
