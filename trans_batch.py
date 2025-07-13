from deep_translator import GoogleTranslator
import re
import os
import glob
import argparse
import time

def is_number_or_scientific(text):
    """检查文本是否为数字或科学计数法（以E或N结尾的数字）"""
    text = text.strip()
    
    # 检查是否为空或只有符号
    if not text or text in ['-', '+']:
        return True
    
    # 检查是否为纯数字（包括负数）
    if text.lstrip('-+').isdigit():
        return True
    
    # 检查是否为小数（包括负数和使用逗号作为小数点的欧式格式）
    try:
        # 尝试解析标准小数格式
        float(text)
        return True
    except ValueError:
        try:
            # 尝试解析欧式小数格式（逗号作为小数点）
            float(text.replace(',', '.'))
            return True
        except ValueError:
            pass
    
    # 检查是否为科学计数法（以E结尾）
    if text.upper().endswith('E') or re.match(r'^[+-]?\d+\.?\d*E[+-]?\d*$', text.upper()):
        return True
    
    # 检查是否为以E或N结尾的数字
    if re.match(r'^[+-]?\d+[EN]$', text.upper()):
        return True
    
    # 检查是否为分数格式（如 3/4）
    if re.match(r'^\d+/\d+$', text):
        return True
        
    return False

def extract_translatable_content(file_path):
    """提取文件中需要翻译的内容"""
    translatable_items = []
    
    try:
        # 尝试不同的编码
        encodings = ['utf-8', 'utf-16', 'latin-1', 'cp1252']
        content = None
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.readlines()
                break
            except UnicodeDecodeError:
                continue
        
        if content is None:
            print(f"⚠️ 无法读取文件 {file_path}，跳过")
            return []
        
        for line_num, line in enumerate(content):
            original_line = line
            line = line.strip()
            
            # 跳过空行、注释行和节标题
            if not line or line.startswith('#') or line.startswith('[') or line.startswith('//'):
                continue
            
            # 查找等号分割的行
            if '=' in line:
                key, value = line.split('=', 1)
                value = value.strip()
                
                # 跳过空值、文件路径、数字和科学计数法
                if (not value or 
                    value.startswith('C:\\') or 
                    is_number_or_scientific(value) or
                    len(value) < 2):
                    continue
                
                # 跳过带有英文中括号的内容
                if '[' in value and ']' in value:
                    continue
                
                # 只翻译包含字母的文本
                if re.search(r'[a-zA-Z]', value) and not value.startswith('http'):
                    translatable_items.append({
                        'file_path': file_path,
                        'line_num': line_num,
                        'key': key.strip(),
                        'value': value,
                        'original_line': original_line,
                        'type': 'key_value'
                    })
            
            # 处理分号分隔的数据（如CSV格式）
            elif ';' in line:
                parts = line.split(';')
                # 检查所有列，但跳过所有数字
                for col_index, part in enumerate(parts):
                    part = part.strip()
                    
                    # 跳过空值、数字、科学计数法和短文本
                    if (not part or 
                        part == '-' or
                        is_number_or_scientific(part) or
                        len(part) < 2):
                        continue
                    
                    # 跳过带有英文中括号的内容
                    if '[' in part and ']' in part:
                        continue
                    
                    # 只翻译包含字母的文本（排除纯数字）
                    if re.search(r'[a-zA-Z]', part):
                        translatable_items.append({
                            'file_path': file_path,
                            'line_num': line_num,
                            'value': part,
                            'original_line': original_line,
                            'type': 'csv_cell',
                            'column_index': col_index
                        })
            
            # 查找冒号分割的行（没有等号的情况）
            elif ': ' in line:
                parts = line.split(': ', 1)
                if len(parts) == 2:
                    key, value = parts
                    value = value.strip()
                    
                    # 跳过空值、数字和科学计数法
                    if (not value or 
                        is_number_or_scientific(value) or
                        len(value) < 2):
                        continue
                    
                    # 跳过带有英文中括号的内容
                    if '[' in value and ']' in value:
                        continue
                    
                    # 只翻译包含字母的文本
                    if re.search(r'[a-zA-Z]', value):
                        translatable_items.append({
                            'file_path': file_path,
                            'line_num': line_num,
                            'key': key.strip(),
                            'value': value,
                            'original_line': original_line,
                            'type': 'colon_value'
                        })
            
            # 没有等号和冒号的行，直接翻译
            else:
                # 跳过带有英文中括号的内容
                if '[' in line and ']' in line:
                    continue
                
                # 只翻译包含字母且长度合适的文本
                if re.search(r'[a-zA-Z]', line) and len(line) >= 2:
                    translatable_items.append({
                        'file_path': file_path,
                        'line_num': line_num,
                        'value': line,
                        'original_line': original_line,
                        'type': 'full_line'
                    })
    
    except Exception as e:
        print(f"❌ 处理文件 {file_path} 时出错: {e}")
    
    return translatable_items

