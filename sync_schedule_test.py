from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
from urllib.parse import quote
from datetime import datetime, timedelta
import re
import logging
import mysql.connector
from mysql.connector import Error


# データベース設定
DB_CONFIG = {
    'host': 'akioka.cloud',
    'database': 'akioka_db',
    'user': 'akioka_administrator',
    'password': 'Akiokapass0',
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


def setup_logging():
    """ログの設定"""
    # ログファイル名（日付付き）
    log_filename = datetime.now().strftime('sync_test_log_%Y%m%d_%H%M%S.log')
    
    # ロガーの設定
    logger = logging.getLogger('schedule_sync_test')
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
        from urllib.parse import urlparse, parse_qs
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        if 'sEID' in query_params:
            return int(query_params['sEID'][0])
        return None
    except Exception as e:
        return None


def login(driver):
    """Cybozuにログイン"""
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


def get_user_schedule(driver, user_name, user_id, target_date, connection, logger):
    """ユーザー個人のスケジュールを取得"""
    try:
        # 日付を文字列に変換
        date_str = f"da.{target_date.year}.{target_date.month}.{target_date.day}"
        date_key = target_date.strftime('%Y-%m-%d')
        
        # ユーザー名をURLエンコード
        encoded_text = quote(user_name)
        
        # URLを構築
        url = f"https://9w4c9.cybozu.com/o/ag.cgi?page=ScheduleIndex&CP=&uid=796&gid=virtual&date={date_str}&Text={encoded_text}"
        
        logger.info(f'ユーザー「{user_name}」の{date_key}のスケジュールにアクセス中...')
        
        # URLに直接アクセス
        driver.get(url)
        time.sleep(1)

        # スケジュール要素を取得
        try:
            element = driver.find_element(By.ID, 'tblgroupweek')
        except Exception as e:
            logger.error(f'スケジュール要素の取得に失敗しました: {e}')
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
                            logger.debug(f'  時刻指定なしの予定をスキップしました')
                            continue
                        
                        event_date_time = event_date_time_elements[0]
                        event_content = event_inner.find_element(By.CLASS_NAME, 'event')

                        # hrefの値を取得
                        href = event_content.get_attribute('href')
                        
                        # URLから実際の日付を抽出
                        event_date = extract_date_from_url(href)
                        if not event_date:
                            logger.warning(f'  警告: URLから日付を抽出できませんでした: {href}')
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
                        logger.error(f'  イベント情報の処理中にエラーが発生しました: {e}')
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
                            
                            logger.info(f'[更新] {event_date}: {new_event["title"]} - {", ".join(changes)}')
                        else:
                            # 変更なし
                            logger.info(f'[変更なし] {event_date}: {new_event["title"]}')
                    else:
                        # 新規追加
                        cursor.execute("""
                            INSERT INTO user_schedules 
                            (user_id, date, title, start_datetime, end_datetime, badge, description_url, EID, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
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
                        
                        logger.info(f'[追加] {event_date}: {new_event["title"]} (ID: {new_event_id}, {new_event["start_datetime"]}-{new_event["end_datetime"]}, {new_event["badge"]})')
                
                # 削除されたイベントを検出して削除
                for existing_event in existing_events:
                    event_id = existing_event[0]
                    event_title = existing_event[1]
                    
                    # 処理済みでないイベントを削除
                    if event_id not in processed_db_ids:
                        cursor.execute("DELETE FROM user_schedules WHERE id = %s", (event_id,))
                        connection.commit()
                        
                        logger.warning(f'[削除] {event_date}: {event_title} (ID: {event_id}) - Cybozuから削除されました')
            
            cursor.close()
            
        except Exception as e:
            logger.error(f'イベント要素の取得に失敗しました: {e}')
            return None

    except Exception as e:
        logger.error(f'予期せぬエラーが発生しました: {e}')
        return None


def main():
    # ログの設定
    logger, log_filename = setup_logging()
    logger.info('=' * 60)
    logger.info('【テスト】村上 飛羽のスケジュール同期テスト')
    logger.info(f'ログファイル: {log_filename}')
    logger.info('=' * 60)
    
    # データベース接続
    logger.info('データベースに接続中...')
    connection = get_db_connection()
    if not connection:
        logger.error('データベース接続に失敗しました。処理を終了します。')
        return
    
    logger.info('データベース接続成功')
    
    # テスト対象ユーザーを取得
    cursor = connection.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, name
        FROM users
        WHERE name = '村上 飛羽'
    """)
    
    user = cursor.fetchone()
    cursor.close()
    
    if not user:
        logger.error('ユーザー「村上 飛羽」が見つかりませんでした。')
        connection.close()
        return
    
    user_id = user['id']
    user_name = user['name']
    
    logger.info(f'テスト対象ユーザー: {user_name} (ID: {user_id})')
    logger.info('')
    
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
    start_date = datetime.now()
    date_list = [start_date + timedelta(days=x*7) for x in range(5)]  # 5週間分（35日）
    
    logger.info(f'取得期間: {date_list[0].strftime("%Y-%m-%d")} ~ 約1ヶ月先まで ({len(date_list)}週間)')
    logger.info('週表示のため、7日おきにアクセスします')
    logger.info('')
    
    logger.info(f'{"=" * 40}')
    logger.info(f'ユーザー: {user_name} (ID: {user_id})')
    logger.info(f'{"=" * 40}')
    
    # 各週でスケジュールを取得
    for i, target_date in enumerate(date_list, 1):
        logger.info(f'週 {i}/{len(date_list)}: {target_date.strftime("%Y-%m-%d")} の週を取得中...')
        get_user_schedule(driver, user_name, user_id, target_date, connection, logger)
    
    connection.close()
    driver.quit()
    
    # 最終統計
    logger.info('')
    logger.info('=' * 60)
    logger.info('テスト完了')
    logger.info('=' * 60)
    logger.info(f'ユーザー「{user_name}」のスケジュール同期が完了しました')
    logger.info(f'ログファイル: {log_filename}')
    logger.info('=' * 60)


if __name__ == "__main__":
    main()

