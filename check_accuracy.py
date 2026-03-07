import json
import sqlite3


def load_correct_answers(md_path):
    """Загружаем правильные ответы из markdown файла."""
    correct_files = set()
    
    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    lines = [line for line in lines if line.strip()]
    
    for line in lines:
        line = line.strip()
        parts = line.split('|')
        if len(parts) >= 3:
            count_part = parts[1].strip()
            path_part = '|'.join(parts[2:]).strip()
            
            try:
                count = int(count_part)
            except ValueError:
                continue
            
            if count == 1:
                correct_files.add(path_part)
    
    return correct_files


def load_from_db(db_path):
    """Загружаем распознанные протоколы из SQLite."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT tender_id, doc_path 
        FROM protocol_analysis 
        WHERE doc_path IS NOT NULL
    """)
    
    protocols = cursor.fetchall()
    conn.close()
    
    return {doc_path: tender_id for doc_path, tender_id in protocols}


def check_accuracy(md_path, db_path):
    correct_files = load_correct_answers(md_path)
    protocols = load_from_db(db_path)
    
    correct_count = 0
    incorrect_count = 0
    total_count = len(protocols)
    
    tender_stats = {}
    
    for path, tender_id in protocols.items():
        if path in correct_files:
            correct_count += 1
        else:
            incorrect_count += 1
        
        if tender_id not in tender_stats:
            tender_stats[tender_id] = {'total': 0, 'correct': 0, 'incorrect': 0}
        
        tender_stats[tender_id]['total'] += 1
        if tender_id in correct_files and path in correct_files:
            tender_stats[tender_id]['correct'] += 1
        else:
            tender_stats[tender_id]['incorrect'] += 1
    
    accuracy = (correct_count / total_count * 100) if total_count > 0 else 0.0
    
    result = {
        'total_protocols': total_count,
        'correct_count': correct_count,
        'accuracy_percent': round(accuracy, 2),
        'tenders': tender_stats
    }
    
    return result


if __name__ == '__main__':
    md_file = input("Путь к markdown-файлу с правильными ответами: ")
    db_file = input("Путь к SQLite базе данных: ")
    
    try:
        result = check_accuracy(md_file, db_file)
        print(f"\nИтоговый JSON сохранен в protocol_accuracy.json")
        print(f"Всего протоколов: {result['total_protocols']}")
        print(f"Правильных: {result['correct_count']}")
        print(f"Точность: {result['accuracy_percent']}%")
        
        with open('protocol_accuracy.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка: {e}")
