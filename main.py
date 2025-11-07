from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import json
from urllib.parse import quote, parse_qs, urlparse
from datetime import datetime, timedelta
import re
import logging
import mysql.connector
from mysql.connector import Error
import os



# デバッグフラグ（Trueにすると処理を選択できる）
DEBUG_FLG = False

# データベース設定
DB_CONFIG = {
    'host': 'akioka.cloud',
    'database': 'akioka_db',
    'user': 'akioka_administrator',
    'password': 'Akiokapass0',  # パスワードを設定してください
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci'
}

# ログファイルのパス
LOG_FILE = 'log.txt'

# 実行状態管理ファイル
STATE_FILE = 'sync_state.json'


def get_db_connection():
    """MySQLデータベースへの接続を取得"""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as e:
        print(f'データベース接続エラー: {e}')
        return None


def init_database():
    """データベースとテーブルを初期化"""
    try:
        connection = get_db_connection()
        if not connection:
            return False
        
        cursor = connection.cursor()
        
        # テーブル作成
        # 施設マスタテーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS facilities (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # 予定テーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedule_events (
                id INT AUTO_INCREMENT PRIMARY KEY,
                facility_id INT NOT NULL,
                date DATE NOT NULL,
                title VARCHAR(500) NOT NULL,
                start_datetime VARCHAR(10) NOT NULL,
                end_datetime VARCHAR(10) NOT NULL,
                badge VARCHAR(100),
                description_url TEXT,
                EID INT,
                status TINYINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY unique_event (facility_id, date, EID),
                FOREIGN KEY (facility_id) REFERENCES facilities(id) ON DELETE CASCADE,
                INDEX idx_facility_date (facility_id, date),
                INDEX idx_date (date),
                INDEX idx_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # 参加者テーブル（Laravelマイグレーションを使用する場合は、この関数は使用されません）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedule_participants (
                id INT AUTO_INCREMENT PRIMARY KEY,
                schedule_event_id INT NOT NULL,
                user_id INT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (schedule_event_id) REFERENCES schedule_events(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE KEY unique_participant (schedule_event_id, user_id),
                INDEX idx_event (schedule_event_id),
                INDEX idx_user (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # ユーザー予定テーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_schedules (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                date DATE NOT NULL,
                title VARCHAR(500) NOT NULL,
                start_datetime VARCHAR(10) NOT NULL,
                end_datetime VARCHAR(10) NOT NULL,
                badge VARCHAR(100),
                description_url TEXT,
                EID INT,
                status TINYINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY unique_user_event (user_id, date, EID),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user_date (user_id, date),
                INDEX idx_date (date),
                INDEX idx_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # 既存テーブルにEIDカラムを追加し、UNIQUE制約を変更
        try:
            # schedule_events テーブル
            cursor.execute("ALTER TABLE schedule_events ADD COLUMN IF NOT EXISTS EID INT")
        except Error:
            pass  # カラムが既に存在する場合は無視
        
        try:
            # 古いUNIQUE制約を削除
            cursor.execute("ALTER TABLE schedule_events DROP INDEX unique_event")
        except Error:
            pass  # 制約が既に削除されている場合は無視
        
        try:
            # 新しいUNIQUE制約を追加
            cursor.execute("ALTER TABLE schedule_events ADD UNIQUE KEY unique_event (facility_id, date, EID)")
        except Error:
            pass  # 制約が既に存在する場合は無視
        
        try:
            # user_schedules テーブル
            cursor.execute("ALTER TABLE user_schedules ADD COLUMN IF NOT EXISTS EID INT")
        except Error:
            pass  # カラムが既に存在する場合は無視
        
        try:
            # 古いUNIQUE制約を削除
            cursor.execute("ALTER TABLE user_schedules DROP INDEX unique_user_event")
        except Error:
            pass  # 制約が既に削除されている場合は無視
        
        try:
            # 新しいUNIQUE制約を追加
            cursor.execute("ALTER TABLE user_schedules ADD UNIQUE KEY unique_user_event (user_id, date, EID)")
        except Error:
            pass  # 制約が既に存在する場合は無視
        
        # statusカラムを追加（存在しない場合）
        try:
            cursor.execute("ALTER TABLE schedule_events ADD COLUMN IF NOT EXISTS status TINYINT DEFAULT 0")
            cursor.execute("ALTER TABLE schedule_events ADD INDEX IF NOT EXISTS idx_status (status)")
        except Error:
            pass  # カラムが既に存在する場合は無視
        
        try:
            cursor.execute("ALTER TABLE user_schedules ADD COLUMN IF NOT EXISTS status TINYINT DEFAULT 0")
            cursor.execute("ALTER TABLE user_schedules ADD INDEX IF NOT EXISTS idx_status (status)")
        except Error:
            pass  # カラムが既に存在する場合は無視
        
        connection.commit()
        cursor.close()
        connection.close()
        
        return True
    except Error as e:
        print(f'データベース初期化エラー: {e}')
        return False


def get_facility_id(connection, facility_name):
    """施設IDを取得（存在しない場合は作成）"""
    cursor = connection.cursor()
    
    # 施設を検索
    cursor.execute("SELECT id FROM facilities WHERE name = %s", (facility_name,))
    result = cursor.fetchone()
    
    if result:
        facility_id = result[0]
    else:
        # 施設を新規作成
        cursor.execute("INSERT INTO facilities (name, created_at, updated_at) VALUES (%s, NOW(), NOW())", (facility_name,))
        connection.commit()
        facility_id = cursor.lastrowid
    
    cursor.close()
    return facility_id


def get_user_id_by_name(connection, user_name):
    """ユーザー名からユーザーIDを取得（存在しない場合はNone）"""
    cursor = connection.cursor()
    
    # ユーザーを検索（nameカラムで検索）
    cursor.execute("SELECT id FROM users WHERE name = %s", (user_name,))
    result = cursor.fetchone()
    
    user_id = result[0] if result else None
    cursor.close()
    return user_id


def load_schedule_from_db(connection):
    """データベースからスケジュールデータを読み込む（JSON形式に変換）"""
    schedule_data = {}
    
    try:
        cursor = connection.cursor(dictionary=True)
        
        # 施設ごとにデータを取得
        cursor.execute("""
            SELECT 
                f.name as facility_name,
                DATE_FORMAT(se.date, '%Y-%m-%d') as date,
                se.id,
                se.title,
                se.start_datetime,
                se.end_datetime,
                se.badge,
                se.description_url
            FROM schedule_events se
            JOIN facilities f ON se.facility_id = f.id
            ORDER BY f.name, se.date, se.start_datetime
        """)
        
        events = cursor.fetchall()
        
        # 参加者情報を取得（user_idからユーザー名を取得）
        cursor.execute("""
            SELECT 
                se.id as event_id,
                GROUP_CONCAT(u.name ORDER BY u.name SEPARATOR ',') as participants
            FROM schedule_events se
            LEFT JOIN schedule_participants sp ON se.id = sp.schedule_event_id
            LEFT JOIN users u ON sp.user_id = u.id
            GROUP BY se.id
        """)
        
        participants_map = {}
        for row in cursor.fetchall():
            event_id = row['event_id']
            participants = row['participants']
            if participants:
                participants_map[event_id] = participants.split(',')
            else:
                participants_map[event_id] = []
        
        # データを構造化
        for event in events:
            facility = event['facility_name']
            date = event['date']
            
            if facility not in schedule_data:
                schedule_data[facility] = {}
            if date not in schedule_data[facility]:
                schedule_data[facility][date] = []
            
            event_data = {
                'id': event['id'],
                'title': event['title'],
                'start_datetime': event['start_datetime'],
                'end_datetime': event['end_datetime'],
                'badge': event['badge'],
                'description_url': event['description_url'],
                'participants': participants_map.get(event['id'], [])
            }
            
            schedule_data[facility][date].append(event_data)
        
        cursor.close()
        
    except Error as e:
        print(f'データベース読み込みエラー: {e}')
    
    return schedule_data


def write_log(message, log_file=LOG_FILE):
    """ログファイルにメッセージを書き込む"""
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(message + '\n')
    except Exception as e:
        print(f'ログ書き込みエラー: {e}')


def load_sync_state():
    """同期状態をJSONファイルから読み込む"""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f'状態ファイル読み込みエラー: {e}')
        return {}


def save_sync_state(state):
    """同期状態をJSONファイルに保存"""
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'状態ファイル保存エラー: {e}')


