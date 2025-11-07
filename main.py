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



# デバッグフラグ（Trueにすると処理を選択できる）
DEBUG_FLG = True

# データベース設定
DB_CONFIG = {
    'host': 'akioka.cloud',
    'database': 'akioka_db',
    'user': 'akioka_administrator',
    'password': 'Akiokapass0',  # パスワードを設定してください
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci'
}


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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY unique_event (facility_id, date, description_url(255)),
                FOREIGN KEY (facility_id) REFERENCES facilities(id) ON DELETE CASCADE,
                INDEX idx_facility_date (facility_id, date),
                INDEX idx_date (date)
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY unique_user_event (user_id, date, description_url(255)),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user_date (user_id, date),
                INDEX idx_date (date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
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


def setup_logging():
    """ログの設定"""
    # ログファイル名（日付付き）
    log_filename = datetime.now().strftime('sync_log_%Y%m%d_%H%M%S.log')
    
    # ロガーの設定
    logger = logging.getLogger('schedule_sync')
    logger.setLevel(logging.INFO)
    
    # 既存のハンドラをクリア（重複防止）
    if logger.handlers:
        logger.handlers.clear()
    
    # ファイルハンドラ
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # コンソールハンドラ
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # フォーマット設定
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # ハンドラを追加
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger, log_filename


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



def get_place_schedule(driver, search_term, target_date, connection, logger=None):
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
                            "description_url": href
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
                    SELECT id, title, start_datetime, end_datetime, badge, description_url
                    FROM schedule_events
                    WHERE facility_id = %s AND date = %s
                """, (facility_id, event_date))
                
                existing_events = cursor.fetchall()
                existing_events_by_url = {
                    row[5]: {
                        'id': row[0],
                        'title': row[1],
                        'start_datetime': row[2],
                        'end_datetime': row[3],
                        'badge': row[4],
                        'description_url': row[5]
                    }
                    for row in existing_events
                }
                
                # 新しく取得したイベントのURLセット
                new_event_urls = {event['description_url'] for event in event_list}
                
                # 新しいデータを同期（追加・更新）
                for new_event in event_list:
                    event_url = new_event['description_url']
                    
                    # 既存のイベントを検索
                    if event_url in existing_events_by_url:
                        existing_event = existing_events_by_url[event_url]
                        
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
                                SET title = %s, start_datetime = %s, end_datetime = %s, badge = %s, description_url = %s, updated_at = NOW()
                                WHERE id = %s
                            """, (
                                new_event['title'],
                                new_event['start_datetime'],
                                new_event['end_datetime'],
                                new_event['badge'],
                                new_event['description_url'],
                                existing_event['id']
                            ))
                            connection.commit()
                            
                            message = f'[更新] {event_date}: {new_event["title"]} - {", ".join(changes)}'
                            if logger:
                                logger.info(message)
                            else:
                                print(message)
                        else:
                            # 変更なし
                            message = f'[変更なし] {event_date}: {new_event["title"]}'
                            if logger:
                                logger.debug(message)
                    else:
                        # 新規追加
                        cursor.execute("""
                            INSERT INTO schedule_events 
                            (facility_id, date, title, start_datetime, end_datetime, badge, description_url, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                        """, (
                            facility_id,
                            event_date,
                            new_event['title'],
                            new_event['start_datetime'],
                            new_event['end_datetime'],
                            new_event['badge'],
                            new_event['description_url']
                        ))
                        connection.commit()
                        new_event_id = cursor.lastrowid
                        
                        message = f'[追加] {event_date}: {new_event["title"]} (ID: {new_event_id}, {new_event["start_datetime"]}-{new_event["end_datetime"]}, {new_event["badge"]})'
                        if logger:
                            logger.info(message)
                        else:
                            print(message)
                
                # 削除されたイベントを検出して削除
                for existing_event in existing_events:
                    event_url = existing_event[5]  # description_url
                    if event_url and event_url not in new_event_urls:
                        event_id = existing_event[0]
                        event_title = existing_event[1]
                        
                        # 参加者も削除（CASCADEで自動削除されるが、ログ用）
                        cursor.execute("DELETE FROM schedule_events WHERE id = %s", (event_id,))
                        connection.commit()
                        
                        message = f'[削除] {event_date}: {event_title} (ID: {event_id}) - Cybozuから削除されました'
                        if logger:
                            logger.warning(message)
                        else:
                            print(message)
            
            cursor.close()
            
            
        except Exception as e:
            print(f'イベント要素の取得に失敗しました: {e}')
            return None


    except Exception as e:
        print(f'予期せぬエラーが発生しました: {e}')
        return None


