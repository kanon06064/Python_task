import sys
import os

print("--- Python環境診断 ---")

# 実行されているPython.exeの正確な場所
print(f"実行中のPython: {sys.executable}")

# Pythonがライブラリを探しに行く場所のリスト
print("\nライブラリ検索パス (sys.path):")
for path in sys.path:
    print(path)

print("\n--- 診断完了 ---")
input("何かキーを押すと終了します...")