def should_run_full_sync(current_time, state):
    """1ヶ月分の同期を実行すべきかを判定
    
    Args:
        current_time: 現在時刻
        state: 同期状態辞書
    
    Returns:
        bool: 1ヶ月分の同期を実行すべきならTrue
    """
    current_hour = current_time.hour
    
    # 0:00台または12:00台でない場合は実行しない
    if current_hour != 0 and current_hour != 12:
        return False
    
    # 前回の1ヶ月分同期時刻を取得
    last_full_sync = state.get('last_full_sync')
    
    if not last_full_sync:
        # 初回実行
        return True
    
    try:
        last_sync_time = datetime.strptime(last_full_sync, '%Y-%m-%d %H:%M:%S')
        time_diff = (current_time - last_sync_time).total_seconds()
        
        # 1時間（3600秒）以上経過している場合のみ実行
        return time_diff >= 3600
    except Exception as e:
        print(f'前回実行時刻の解析エラー: {e}')
        return True  # エラーの場合は実行する


def setup_logging():
    """ログの設定"""
    # ロガーの設定
    logger = logging.getLogger('schedule_sync')
    logger.setLevel(logging.INFO)
    
    # 既存のハンドラをクリア（重複防止）
    if logger.handlers:
        logger.handlers.clear()
    
    # コンソールハンドラのみ（ファイルへの書き込みは別途行う）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # フォーマット設定
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    
    # ハンドラを追加
    logger.addHandler(console_handler)
    
    return logger


def extract_date_from_url(url):
    """URLから日付を抽出する関数
    例: Date=da.2025.11.5 -> 2025-11-05
    """
    try:
        # URLからDateパラメータを抽出
        match = re.search(r'Date=da\.(\d+)\.(\d+)\.(\d+)', url)
        if match:
            year = match.group(1)
            month = match.group(2).zfill(2)  # 1桁の月を2桁にゼロパディング
            day = match.group(3).zfill(2)    # 1桁の日を2桁にゼロパディング
            return f"{year}-{month}-{day}"
        return None
    except Exception as e:
        print(f'日付抽出エラー: {e}')
        return None


def extract_id_from_title(title):
    """タイトルから[id]を抽出する関数
    例: [123]会議 -> 123
    """
    try:
        match = re.match(r'^\[(\d+)\]', title)
        if match:
            return int(match.group(1))
        return None
    except Exception as e:
        return None


def extract_eid_from_url(url):
    """URLからsEID（イベントID）を抽出する関数
    例: sEID=139027 -> 139027
    """
    try:
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        if 'sEID' in query_params:
            return int(query_params['sEID'][0])
        return None
    except Exception as e:
        return None


def login(driver):
    # 指定したURLにアクセス
    url = 'https://9w4c9.cybozu.com/'
    driver.get(url)

    # username-:0-textというIDが付与されたinputにto-murakamiと入力
    input_element = driver.find_element(By.ID, 'username-:0-text')
    input_element.send_keys('to-murakami')

    # password-:1-textというIDが付与されたinput要素にto-murakami@akioka55と入力
    password_element = driver.find_element(By.ID, 'password-:1-text')
    password_element.send_keys('to-murakami@akioka55')

    # login-buttonというクラスが付与された要素をクリック
    login_button = driver.find_element(By.CLASS_NAME, 'login-button')
    login_button.click()

    time.sleep(1)
    
    # c-index-Services-ServiceItemが付与されたクラスの配下にあるa要素をクリック
    service_item = driver.find_element(By.CLASS_NAME, 'c-index-Services-ServiceItem')
    link = service_item.find_element(By.TAG_NAME, 'a')
    link.click()
    
    time.sleep(1)



