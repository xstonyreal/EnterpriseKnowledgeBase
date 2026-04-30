1. 檢查 BM25 中是否包含特定關鍵字

.venv\Scripts\python -c "import pickle; data=pickle.load(open('data/bm25_db/bm25.pkl','rb')); docs=[d for d in data['documents'] if '關鍵字' in d.page_content]; print(f'找到 {len(docs)} 個切片'); print(docs[0].page_content[:200] if docs else '無')"

2. 測試 BM25 檢索（分詞 + Top 5 來源）

.venv\Scripts\python -c "
import pickle
import jieba
data = pickle.load(open('data/bm25_db/bm25.pkl', 'rb'))
bm25 = data['instance']
query = '你的查詢'
tokens = jieba.lcut_for_search(query)
scores = bm25.get_scores(tokens)
top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:5]
print('查詢:', query)
print('分詞:', tokens)
print('Top 5 分數:', [scores[i] for i in top_idx])
print('Top 5 來源:', [data['documents'][i].metadata.get('source') for i in top_idx])
"

3. 測試 SearchService 混合檢索

.venv\Scripts\python -c "
from app.services.search_service import SearchService
s = SearchService()
results = s.hybrid_search('你的查詢', top_n=5)
for r in results:
    print(r['metadata'].get('source'), r['metadata'].get('domain'), r['score'])

4. 測試 engine.py 完整流程

.venv\Scripts\python -c "
from app.core.engine import get_chat_response_stream
gen, sources = get_chat_response_stream('你的查詢', filter_domain='未分类资产')
print('sources:', sources)
"