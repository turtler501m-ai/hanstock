import re

with open('src/dashboard.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

# Fix line 2022 (index 2021)
if 'diff_reason' in lines[2021] and 'DRY_RUN' in lines[2021]:
    lines[2021] = '                        "diff_reason": "DRY_RUN"\n'

# Fix line 2035 (index 2034)
if 'diff_reason' in lines[2034] and '보정' in lines[2034]:
    lines[2034] = '                    diff_reason = "신규매수/매도 대기 보정 완료"\n'

# Fix line 2037 (index 2036)
if 'diff_reason' in lines[2036] and '보정' in lines[2036]:
    lines[2036] = '                    diff_reason = f"수량 불일치: {recorded_qty} -> {ch[\'qty\']} 보정 필요"\n'

with open('src/dashboard.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Fixed!")