def translate_texts_in_blocks(texts, max_block_size=3000, max_retries=3):
    """分块翻译文本列表，支持网络错误重试"""
    translated_texts = []
    
    current_block = []
    current_length = 0
    block_count = 0
    
    def translate_block_with_retry(block_text, block_num, retry_count=0):
        """带重试机制的块翻译函数"""
        try:
            translated_block = GoogleTranslator(source='auto', target='zh-CN').translate(block_text)
            return translated_block
        except Exception as e:
            error_msg = str(e).lower()
            # 检查是否为网络相关错误
            if any(keyword in error_msg for keyword in ['network', 'connection', 'timeout', 'ssl', 'handshake', 'keyboardinterrupt']):
                if retry_count < max_retries:
                    wait_time = (retry_count + 1) * 2  # 递增等待时间
                    print(f"⚠️ 第 {block_num} 块网络错误，{wait_time}秒后重试 (第{retry_count + 1}次重试): {e}")
                    time.sleep(wait_time)
                    return translate_block_with_retry(block_text, block_num, retry_count + 1)
                else:
                    print(f"❌ 第 {block_num} 块重试{max_retries}次后仍失败，使用原文: {e}")
                    return None
            else:
                print(f"❌ 第 {block_num} 块翻译失败（非网络错误），使用原文: {e}")
                return None
    
    for i, text in enumerate(texts):
        # 如果加上当前文本会超出限制，先翻译当前块
        if current_length + len(text) > max_block_size and current_block:
            block_count += 1
            progress = (i / len(texts)) * 100
            print(f"🔄 翻译第 {block_count} 块 ({len(current_block)} 个文本, {current_length} 字符) - 进度: {progress:.1f}%")
            
            # 翻译当前块
            block_text = "\n\n".join(current_block)
            translated_block = translate_block_with_retry(block_text, block_count)
            
            if translated_block:
                block_translations = translated_block.strip().split("\n\n")
                
                # 确保翻译结果数量匹配
                while len(block_translations) < len(current_block):
                    block_translations.append(current_block[len(block_translations)])
                
                translated_texts.extend(block_translations[:len(current_block)])
                print(f"✅ 第 {block_count} 块翻译完成")
            else:
                # 翻译失败，使用原文
                translated_texts.extend(current_block)
            
            # 重置当前块
            current_block = []
            current_length = 0
        
        # 添加当前文本到块中
        current_block.append(text)
        current_length += len(text) + 2  # +2 for "\n\n"
    
    # 翻译最后一个块
    if current_block:
        block_count += 1
        print(f"🔄 翻译第 {block_count} 块 ({len(current_block)} 个文本, {current_length} 字符) - 最后一块")
        
        block_text = "\n\n".join(current_block)
        translated_block = translate_block_with_retry(block_text, block_count)
        
        if translated_block:
            block_translations = translated_block.strip().split("\n\n")
            
            while len(block_translations) < len(current_block):
                block_translations.append(current_block[len(block_translations)])
            
            translated_texts.extend(block_translations[:len(current_block)])
            print(f"✅ 第 {block_count} 块翻译完成")
        else:
            # 翻译失败，使用原文
            translated_texts.extend(current_block)
    
    if block_count > 0:
        print(f"🎉 所有 {block_count} 个块翻译完成！")
    
    return translated_texts