def get_place_schedule(driver, search_term, target_date, connection, logger=None, counters=None, log_messages=None, changed_event_ids=None):
    """施設のスケジュールを取得
    
    Args:
        changed_event_ids: 新規追加・更新されたイベントIDを記録するセット（オプション）
    """
    try:
        # 日付を文字列に変換
        date_str = f"da.{target_date.year}.{target_date.month}.{target_date.day}"
        date_key = target_date.strftime('%Y-%m-%d')
        
        # 施設名をURLエンコード
        encoded_text = quote(search_term)
        
        # URLを構築
        url = f"https://9w4c9.cybozu.com/o/ag.cgi?page=ScheduleIndex&CP=&uid=796&gid=virtual&date={date_str}&Text={encoded_text}"
        
        message = f'施設「{search_term}」の{date_key}のスケジュールにアクセス中...'
        if logger:
            logger.info(message)
        else:
            print(message)
        
        # URLに直接アクセス
        driver.get(url)
        time.sleep(1)

        # スケジュール要素を取得
        try:
            element = driver.find_element(By.ID, 'tblgroupweek')
        except Exception as e:
            print(f'スケジュール要素の取得に失敗しました: {e}')
            return None
        
        try:
            # eventcellクラスが付与されたすべてのエレメントを取得（週の全日分）
            eventcells = element.find_elements(By.CLASS_NAME, 'eventcell')
            
            # 日付ごとにイベントを格納する辞書
            events_by_date = {}
            
            # 各eventcellからイベントを取得
            for eventcell in eventcells:
                # eventInnerクラスが付与された全てのエレメントを取得
                event_inner_elements = eventcell.find_elements(By.CLASS_NAME, 'eventInner')
                
                # 各event_inner_elementからeventDateTimeとeventクラスの要素を取得
                for event_inner in event_inner_elements:
                    try:
                        # 要素を都度取得し直す
                        event_date_time = event_inner.find_element(By.CLASS_NAME, 'eventDateTime')
                        event_content = event_inner.find_element(By.CLASS_NAME, 'event')

                        # hrefの値を取得
                        href = event_content.get_attribute('href')
                        
                        # URLから実際の日付を抽出
                        event_date = extract_date_from_url(href)
                        if not event_date:
                            print(f'  警告: URLから日付を抽出できませんでした: {href}')
                            continue
                        
                        # URLからEID（イベントID）を抽出
                        eid = extract_eid_from_url(href)
                        
                        # 時刻を分割して格納
                        time_parts = event_date_time.text.split('-')
                        start_datetime = ""
                        finish_datetime = ""
                        if len(time_parts) >= 2:
                            start_datetime = time_parts[0].strip()
                            finish_datetime = time_parts[1].strip()

                        # タイトルを:で分割
                        title_parts = event_content.get_attribute('title').split(':')
                        if len(title_parts) > 1:
                            badge = title_parts[0].strip()
                            title = title_parts[1].strip()
                        else:
                            badge = ""
                            title = title_parts[0].strip()

                        # イベントデータを辞書として追加
                        event_data = {
                            "title": title,
                            "start_datetime": start_datetime,
                            "end_datetime": finish_datetime,
                            "badge": badge,
                            "description_url": href,
                            "eid": eid
                        }
                        
                        # 日付ごとにイベントを格納
                        if event_date not in events_by_date:
                            events_by_date[event_date] = []
                        events_by_date[event_date].append(event_data)

                    except Exception as e:
                        print(f'  イベント情報の処理中にエラーが発生しました: {e}')
                        continue
            
            # データベースから既存データを読み込む
            schedule_data = load_schedule_from_db(connection)
            
            # 施設IDを取得
            facility_id = get_facility_id(connection, search_term)
            cursor = connection.cursor()
            
            # 日付ごとにイベントを同期（追加・更新・削除）
            for event_date, event_list in events_by_date.items():
                # 既存のイベントを取得（この施設・この日付）
                cursor.execute("""
                    SELECT id, title, start_datetime, end_datetime, badge, description_url, EID
                    FROM schedule_events
                    WHERE facility_id = %s AND date = %s
                """, (facility_id, event_date))
                
                existing_events = cursor.fetchall()
                
                # 既存イベントをDBのidとEIDと内容で索引化
                existing_events_by_db_id = {}
                existing_events_by_eid = {}  # EIDで索引化
                existing_events_by_content = {}  # 日付+時刻+タイトルで照合（EIDなしの場合用）
                
                for row in existing_events:
                    event_info = {
                        'id': row[0],
                        'title': row[1],
                        'start_datetime': row[2],
                        'end_datetime': row[3],
                        'badge': row[4],
                        'description_url': row[5],
                        'eid': row[6]
                    }
                    existing_events_by_db_id[row[0]] = event_info
                    
                    # EIDで索引化（EIDがある場合）
                    if row[6] is not None:
                        existing_events_by_eid[row[6]] = event_info
                    
                    # 内容ベースのキー（EIDなしの場合用）
                    content_key = f"{row[2]}|{row[3]}|{row[1]}"  # start|end|title
                    existing_events_by_content[content_key] = event_info
                
                # 処理済みのDBイベントIDセット
                processed_db_ids = set()
                
                # 新しいデータを同期（追加・更新）
                for new_event in event_list:
                    event_eid = new_event.get('eid')
                    
                    # タイトルから[id]を抽出してDB上のイベントIDを取得
                    db_event_id = extract_id_from_title(new_event['title'])
                    
                    existing_event = None
                    
                    # まずDB IDで照合（システムから登録されたイベント）
                    if db_event_id and db_event_id in existing_events_by_db_id:
                        existing_event = existing_events_by_db_id[db_event_id]
                        processed_db_ids.add(db_event_id)
                    # 次にEIDで照合（EIDがある場合）
                    elif event_eid and event_eid in existing_events_by_eid:
                        existing_event = existing_events_by_eid[event_eid]
                        processed_db_ids.add(existing_event['id'])
                    # 最後に内容で照合（EIDがない場合）
                    else:
                        content_key = f"{new_event['start_datetime']}|{new_event['end_datetime']}|{new_event['title']}"
                        if content_key in existing_events_by_content:
                            existing_event = existing_events_by_content[content_key]
                            processed_db_ids.add(existing_event['id'])
                    
                    # 既存のイベントを検索
                    if existing_event:
                        
                        # 変更を検知（title, start_datetime, end_datetime, badgeを比較）
                        has_changes = (
                            existing_event['title'] != new_event['title'] or
                            existing_event['start_datetime'] != new_event['start_datetime'] or
                            existing_event['end_datetime'] != new_event['end_datetime'] or
                            existing_event['badge'] != new_event['badge']
                        )
                        
                        if has_changes:
                            # 変更内容の詳細
                            changes = []
                            if existing_event['title'] != new_event['title']:
                                changes.append(f"タイトル: {existing_event['title']} → {new_event['title']}")
                            if existing_event['start_datetime'] != new_event['start_datetime']:
                                changes.append(f"開始: {existing_event['start_datetime']} → {new_event['start_datetime']}")
                            if existing_event['end_datetime'] != new_event['end_datetime']:
                                changes.append(f"終了: {existing_event['end_datetime']} → {new_event['end_datetime']}")
                            if existing_event['badge'] != new_event['badge']:
                                changes.append(f"バッジ: {existing_event['badge']} → {new_event['badge']}")
                            
                            # データベースを更新
                            cursor.execute("""
                                UPDATE schedule_events
                                SET title = %s, start_datetime = %s, end_datetime = %s, badge = %s, description_url = %s, EID = %s, updated_at = NOW()
                                WHERE id = %s
                            """, (
                                new_event['title'],
                                new_event['start_datetime'],
                                new_event['end_datetime'],
                                new_event['badge'],
                                new_event['description_url'],
                                new_event.get('eid'),
                                existing_event['id']
                            ))
                            connection.commit()
                            
                            message = f'[更新] {event_date}: {new_event["title"]} - {", ".join(changes)}'
                            if logger:
                                logger.info(message)
                            else:
                                print(message)
                            
                            # 統計とログに追加
                            if counters:
                                counters['facility_update'] += 1
                            if log_messages is not None:
                                log_messages.append(f'  [更新] 施設:{search_term} | {event_date} {new_event["start_datetime"]}-{new_event["end_datetime"]} | {new_event["title"]}')
                            # 変更されたイベントIDを記録
                            if changed_event_ids is not None:
                                changed_event_ids.add(existing_event['id'])
                        else:
                            # 変更なし
                            message = f'[変更なし] {event_date}: {new_event["title"]}'
                            if logger:
                                logger.debug(message)
                    else:
                        # 新規追加
                        cursor.execute("""
                            INSERT INTO schedule_events 
                            (facility_id, date, title, start_datetime, end_datetime, badge, description_url, EID, status, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, NOW(), NOW())
                        """, (
                            facility_id,
                            event_date,
                            new_event['title'],
                            new_event['start_datetime'],
                            new_event['end_datetime'],
                            new_event['badge'],
                            new_event['description_url'],
                            new_event.get('eid')
                        ))
                        connection.commit()
                        new_event_id = cursor.lastrowid
                        
                        message = f'[追加] {event_date}: {new_event["title"]} (ID: {new_event_id}, {new_event["start_datetime"]}-{new_event["end_datetime"]}, {new_event["badge"]})'
                        if logger:
                            logger.info(message)
                        else:
                            print(message)
                        
                        # 統計とログに追加
                        if counters:
                            counters['facility_add'] += 1
                        if log_messages is not None:
                            log_messages.append(f'  [追加] 施設:{search_term} | {event_date} {new_event["start_datetime"]}-{new_event["end_datetime"]} | {new_event["title"]}')
                        # 新規追加されたイベントIDを記録
                        if changed_event_ids is not None:
                            changed_event_ids.add(new_event_id)
                
                # 削除されたイベントを検出して削除
                for existing_event in existing_events:
                    event_id = existing_event[0]
                    event_title = existing_event[1]
                    event_url = existing_event[5]  # description_url
                    
                    # 処理済みでないイベントを削除
                    if event_id not in processed_db_ids:
                        # 参加者も削除（CASCADEで自動削除されるが、ログ用）
                        cursor.execute("DELETE FROM schedule_events WHERE id = %s", (event_id,))
                        connection.commit()
                        
                        message = f'[削除] {event_date}: {event_title} (ID: {event_id}) - Cybozuから削除されました'
                        if logger:
                            logger.warning(message)
                        else:
                            print(message)
                        
                        # 統計とログに追加
                        if counters:
                            counters['facility_delete'] += 1
                        if log_messages is not None:
                            log_messages.append(f'  [削除] 施設:{search_term} | {event_date} | {event_title}')
            
            cursor.close()
            
            
        except Exception as e:
            print(f'イベント要素の取得に失敗しました: {e}')
            return None


    except Exception as e:
        print(f'予期せぬエラーが発生しました: {e}')
        return None


