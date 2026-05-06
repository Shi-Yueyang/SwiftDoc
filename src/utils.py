import chardet

def decode_file(raw_data):
    """Automatically decode file content: prioritize UTF-8, then GB18030, and finally detect encoding with chardet."""
    try:
        return raw_data.decode('utf-8')
    except UnicodeDecodeError:
        pass
    try:
        return raw_data.decode('gb18030')
    except UnicodeDecodeError:
        detected = chardet.detect(raw_data)
        encoding = detected.get('encoding', 'utf-8')
        if encoding and encoding.lower() in ('gb2312', 'gbk', 'gb18030'):
            encoding = 'gb18030'
        return raw_data.decode(encoding, errors='ignore')
    
def get_node_text(node):
    return node.text.decode('utf-8')

def find_identifier(node):
    if node.type == 'identifier':
        return node
    for child in node.children:
        result = find_identifier(child)
        if result:
            return result
    return None