def update_file_with_translations(file_path, updates):
    """用翻译结果更新文件"""
    try:
        # 读取原文件
        encodings = ['utf-8', 'utf-16', 'latin-1', 'cp1252']
        content = None
        used_encoding = None
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.readlines()
                used_encoding = encoding
                break
            except UnicodeDecodeError:
                continue
        
        if content is None:
            print(f"❌ 无法读取文件 {file_path}")
            return
        
        # 应用翻译
        for update in updates:
            line_num = update['line_num']
            translated_value = update['translated_value']
            update_type = update['type']
            
            if line_num < len(content):
                if update_type == 'key_value':
                    # 键值对格式
                    key = update['key']
                    new_line = f"{key}={translated_value}\n"
                elif update_type == 'colon_value':
                    # 冒号分割格式
                    key = update['key']
                    new_line = f"{key}: {translated_value}\n"
                elif update_type == 'csv_cell':
                    # CSV格式，需要替换特定列
                    original_line = update['original_line']
                    parts = original_line.strip().split(';')
                    col_index = update['column_index']
                    if col_index < len(parts):
                        parts[col_index] = translated_value
                    new_line = ';'.join(parts) + '\n'
                elif update_type == 'full_line':
                    # 整行翻译
                    new_line = f"{translated_value}\n"
                
                content[line_num] = new_line
        
        # 写入翻译后的文件
        output_file = file_path.replace('.dat', '_translated.dat').replace('.txt', '_translated.txt')
        
        # 强制使用UTF-8编码保存翻译后的文件，避免中文字符编码问题
        with open(output_file, 'w', encoding='utf-8') as f:
            f.writelines(content)
        
        print(f"✅ 已更新文件: {output_file} ({len(updates)} 个翻译项)")
        
    except Exception as e:
        print(f"❌ 更新文件 {file_path} 时出错: {e}")



def process_files_batch(file_pattern=None, max_files=None, start_index=0):
    """分批处理文件"""
    # 获取所有.dat和.txt文件
    if file_pattern:
        dat_files = glob.glob(f"*{file_pattern}*.dat")
        txt_files = glob.glob(f"*{file_pattern}*.txt")
    else:
        dat_files = glob.glob("*.dat")
        txt_files = glob.glob("*.txt")
    
    all_files = dat_files + txt_files
    
    # 排除已翻译的文件
    all_files = [f for f in all_files if not f.endswith('_translated.dat') and not f.endswith('_translated.txt')]
    
    if start_index > 0:
        all_files = all_files[start_index:]
    
    if max_files:
        all_files = all_files[:max_files]
    
    if not all_files:
        print("❌ 未找到任何匹配的.dat或.txt文件")
        return
    
    print(f"📁 找到 {len(all_files)} 个文件待处理")
    
    # 分析每个文件
    files_with_content = []
    files_without_content = []
    
    for file_path in all_files:
        print(f"📖 分析文件: {file_path}")
        items = extract_translatable_content(file_path)
        if items:
            files_with_content.append((file_path, items))
            print(f"   找到 {len(items)} 个待翻译项")
        else:
            files_without_content.append(file_path)
            print(f"   没有找到待翻译项")
    
    print(f"\n📊 统计结果:")
    print(f"   有内容需翻译的文件: {len(files_with_content)} 个")
    print(f"   没有内容需翻译的文件: {len(files_without_content)} 个")
    
    if files_without_content:
        print(f"\n📝 没有翻译内容的文件列表:")
        for file_path in files_without_content:
            print(f"   - {file_path}")
    
    if not files_with_content:
        print("❌ 未找到任何需要翻译的内容")
        return
    
    # 处理有内容的文件
    for file_path, items in files_with_content:
        print(f"\n🔄 开始翻译文件: {file_path} ({len(items)} 个项目)")
        
        # 提取所有需要翻译的文本
        texts_to_translate = [item['value'] for item in items]
        
        # 分块翻译
        translated_texts = translate_texts_in_blocks(texts_to_translate)
        
        # 确保翻译结果数量匹配
        if len(translated_texts) != len(items):
            print("⚠️ 警告：翻译结果数量与原文不符！")
            # 用原文补齐
            while len(translated_texts) < len(items):
                translated_texts.append(items[len(translated_texts)]['value'])
        
        # 准备更新数据
        updates = []
        for i, item in enumerate(items):
            update_item = {
                'line_num': item['line_num'],
                'original_value': item['value'],
                'translated_value': translated_texts[i],
                'original_line': item['original_line'],
                'type': item['type']
            }
            
            if item['type'] in ['key_value', 'colon_value']:
                update_item['key'] = item['key']
            elif item['type'] == 'csv_cell':
                update_item['column_index'] = item['column_index']
                update_item['original_line'] = item['original_line']
            
            updates.append(update_item)
        
        # 更新文件
        update_file_with_translations(file_path, updates)
    
    print(f"\n✅ 批量翻译完成！处理了 {len(files_with_content)} 个文件")