def get_user_schedule(driver, user_name, user_id, target_date, connection, logger=None, counters=None, log_messages=None):
    """ユーザー個人のスケジュールを取得"""
    try:
        # 日付を文字列に変換
        date_str = f"da.{target_date.year}.{target_date.month}.{target_date.day}"
        date_key = target_date.strftime('%Y-%m-%d')
        
        # ユーザー名をURLエンコード
        encoded_text = quote(user_name)
        
        # URLを構築
        url = f"https://9w4c9.cybozu.com/o/ag.cgi?page=ScheduleIndex&CP=&uid=796&gid=virtual&date={date_str}&Text={encoded_text}"
        
        message = f'ユーザー「{user_name}」の{date_key}のスケジュールにアクセス中...'
        if logger:
            logger.info(message)
        else:
            print(message)
        
        # URLに直接アクセス
        driver.get(url)
        time.sleep(1)

        # スケジュール要素を取得
        try:
            element = driver.find_element(By.ID, 'tblgroupweek')
        except Exception as e:
            print(f'スケジュール要素の取得に失敗しました: {e}')
            return None
        
        try:
            # eventcellクラスが付与されたすべてのエレメントを取得（週の全日分）
            eventcells = element.find_elements(By.CLASS_NAME, 'eventcell')
            
            # 日付ごとにイベントを格納する辞書
            events_by_date = {}
            
            # 各eventcellからイベントを取得
            for eventcell in eventcells:
                # eventInnerクラスが付与された全てのエレメントを取得
                event_inner_elements = eventcell.find_elements(By.CLASS_NAME, 'eventInner')
                
                # 各event_inner_elementからeventDateTimeとeventクラスの要素を取得
                for event_inner in event_inner_elements:
                    try:
                        # eventDateTimeの存在確認（時刻指定がない予定はスキップ）
                        event_date_time_elements = event_inner.find_elements(By.CLASS_NAME, 'eventDateTime')
                        if not event_date_time_elements:
                            # 時刻指定がない予定（終日予定など）はユーザー予定として登録しない
                            if logger:
                                logger.debug(f'  時刻指定なしの予定をスキップしました')
                            continue
                        
                        event_date_time = event_date_time_elements[0]
                        event_content = event_inner.find_element(By.CLASS_NAME, 'event')

                        # hrefの値を取得
                        href = event_content.get_attribute('href')
                        
                        # URLから実際の日付を抽出
                        event_date = extract_date_from_url(href)
                        if not event_date:
                            print(f'  警告: URLから日付を抽出できませんでした: {href}')
                            continue
                        
                        # URLからEID（イベントID）を抽出
                        eid = extract_eid_from_url(href)
                        
                        # 時刻を分割して格納
                        time_parts = event_date_time.text.split('-')
                        start_datetime = ""
                        finish_datetime = ""
                        if len(time_parts) >= 2:
                            start_datetime = time_parts[0].strip()
                            finish_datetime = time_parts[1].strip()
                        else:
                            # 時刻フォーマットが不正な場合もスキップ
                            if logger:
                                logger.debug(f'  時刻フォーマット不正の予定をスキップしました: {event_date_time.text}')
                            continue

                        # タイトルを:で分割
                        title_parts = event_content.get_attribute('title').split(':')
                        if len(title_parts) > 1:
                            badge = title_parts[0].strip()
                            title = title_parts[1].strip()
                        else:
                            badge = ""
                            title = title_parts[0].strip()

                        # イベントデータを辞書として追加
                        event_data = {
                            "title": title,
                            "start_datetime": start_datetime,
                            "end_datetime": finish_datetime,
                            "badge": badge,
                            "description_url": href,
                            "eid": eid
                        }
                        
                        # 日付ごとにイベントを格納
                        if event_date not in events_by_date:
                            events_by_date[event_date] = []
                        events_by_date[event_date].append(event_data)

                    except Exception as e:
                        print(f'  イベント情報の処理中にエラーが発生しました: {e}')
                        continue
            
            cursor = connection.cursor()
            
            # 日付ごとにイベントを同期（追加・更新・削除）
            for event_date, event_list in events_by_date.items():
                # 既存のイベントを取得（このユーザー・この日付）
                cursor.execute("""
                    SELECT id, title, start_datetime, end_datetime, badge, description_url, EID
                    FROM user_schedules
                    WHERE user_id = %s AND date = %s
                """, (user_id, event_date))
                
                existing_events = cursor.fetchall()
                
                # 既存イベントをDBのidとEIDと内容で索引化
                existing_events_by_db_id = {}
                existing_events_by_eid = {}  # EIDで索引化
                existing_events_by_content = {}  # 日付+時刻+タイトルで照合（EIDなしの場合用）
                
                for row in existing_events:
                    event_info = {
                        'id': row[0],
                        'title': row[1],
                        'start_datetime': row[2],
                        'end_datetime': row[3],
                        'badge': row[4],
                        'description_url': row[5],
                        'eid': row[6]
                    }
                    existing_events_by_db_id[row[0]] = event_info
                    
                    # EIDで索引化（EIDがある場合）
                    if row[6] is not None:
                        existing_events_by_eid[row[6]] = event_info
                    
                    # 内容ベースのキー（EIDなしの場合用）
                    content_key = f"{row[2]}|{row[3]}|{row[1]}"  # start|end|title
                    existing_events_by_content[content_key] = event_info
                
                # 処理済みのDBイベントIDセット
                processed_db_ids = set()
                
                # 新しいデータを同期（追加・更新）
                for new_event in event_list:
                    event_eid = new_event.get('eid')
                    
                    # タイトルから[id]を抽出してDB上のイベントIDを取得
                    db_event_id = extract_id_from_title(new_event['title'])
                    
                    existing_event = None
                    
                    # まずDB IDで照合（システムから登録されたイベント）
                    if db_event_id and db_event_id in existing_events_by_db_id:
                        existing_event = existing_events_by_db_id[db_event_id]
                        processed_db_ids.add(db_event_id)
                    # 次にEIDで照合（EIDがある場合）
                    elif event_eid and event_eid in existing_events_by_eid:
                        existing_event = existing_events_by_eid[event_eid]
                        processed_db_ids.add(existing_event['id'])
                    # 最後に内容で照合（EIDがない場合）
                    else:
                        content_key = f"{new_event['start_datetime']}|{new_event['end_datetime']}|{new_event['title']}"
                        if content_key in existing_events_by_content:
                            existing_event = existing_events_by_content[content_key]
                            processed_db_ids.add(existing_event['id'])
                    
                    # 既存のイベントを検索
                    if existing_event:
                        
                        # 変更を検知（title, start_datetime, end_datetime, badgeを比較）
                        has_changes = (
                            existing_event['title'] != new_event['title'] or
                            existing_event['start_datetime'] != new_event['start_datetime'] or
                            existing_event['end_datetime'] != new_event['end_datetime'] or
                            existing_event['badge'] != new_event['badge']
                        )
                        
                        if has_changes:
                            # 変更内容の詳細
                            changes = []
                            if existing_event['title'] != new_event['title']:
                                changes.append(f"タイトル: {existing_event['title']} → {new_event['title']}")
                            if existing_event['start_datetime'] != new_event['start_datetime']:
                                changes.append(f"開始: {existing_event['start_datetime']} → {new_event['start_datetime']}")
                            if existing_event['end_datetime'] != new_event['end_datetime']:
                                changes.append(f"終了: {existing_event['end_datetime']} → {new_event['end_datetime']}")
                            if existing_event['badge'] != new_event['badge']:
                                changes.append(f"バッジ: {existing_event['badge']} → {new_event['badge']}")
                            
                            # データベースを更新
                            cursor.execute("""
                                UPDATE user_schedules
                                SET title = %s, start_datetime = %s, end_datetime = %s, badge = %s, description_url = %s, EID = %s, updated_at = NOW()
                                WHERE id = %s
                            """, (
                                new_event['title'],
                                new_event['start_datetime'],
                                new_event['end_datetime'],
                                new_event['badge'],
                                new_event['description_url'],
                                new_event.get('eid'),
                                existing_event['id']
                            ))
                            connection.commit()
                            
                            message = f'[更新] {event_date}: {new_event["title"]} - {", ".join(changes)}'
                            if logger:
                                logger.info(message)
                            else:
                                print(message)
                            
                            # 統計とログに追加
                            if counters:
                                counters['user_update'] += 1
                            if log_messages is not None:
                                log_messages.append(f'  [更新] ユーザー:{user_name} | {event_date} {new_event["start_datetime"]}-{new_event["end_datetime"]} | {new_event["title"]}')
                        else:
                            # 変更なし
                            message = f'[変更なし] {event_date}: {new_event["title"]}'
                            if logger:
                                logger.debug(message)
                    else:
                        # 新規追加
                        cursor.execute("""
                            INSERT INTO user_schedules 
                            (user_id, date, title, start_datetime, end_datetime, badge, description_url, EID, status, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, NOW(), NOW())
                        """, (
                            user_id,
                            event_date,
                            new_event['title'],
                            new_event['start_datetime'],
                            new_event['end_datetime'],
                            new_event['badge'],
                            new_event['description_url'],
                            new_event.get('eid')
                        ))
                        connection.commit()
                        new_event_id = cursor.lastrowid
                        
                        message = f'[追加] {event_date}: {new_event["title"]} (ID: {new_event_id}, {new_event["start_datetime"]}-{new_event["end_datetime"]}, {new_event["badge"]})'
                        if logger:
                            logger.info(message)
                        else:
                            print(message)
                        
                        # 統計とログに追加
                        if counters:
                            counters['user_add'] += 1
                        if log_messages is not None:
                            log_messages.append(f'  [追加] ユーザー:{user_name} | {event_date} {new_event["start_datetime"]}-{new_event["end_datetime"]} | {new_event["title"]}')
                
                # 削除されたイベントを検出して削除
                for existing_event in existing_events:
                    event_id = existing_event[0]
                    event_title = existing_event[1]
                    event_url = existing_event[5]  # description_url
                    
                    # 処理済みでないイベントを削除
                    if event_id not in processed_db_ids:
                        cursor.execute("DELETE FROM user_schedules WHERE id = %s", (event_id,))
                        connection.commit()
                        
                        message = f'[削除] {event_date}: {event_title} (ID: {event_id}) - Cybozuから削除されました'
                        if logger:
                            logger.warning(message)
                        else:
                            print(message)
                        
                        # 統計とログに追加
                        if counters:
                            counters['user_delete'] += 1
                        if log_messages is not None:
                            log_messages.append(f'  [削除] ユーザー:{user_name} | {event_date} | {event_title}')
            
            cursor.close()
            
        except Exception as e:
            print(f'イベント要素の取得に失敗しました: {e}')
            return None

    except Exception as e:
        print(f'予期せぬエラーが発生しました: {e}')
        return None


