
"""
调试 Weaviate 数据库：
- 查看所有 collections
- 查看 schema
- 查看数据量
- 展示几条样例数据
"""

from rag.retrievers.vector_retriever import get_weaviate_client


def main():
    client = get_weaviate_client()

    try:
        print("=" * 80)
        print("📦 Weaviate Collections")
        print("=" * 80)

        collections = client.collections.list_all()

        if not collections:
            print("❌ 当前没有任何 collection")
            return

        for name in collections:
            print(f"\n🧠 Collection: {name}")

            col = client.collections.get(name)

            # -----------------------------
            # 查看数据
            # -----------------------------
            print("\n📄 Sample Objects:\n")

            try:
                result = col.query.fetch_objects(limit=5)

                objs = result.objects

                if not objs:
                    print("⚠️ 当前 collection 没有数据")
                    continue

                print(f"✅ 查询到 {len(objs)} 条样例数据\n")

                for idx, obj in enumerate(objs, start=1):
                    print("-" * 80)
                    print(f"#{idx}")
                    print(f"UUID: {obj.uuid}")

                    props = obj.properties or {}

                    for k, v in props.items():
                        if isinstance(v, str) and len(v) > 200:
                            v = v[:200] + "..."

                        print(f"{k}: {v}")

                    print()

            except Exception as e:
                print(f"❌ 查询失败: {e}")

    finally:
        client.close()
        print("\n🔒 Weaviate client 已关闭")


if __name__ == "__main__":
    main()

    # python -m tests.show_weaviate