def main():
    parser = argparse.ArgumentParser(description='批量数据文件翻译工具')
    parser.add_argument('--pattern', '-p', help='文件名模式过滤器')
    parser.add_argument('--max-files', '-m', type=int, help='最大处理文件数')
    parser.add_argument('--start-index', '-s', type=int, default=0, help='开始处理的文件索引')
    parser.add_argument('--analyze-only', '-a', action='store_true', help='仅分析文件，不进行翻译')
    
    args = parser.parse_args()
    
    print("🚀 批量数据文件翻译工具")
    print("📋 功能：翻译.dat和.txt文件中的文本内容")
    print("   - 等号后面的内容")
    print("   - 冒号后面的内容")
    print("   - 没有等号和冒号的整行内容")
    print("🚫 跳过：数字、科学计数法、文件路径、带中括号的内容")
    print("-" * 50)
    
    if args.analyze_only:
        print("🔍 仅分析模式：只分析文件，不进行翻译")
        analyze_files_only(args.pattern, args.max_files, args.start_index)
    else:
        process_files_batch(args.pattern, args.max_files, args.start_index)

def analyze_files_only(file_pattern=None, max_files=None, start_index=0):
    """仅分析文件，不进行翻译"""
    # 获取所有.dat和.txt文件
    if file_pattern:
        dat_files = glob.glob(f"*{file_pattern}*.dat")
        txt_files = glob.glob(f"*{file_pattern}*.txt")
    else:
        dat_files = glob.glob("*.dat")
        txt_files = glob.glob("*.txt")
    
    all_files = dat_files + txt_files
    
    # 排除已翻译的文件
    all_files = [f for f in all_files if not f.endswith('_translated.dat') and not f.endswith('_translated.txt')]
    
    if start_index > 0:
        all_files = all_files[start_index:]
    
    if max_files:
        all_files = all_files[:max_files]
    
    if not all_files:
        print("❌ 未找到任何匹配的.dat或.txt文件")
        return
    
    print(f"📁 找到 {len(all_files)} 个文件待分析")
    
    # 分析每个文件
    files_with_content = []
    files_without_content = []
    
    for file_path in all_files:
        print(f"📖 分析文件: {file_path}")
        items = extract_translatable_content(file_path)
        if items:
            files_with_content.append((file_path, items))
            print(f"   找到 {len(items)} 个待翻译项")
        else:
            files_without_content.append(file_path)
            print(f"   没有找到待翻译项")
    
    print(f"\n📊 统计结果:")
    print(f"   有内容需翻译的文件: {len(files_with_content)} 个")
    print(f"   没有内容需翻译的文件: {len(files_without_content)} 个")
    
    if files_without_content:
        print(f"\n📝 没有翻译内容的文件列表:")
        for file_path in files_without_content:
            print(f"   - {file_path}")
    
    if files_with_content:
        print(f"\n📝 有翻译内容的文件列表:")
        total_items = 0
        for file_path, items in files_with_content:
            print(f"   - {file_path} ({len(items)} 项)")
            total_items += len(items)
        print(f"\n📊 总计待翻译项目: {total_items} 个")

if __name__ == "__main__":
    main()