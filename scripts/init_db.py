"""初始化 MySQL 数据库表结构"""
from loguru import logger
from memory.long_term import LongTermMemory


def main():
    logger.info("正在初始化数据库表...")
    LongTermMemory().create_tables()
    logger.success("✅ 数据库表初始化完成")


if __name__ == "__main__":
    main()
