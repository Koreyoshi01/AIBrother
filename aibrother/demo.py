"""
问师兄 — NanoBot 四种场景演示

使用方式：
  1. 在 aibrother/config.json 中配置 API key
  2. 安装 nanobot：pip install -e ..
  3. 运行：PYTHONUTF8=1 python aibrother/demo.py
     （Windows 中文系统需 PYTHONUTF8=1 解决编码问题）
"""

import asyncio
import sys
from pathlib import Path

from nanobot.nanobot import Nanobot

AIBROTHER_DIR = Path(__file__).parent.resolve()
CONFIG_PATH = AIBROTHER_DIR / "config.json"

SCENARIOS = [
    ("🧪 做实验", "师兄，我要做二氧化碳的吸收与解析实验，需要用什么试剂？试剂比例是多少？"),
    ("🧪 做实验", "我做二氧化碳吸收实验时，吸收效率一直上不去只有60%，可能是什么原因？"),
    ("📄 写论文", "师兄，我刚进实验室做CO2捕获方向，帮我推荐一篇前沿的论文？"),
    ("📄 写论文", "我想用离子液体做CO2吸收剂，这个idea靠谱吗？有什么优缺点？"),
    ("📊 做汇报", "师兄，我这周的实验数据出来了，要做一个组会汇报，应该怎么组织PPT？"),
    ("📝 做日记", "我今天做了三组CO2吸收实验，温度分别是25°C、30°C、35°C，每组测了吸收速率和容量。25°C时吸收效果最好，30°C次之，35°C时溶液有点发黄。气体流量太大时吸收效率会下降。"),
]


async def main():
    print("=" * 60)
    print("  问师兄 NanoBot Demo")
    print("  四种场景 · 分层知识库 · 可溯源")
    print("=" * 60)

    if not CONFIG_PATH.exists():
        print(f"\n[错误] 找不到配置文件: {CONFIG_PATH}")
        print("请确保在 AIBrother 项目根目录下运行")
        sys.exit(1)

    bot = Nanobot.from_config(str(CONFIG_PATH))

    for tag, question in SCENARIOS:
        print(f"\n{'─' * 60}")
        print(f"  {tag}")
        print(f"  用户: {question}")
        print(f"{'─' * 60}")

        try:
            result = await bot.run(question)
            print(f"\n回答:\n{result.content}")
            if result.tools_used:
                print(f"\n  [使用工具]: {', '.join(result.tools_used)}")
        except Exception as e:
            print(f"\n  [错误]: {e}")

    print(f"\n{'=' * 60}")
    print("  Demo 运行完毕")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