def get_user_schedule(driver, user_name, user_id, target_date, connection, logger=None):
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
                            "description_url": href
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
                    SELECT id, title, start_datetime, end_datetime, badge, description_url
                    FROM user_schedules
                    WHERE user_id = %s AND date = %s
                """, (user_id, event_date))
                
                existing_events = cursor.fetchall()
                existing_events_by_url = {
                    row[5]: {
                        'id': row[0],
                        'title': row[1],
                        'start_datetime': row[2],
                        'end_datetime': row[3],
                        'badge': row[4],
                        'description_url': row[5]
                    }
                    for row in existing_events
                }
                
                # 新しく取得したイベントのURLセット
                new_event_urls = {event['description_url'] for event in event_list}
                
                # 新しいデータを同期（追加・更新）
                for new_event in event_list:
                    event_url = new_event['description_url']
                    
                    # 既存のイベントを検索
                    if event_url in existing_events_by_url:
                        existing_event = existing_events_by_url[event_url]
                        
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
                                SET title = %s, start_datetime = %s, end_datetime = %s, badge = %s, description_url = %s, updated_at = NOW()
                                WHERE id = %s
                            """, (
                                new_event['title'],
                                new_event['start_datetime'],
                                new_event['end_datetime'],
                                new_event['badge'],
                                new_event['description_url'],
                                existing_event['id']
                            ))
                            connection.commit()
                            
                            message = f'[更新] {event_date}: {new_event["title"]} - {", ".join(changes)}'
                            if logger:
                                logger.info(message)
                            else:
                                print(message)
                        else:
                            # 変更なし
                            message = f'[変更なし] {event_date}: {new_event["title"]}'
                            if logger:
                                logger.debug(message)
                    else:
                        # 新規追加
                        cursor.execute("""
                            INSERT INTO user_schedules 
                            (user_id, date, title, start_datetime, end_datetime, badge, description_url, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                        """, (
                            user_id,
                            event_date,
                            new_event['title'],
                            new_event['start_datetime'],
                            new_event['end_datetime'],
                            new_event['badge'],
                            new_event['description_url']
                        ))
                        connection.commit()
                        new_event_id = cursor.lastrowid
                        
                        message = f'[追加] {event_date}: {new_event["title"]} (ID: {new_event_id}, {new_event["start_datetime"]}-{new_event["end_datetime"]}, {new_event["badge"]})'
                        if logger:
                            logger.info(message)
                        else:
                            print(message)
                
                # 削除されたイベントを検出して削除
                for existing_event in existing_events:
                    event_url = existing_event[5]  # description_url
                    if event_url and event_url not in new_event_urls:
                        event_id = existing_event[0]
                        event_title = existing_event[1]
                        
                        cursor.execute("DELETE FROM user_schedules WHERE id = %s", (event_id,))
                        connection.commit()
                        
                        message = f'[削除] {event_date}: {event_title} (ID: {event_id}) - Cybozuから削除されました'
                        if logger:
                            logger.warning(message)
                        else:
                            print(message)
            
            cursor.close()
            
        except Exception as e:
            print(f'イベント要素の取得に失敗しました: {e}')
            return None

    except Exception as e:
        print(f'予期せぬエラーが発生しました: {e}')
        return None


def main():
    # ログの設定
    logger, log_filename = setup_logging()
    logger.info('=' * 60)
    logger.info('スケジュール同期処理を開始します')
    logger.info(f'ログファイル: {log_filename}')
    logger.info('=' * 60)
    
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

    # 現在の日付から1ヶ月先までの週のリストを生成（7日おき）
    # Cybozuは週表示なので、7日おきにアクセスすれば全期間をカバーできる
    start_date = datetime.now()
    date_list = [start_date + timedelta(days=x*7) for x in range(5)]  # 5週間分（35日）
    
    participant_count = 0
    
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
                get_place_schedule(driver, search_term, target_date, connection, logger)

        # 施設スケジュール参加ユーザーを取得
        logger.info('')
        logger.info('=' * 60)
        logger.info('参加者情報を取得中...')
        logger.info('=' * 60)
        
        cursor = connection.cursor()
        
        # データベースから参加者未登録のイベントを取得
        cursor.execute("""
            SELECT se.id, se.description_url, se.title, f.name as facility_name
            FROM schedule_events se
            JOIN facilities f ON se.facility_id = f.id
            WHERE se.description_url IS NOT NULL AND se.description_url != ''
            ORDER BY f.name, se.date
        """)
        
        events = cursor.fetchall()
        
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
                    get_user_schedule(driver, user_name, user_id, target_date, connection, logger)
        else:
            logger.info('cybozu_flg=1のユーザーが見つかりませんでした')
    else:
        logger.info('ユーザー個人予定の取得をスキップします')
        logger.info('')
    
    connection.close()
    driver.quit()
    
    # 最終統計
    logger.info('')
    logger.info('=' * 60)
    logger.info('処理完了')
    logger.info('=' * 60)
    
    if process_facilities:
        logger.info(f'会議室予定: 取得完了')
        logger.info(f'  └ 参加者情報: {participant_count}名を取得')
    else:
        logger.info('会議室予定: スキップ')
    
    if process_users:
        logger.info(f'ユーザー個人予定: {len(cybozu_users) if cybozu_users else 0}名分を取得')
    else:
        logger.info('ユーザー個人予定: スキップ')
    
    logger.info(f'ログファイル: {log_filename}')
    logger.info('=' * 60)

if __name__ == "__main__":
    main()