def main():
    # 開始時刻を記録
    start_time = datetime.now()
    
    # ログの設定
    logger = setup_logging()
    logger.info('=' * 60)
    logger.info('スケジュール同期処理を開始します')
    logger.info('=' * 60)
    
    # ログメッセージを格納するリスト
    log_messages = []
    log_messages.append('=' * 80)
    log_messages.append(f'■ 実行開始: {start_time.strftime("%Y-%m-%d %H:%M:%S")}')
    
    # デバッグモード: 処理内容を選択
    process_facilities = True  # 会議室予定を処理するか
    process_users = True       # ユーザー予定を処理するか
    
    if DEBUG_FLG:
        print('')
        print('=' * 60)
        print('デバッグモード: 処理内容を選択してください')
        print('=' * 60)
        print('1. 会議室予定のみ取得・登録')
        print('2. ユーザー予定のみ取得・登録')
        print('3. 両方取得・登録')
        print('=' * 60)
        
        while True:
            choice = input('選択してください (1/2/3): ').strip()
            if choice == '1':
                process_facilities = True
                process_users = False
                logger.info('デバッグモード: 会議室予定のみを処理します')
                break
            elif choice == '2':
                process_facilities = False
                process_users = True
                logger.info('デバッグモード: ユーザー予定のみを処理します')
                break
            elif choice == '3':
                process_facilities = True
                process_users = True
                logger.info('デバッグモード: 両方を処理します')
                break
            else:
                print('無効な選択です。1、2、または3を入力してください。')
        
        print('')
    
    # データベース接続
    logger.info('データベースに接続中...')
    connection = get_db_connection()
    if not connection:
        logger.error('データベース接続に失敗しました。処理を終了します。')
        return
    
    logger.info('データベース接続成功')
    
    # データベース初期化
    logger.info('データベースを初期化中...')
    if not init_database():
        logger.error('データベース初期化に失敗しました。処理を終了します。')
        connection.close()
        return
    logger.info('データベース初期化完了')
    
    # Chromeブラウザのオプションを設定
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')

    # Chromeブラウザのドライバーを設定
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    # ログイン処理
    logger.info('Cybozuにログイン中...')
    login(driver)
    logger.info('ログイン成功')

    # 同期状態を読み込み
    sync_state = load_sync_state()
    
    # 現在時刻に基づいて取得期間を決定
    # 0:00台または12:00台で、前回から1時間以上経過している場合は1ヶ月分
    # それ以外は1週間分
    run_full_sync = should_run_full_sync(start_time, sync_state)
    
    if run_full_sync:
        weeks_count = 5  # 5週間分（約1ヶ月）
        date_range_text = '1ヶ月分（5週間）'
        logger.info(f'>>> 定期実行時刻（{start_time.hour}:00台）のため、1ヶ月分のデータを取得します。')
        # 実行時刻を記録
        sync_state['last_full_sync'] = start_time.strftime('%Y-%m-%d %H:%M:%S')
        save_sync_state(sync_state)
    else:
        weeks_count = 1  # 1週間分
        date_range_text = '1週間分'
        current_hour = start_time.hour
        if current_hour == 0 or current_hour == 12:
            last_full = sync_state.get('last_full_sync', '未実行')
            logger.info(f'>>> 定期実行時刻ですが、前回実行済み（{last_full}）のため、1週間分のデータを取得します。')
        else:
            logger.info(f'>>> 通常実行のため、1週間分のデータを取得します。')
    
    log_messages.append(f'■ 取得期間: {date_range_text}')
    
    # 現在の日付から週のリストを生成（7日おき）
    # Cybozuは週表示なので、7日おきにアクセスすれば全期間をカバーできる
    start_date = start_time
    date_list = [start_date + timedelta(days=x*7) for x in range(weeks_count)]
    
    participant_count = 0
    
    # 処理統計用のカウンター（辞書で管理）
    counters = {
        'facility_add': 0,
        'facility_update': 0,
        'facility_delete': 0,
        'user_add': 0,
        'user_update': 0,
        'user_delete': 0
    }
    
    # 新規追加・更新されたイベントIDを記録するセット
    changed_event_ids = set()
    
    # === 会議室予定の取得 ===
    if process_facilities:
        # 施設のスケジュールを取得
        searchArray = ['社長室', '応接室', '事務室面談テーブル', '社員休憩室', '二階食堂']
        
        logger.info(f'取得期間: {date_list[0].strftime("%Y-%m-%d")} ~ 約1ヶ月先まで ({len(date_list)}週間)')
        logger.info(f'対象施設: {", ".join(searchArray)} ({len(searchArray)}施設)')
        logger.info('週表示のため、7日おきにアクセスします')
        logger.info('')

        # 各施設・各週でスケジュールを取得
        for search_term in searchArray:
            logger.info(f'{"=" * 40}')
            logger.info(f'施設: {search_term}')
            logger.info(f'{"=" * 40}')
            for i, target_date in enumerate(date_list, 1):
                logger.info(f'週 {i}/{len(date_list)}: {target_date.strftime("%Y-%m-%d")} の週を取得中...')
                get_place_schedule(driver, search_term, target_date, connection, logger, counters, log_messages, changed_event_ids)

        # 施設スケジュール参加ユーザーを取得
        logger.info('')
        logger.info('=' * 60)
        logger.info('参加者情報を取得中...')
        logger.info('=' * 60)
        
        cursor = connection.cursor()
        
        # フル同期の場合は全イベント、通常同期の場合は新規・更新されたイベントのみ
        events = []
        
        if run_full_sync:
            logger.info('フル同期: 全イベントの参加者情報を取得します')
            # データベースから全イベントを取得
            cursor.execute("""
                SELECT se.id, se.description_url, se.title, f.name as facility_name
                FROM schedule_events se
                JOIN facilities f ON se.facility_id = f.id
                WHERE se.description_url IS NOT NULL AND se.description_url != ''
                ORDER BY f.name, se.date
            """)
            events = cursor.fetchall()
        elif changed_event_ids:
            logger.info(f'通常同期: 新規・更新された{len(changed_event_ids)}件のイベントの参加者情報を取得します')
            # 新規・更新されたイベントのみ取得
            placeholders = ','.join(['%s'] * len(changed_event_ids))
            cursor.execute(f"""
                SELECT se.id, se.description_url, se.title, f.name as facility_name
                FROM schedule_events se
                JOIN facilities f ON se.facility_id = f.id
                WHERE se.id IN ({placeholders})
                  AND se.description_url IS NOT NULL AND se.description_url != ''
                ORDER BY f.name, se.date
            """, tuple(changed_event_ids))
            events = cursor.fetchall()
        else:
            logger.info('通常同期: 新規・更新されたイベントがないため、参加者情報の取得をスキップします')
        
        for event_id, description_url, event_title, facility_name in events:
            try:
                driver.get(description_url)
                time.sleep(1)  # ページが完全に読み込まれるまで待機

                # participantクラスが付与された要素をすべて取得
                participants_elements = driver.find_elements(By.CLASS_NAME, 'participant')
                participant_names = [element.text for element in participants_elements]

                # 既存の参加者を削除
                cursor.execute("DELETE FROM schedule_participants WHERE schedule_event_id = %s", (event_id,))
                
                # 新しい参加者を追加（ユーザー名からuser_idを取得）
                added_count = 0
                not_found_users = []
                for participant_name in participant_names:
                    user_id = get_user_id_by_name(connection, participant_name)
                    if user_id:
                        try:
                            cursor.execute("""
                                INSERT INTO schedule_participants (schedule_event_id, user_id, created_at, updated_at)
                                VALUES (%s, %s, NOW(), NOW())
                            """, (event_id, user_id))
                            added_count += 1
                        except Error as e:
                            # 重複エラーなどは無視
                            logger.debug(f'  参加者追加エラー: {participant_name} - {e}')
                    else:
                        not_found_users.append(participant_name)
                
                connection.commit()
                participant_count += added_count
                
                if not_found_users:
                    logger.warning(f'  {facility_name}: {event_title} - ユーザーが見つかりません: {", ".join(not_found_users)}')
                
                logger.info(f'  {facility_name}: {event_title} - 参加者: {added_count}名（{len(participant_names)}名中）')
            except Exception as e:
                logger.error(f'  {event_title}: 参加者取得エラー - {e}')
                connection.rollback()
        
        cursor.close()
    else:
        logger.info('会議室予定の取得をスキップします')
        logger.info('')
    
    # === ユーザー個人予定の取得 ===
    cybozu_users = []
    if process_users:
        logger.info('')
        logger.info('=' * 60)
        logger.info('ユーザー個人のスケジュールを取得中...')
        logger.info('=' * 60)
        
        # cybozu_flg=1のユーザーを取得
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, name
            FROM users
            WHERE cybozu_flg = 1
            ORDER BY name
        """)
        
        cybozu_users = cursor.fetchall()
        cursor.close()
        
        if cybozu_users:
            logger.info(f'対象ユーザー: {len(cybozu_users)}名')
            logger.info(f'取得期間: {date_list[0].strftime("%Y-%m-%d")} ~ 約1ヶ月先まで ({len(date_list)}週間)')
            logger.info('')
            
            # 各ユーザー・各週でスケジュールを取得
            for user in cybozu_users:
                user_id = user['id']
                user_name = user['name']
                
                logger.info(f'{"=" * 40}')
                logger.info(f'ユーザー: {user_name} (ID: {user_id})')
                logger.info(f'{"=" * 40}')
                
                for i, target_date in enumerate(date_list, 1):
                    logger.info(f'週 {i}/{len(date_list)}: {target_date.strftime("%Y-%m-%d")} の週を取得中...')
                    get_user_schedule(driver, user_name, user_id, target_date, connection, logger, counters, log_messages)
        else:
            logger.info('cybozu_flg=1のユーザーが見つかりませんでした')
    else:
        logger.info('ユーザー個人予定の取得をスキップします')
        logger.info('')
    
    connection.close()
    driver.quit()
    
    # 終了時刻を記録
    end_time = datetime.now()
    processing_time = (end_time - start_time).total_seconds()
    
    # 最終統計
    logger.info('')
    logger.info('=' * 60)
    logger.info('処理完了')
    logger.info('=' * 60)
    
    # ログメッセージに処理サマリーを追加
    log_messages.append('')
    log_messages.append('■ 処理結果サマリー')
    
    if process_facilities:
        logger.info(f'会議室予定: 取得完了')
        logger.info(f'  └ 追加: {counters["facility_add"]}件')
        logger.info(f'  └ 更新: {counters["facility_update"]}件')
        logger.info(f'  └ 削除: {counters["facility_delete"]}件')
        logger.info(f'  └ 参加者情報: {participant_count}名を取得')
        
        log_messages.append(f'  [会議室予定]')
        log_messages.append(f'    追加: {counters["facility_add"]}件')
        log_messages.append(f'    更新: {counters["facility_update"]}件')
        log_messages.append(f'    削除: {counters["facility_delete"]}件')
        log_messages.append(f'    参加者: {participant_count}名')
    else:
        logger.info('会議室予定: スキップ')
        log_messages.append('  [会議室予定] スキップ')
    
    if process_users:
        logger.info(f'ユーザー個人予定: {len(cybozu_users) if cybozu_users else 0}名分を取得')
        logger.info(f'  └ 追加: {counters["user_add"]}件')
        logger.info(f'  └ 更新: {counters["user_update"]}件')
        logger.info(f'  └ 削除: {counters["user_delete"]}件')
        
        log_messages.append(f'  [ユーザー個人予定] {len(cybozu_users) if cybozu_users else 0}名')
        log_messages.append(f'    追加: {counters["user_add"]}件')
        log_messages.append(f'    更新: {counters["user_update"]}件')
        log_messages.append(f'    削除: {counters["user_delete"]}件')
    else:
        logger.info('ユーザー個人予定: スキップ')
        log_messages.append('  [ユーザー個人予定] スキップ')
    
    log_messages.append('')
    log_messages.append(f'■ 実行終了: {end_time.strftime("%Y-%m-%d %H:%M:%S")}')
    log_messages.append(f'■ 処理時間: {processing_time:.2f}秒')
    log_messages.append('=' * 80)
    log_messages.append('')
    
    # ログファイルに書き込み
    write_log('\n'.join(log_messages))
    logger.info(f'ログを {LOG_FILE} に保存しました。')
    logger.info('=' * 60)

if __name__ == "__main__":
    main()
