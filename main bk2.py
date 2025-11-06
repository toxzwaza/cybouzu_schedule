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



def setup_logging():
    """ログの設定"""
    # ログファイル名（日付付き）
    log_filename = datetime.now().strftime('sync_log_%Y%m%d_%H%M%S.log')
    
    # ロガーの設定
    logger = logging.getLogger('schedule_sync')
    logger.setLevel(logging.INFO)
    
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



def get_place_schedule(driver, search_term, target_date, logger=None):
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
            
            try:
                with open('schedule.json', 'r', encoding='utf-8') as f:
                    schedule_data = json.load(f)
                    
                # 古い形式のデータ構造をチェックし、新しい形式に変換
                for place_name, value in list(schedule_data.items()):
                    if isinstance(value, list):
                        # 古い形式（リスト）の場合は削除して新しい形式で再作成
                        print(f'  警告: {place_name}の古い形式のデータを削除します')
                        del schedule_data[place_name]
            except FileNotFoundError:
                schedule_data = {}
            
            # 既存のIDの最大値を取得
            max_id = 0
            for place_name, dates_dict in schedule_data.items():
                if isinstance(dates_dict, dict):
                    for date_key, events in dates_dict.items():
                        if isinstance(events, list):
                            for event in events:
                                if isinstance(event, dict) and "id" in event:
                                    if event["id"] > max_id:
                                        max_id = event["id"]
            
            # 施設名のキーが存在しない場合は作成
            if search_term not in schedule_data:
                schedule_data[search_term] = {}
            
            # 日付ごとにイベントを同期（追加・更新・削除）
            for event_date, event_list in events_by_date.items():
                # 日付のキーが存在しない場合は作成
                if event_date not in schedule_data[search_term]:
                    schedule_data[search_term][event_date] = []
                
                # 既存のイベントをURLでインデックス化（高速検索用）
                existing_events_by_url = {
                    event.get('description_url'): event 
                    for event in schedule_data[search_term][event_date]
                    if isinstance(event, dict)
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
                            existing_event.get('title') != new_event['title'] or
                            existing_event.get('start_datetime') != new_event['start_datetime'] or
                            existing_event.get('end_datetime') != new_event['end_datetime'] or
                            existing_event.get('badge') != new_event['badge']
                        )
                        
                        if has_changes:
                            # 変更を適用（IDとparticipantsは保持）
                            event_id = existing_event.get('id')
                            participants = existing_event.get('participants', [])
                            
                            # 変更内容の詳細
                            changes = []
                            if existing_event.get('title') != new_event['title']:
                                changes.append(f"タイトル: {existing_event.get('title')} → {new_event['title']}")
                            if existing_event.get('start_datetime') != new_event['start_datetime']:
                                changes.append(f"開始: {existing_event.get('start_datetime')} → {new_event['start_datetime']}")
                            if existing_event.get('end_datetime') != new_event['end_datetime']:
                                changes.append(f"終了: {existing_event.get('end_datetime')} → {new_event['end_datetime']}")
                            if existing_event.get('badge') != new_event['badge']:
                                changes.append(f"バッジ: {existing_event.get('badge')} → {new_event['badge']}")
                            
                            existing_event.update({
                                'title': new_event['title'],
                                'start_datetime': new_event['start_datetime'],
                                'end_datetime': new_event['end_datetime'],
                                'badge': new_event['badge'],
                                'description_url': new_event['description_url']
                            })
                            
                            # IDとparticipantsを復元
                            if event_id:
                                existing_event['id'] = event_id
                            if participants:
                                existing_event['participants'] = participants
                            
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
                        max_id += 1
                        new_event["id"] = max_id
                        schedule_data[search_term][event_date].append(new_event)
                        message = f'[追加] {event_date}: {new_event["title"]} (ID: {max_id}, {new_event["start_datetime"]}-{new_event["end_datetime"]}, {new_event["badge"]})'
                        if logger:
                            logger.info(message)
                        else:
                            print(message)
                
                # 削除されたイベントを検出して削除
                events_to_remove = []
                for existing_event in schedule_data[search_term][event_date]:
                    if isinstance(existing_event, dict):
                        event_url = existing_event.get('description_url')
                        if event_url and event_url not in new_event_urls:
                            events_to_remove.append(existing_event)
                            message = f'[削除] {event_date}: {existing_event.get("title", "不明")} (ID: {existing_event.get("id")}) - Cybozuから削除されました'
                            if logger:
                                logger.warning(message)
                            else:
                                print(message)
                
                # 削除対象のイベントを削除
                for event_to_remove in events_to_remove:
                    schedule_data[search_term][event_date].remove(event_to_remove)
                
                # 空になった日付エントリを削除
                if not schedule_data[search_term][event_date]:
                    del schedule_data[search_term][event_date]
                    print(f'  {event_date}: この日の予定がすべて削除されたため、日付エントリを削除')
            
            # 空になった施設エントリを削除
            if not schedule_data[search_term]:
                del schedule_data[search_term]
                print(f'  {search_term}: この施設の予定がすべて削除されたため、施設エントリを削除')
            
            # JSONファイルに書き込み
            with open('schedule.json', 'w', encoding='utf-8') as f:
                json.dump(schedule_data, f, ensure_ascii=False, indent=4)
            
            
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
    
    # Chromeブラウザのオプションを設定
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')

    # Chromeブラウザのドライバーを設定
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    # ログイン処理
    logger.info('Cybozuにログイン中...')
    login(driver)
    logger.info('ログイン成功')

    # 施設のスケジュールを取得
    searchArray = ['社長室', '応接室', '事務室面談テーブル', '社員休憩室', '二階食堂']
    
    # 現在の日付から1ヶ月先までの週のリストを生成（7日おき）
    # Cybozuは週表示なので、7日おきにアクセスすれば全期間をカバーできる
    start_date = datetime.now()
    date_list = [start_date + timedelta(days=x*7) for x in range(5)]  # 5週間分（35日）
    
    logger.info(f'取得期間: {date_list[0].strftime("%Y-%m-%d")} ~ 約1ヶ月先まで ({len(date_list)}週間)')
    logger.info(f'対象施設: {", ".join(searchArray)} ({len(searchArray)}施設)')
    logger.info('週表示のため、7日おきにアクセスします')
    logger.info('')

    # 各施設・各週でスケジュールを取得
    total_added = 0
    total_updated = 0
    total_deleted = 0
    
    for search_term in searchArray:
        logger.info(f'{"=" * 40}')
        logger.info(f'施設: {search_term}')
        logger.info(f'{"=" * 40}')
        for i, target_date in enumerate(date_list, 1):
            logger.info(f'週 {i}/{len(date_list)}: {target_date.strftime("%Y-%m-%d")} の週を取得中...')
            get_place_schedule(driver, search_term, target_date, logger)

    # 施設スケジュール参加ユーザーを取得
    logger.info('')
    logger.info('=' * 60)
    logger.info('参加者情報を取得中...')
    logger.info('=' * 60)
    
    participant_count = 0
    with open('schedule.json', 'r', encoding='utf-8') as f:
        schedule_data = json.load(f)
        for place, dates_dict in schedule_data.items():
            # データ構造のチェック
            if not isinstance(dates_dict, dict):
                logger.warning(f'{place}のデータ構造が不正です。スキップします。')
                continue
                
            logger.info(f'施設: {place}')
            for date_key, events in dates_dict.items():
                if not isinstance(events, list):
                    logger.warning(f'  {date_key}のイベントデータが不正です。スキップします。')
                    continue
                    
                for event in events:
                    if not isinstance(event, dict):
                        continue
                    
                    description_url = event.get("description_url")
                    if not description_url:
                        logger.warning(f'  {event.get("title", "不明")}: 説明URLが見つかりません')
                        continue
                        
                    try:
                        driver.get(description_url)
                        time.sleep(1)  # ページが完全に読み込まれるまで待機

                        # participantクラスが付与された要素をすべて取得
                        participants_elements = driver.find_elements(By.CLASS_NAME, 'participant')
                        participants = [element.text for element in participants_elements]

                        # JSONファイルにparticipantsを追加
                        event["participants"] = participants
                        participant_count += len(participants)
                        logger.info(f'  {date_key}: {event.get("title")} - 参加者: {len(participants)}名')
                    except Exception as e:
                        logger.error(f'  {event.get("title", "不明")}: 参加者取得エラー - {e}')
                        event["participants"] = []

        # 変更されたデータをJSONファイルに書き込む
        with open('schedule.json', 'w', encoding='utf-8') as f:
            json.dump(schedule_data, f, ensure_ascii=False, indent=4)
    
    driver.quit()
    
    # 最終統計
    logger.info('')
    logger.info('=' * 60)
    logger.info('処理完了')
    logger.info('=' * 60)
    logger.info(f'参加者情報: {participant_count}名を取得')
    logger.info(f'ログファイル: {log_filename}')
    logger.info('=' * 60)

if __name__ == "__main__":
    main()
