import re

input_file = 'docs/code-guide/code-guide_agent-local-method.md'
output_file = 'docs/code-guide/code-guide_agent-local-method.cleaned.md'

# 1. 去除常见命令行复制边框和隐藏字符
def clean_line(line):
    # 去除全角边框符号和多余星号
    line = re.sub(r'[┃┏┓┗┛━]+', '', line)
    # 去除多余的全角空格、不可见字符
    line = line.replace('\u3000', '').replace('\u200b', '')
    # 去除行首多余的星号和空格
    line = re.sub(r'^\s*\*+\s*', '', line)
    # 去除行尾多余的星号和空格
    line = re.sub(r'\s*\*+\s*$', '', line)
    # 去除多余的空白
    return line.rstrip()

# 2. 检测并标记 Python 代码块
def process_lines(lines):
    output = []
    in_code = False
    code_block = []
    for i, line in enumerate(lines):
        clean = clean_line(line)
        # 检查是否是代码行（以def/async/class开头或缩进4空格）
        is_code = (
            re.match(r'^\s*(def |async def |class )', clean) or
            (len(clean) > 0 and (line.startswith('    ') or line.startswith('\t')))
        )
        if is_code:
            if not in_code:
                # 代码块开始
                in_code = True
                output.append('```python')
            code_block.append(clean)
        else:
            if in_code:
                # 代码块结束
                output.extend(code_block)
                output.append('```')
                code_block = []
                in_code = False
            if clean.strip():  # 跳过空行
                output.append(clean)
    # 结尾如果还在代码块内
    if in_code:
        output.extend(code_block)
        output.append('```')
    return output

if __name__ == '__main__':
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    processed = process_lines(lines)
    with open(output_file, 'w', encoding='utf-8') as f:
        for line in processed:
            f.write(line.rstrip() + '\n')
    print(f"过滤和代码块标记完成，输出文件：{output_file}")