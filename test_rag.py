import rag, json
results = rag.retrieve('maa for db@aws', k=5)
stats = rag.index_stats()
print('Chunks:', stats['n_chunks'], 'Terms:', stats['n_terms'])
for i, r in enumerate(results):
    print(f"#{i+1} [{r['source']}] {r.get('title','')[:60]}")
