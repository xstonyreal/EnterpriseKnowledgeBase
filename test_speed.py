"""
响应速度测试
运行: python test_speed.py
"""

import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.ingest_service import initialize_knowledge_base
from app.core.engine import get_chat_response_stream

def test_speed():
    print("=" * 60)
    print("⚡ 响应速度测试")
    print("=" * 60)

    # 1. 加载向量库
    print("\n📂 加载向量库...")
    t0 = time.time()
    vectorstore = initialize_knowledge_base()
    load_time = (time.time() - t0) * 1000
    print(f"   加载耗时: {load_time:.2f} ms")

    if vectorstore is None:
        print("❌ 向量库为空，请先同步文件")
        return

    # 测试问题
    query = "侍女的作用？"
    print(f"\n📝 测试问题: {query}")
    print("-" * 60)

    # 2. 执行完整流程并计时
    t_start = time.time()
    first_token_time = None
    token_count = 0
    full_response = ""

    print("\n🤖 开始生成回答...\n")

    # 获取流式生成器
    stream_gen, sources = get_chat_response_stream(query, filter_domain=None)

    for chunk in stream_gen:
        if first_token_time is None:
            first_token_time = time.time() - t_start
            print(f"⏱️ 首 token 耗时: {first_token_time * 1000:.2f} ms")
            print("-" * 40)
        token_count += 1
        full_response += chunk

    t_total = time.time() - t_start

    print("\n" + "-" * 60)
    print("\n📊 测试结果汇总:")
    print(f"   ├─ 加载耗时:     {load_time:.2f} ms")
    print(f"   ├─ 首 token:     {first_token_time * 1000:.2f} ms")
    print(f"   ├─ 总耗时:       {t_total * 1000:.2f} ms")
    print(f"   ├─ 生成 token:   {token_count}")
    if t_total > 0:
        print(f"   └─ 推理速度:     {token_count / t_total:.1f} tok/s")

    print(f"\n📝 回答预览: {full_response[:200]}...")

    # 3. 瓶颈判断
    print("\n" + "=" * 60)
    print("🎯 瓶颈分析:")
    print("=" * 60)

    if first_token_time and first_token_time > 3:
        print("   ⚠️ 首 token > 3s → 建议:")
        print("      1. 减少检索数量 (k=4 → k=2)")
        print("      2. 使用更小的模型 (0.5B)")
        print("      3. 减少切片大小 (CHUNK_SIZE)")
    elif first_token_time and first_token_time > 1:
        print(f"   ⚠️ 首 token {first_token_time*1000:.0f}ms → 可接受")
    else:
        print(f"   ✅ 首 token 响应很快 ({first_token_time*1000:.0f}ms)")

    if load_time > 2000:
        print(f"   ⚠️ 加载耗时 {load_time:.0f}ms → 索引较大，首次访问较慢")
    else:
        print(f"   ✅ 加载正常 ({load_time:.0f}ms)")

    # 4. 来源信息
    if sources:
        print(f"\n📚 参考来源: {len(sources)} 个文档")
        for src in sources[:2]:
            print(f"   - {src}")

    print("=" * 60)

if __name__ == "__main__":
    test_speed()