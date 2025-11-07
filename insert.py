from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import Select
from webdriver_manager.chrome import ChromeDriverManager
import time
import mysql.connector
from mysql.connector import Error
from datetime import datetime


# データベース設定
DB_CONFIG = {
    'host': 'akioka.cloud',
    'database': 'akioka_db',
    'user': 'akioka_administrator',
    'password': 'Akiokapass0',
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci'
}

# ログファイルのパス
LOG_FILE = 'insert.log'


def write_log(message, log_file=LOG_FILE):
    """ログファイルにメッセージを書き込む"""
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(message + '\n')
    except Exception as e:
        print(f'ログ書き込みエラー: {e}')


def get_db_connection():
    """MySQLデータベースへの接続を取得"""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as e:
        print(f'データベース接続エラー: {e}')
        return None


def convert_date_to_cybozu_format(date_value):
    """日付をCybozu形式(da.YYYY.M.D)に変換"""
    if isinstance(date_value, str):
        # 文字列の場合、datetime.dateオブジェクトに変換
        date_obj = datetime.strptime(date_value, '%Y-%m-%d').date()
    else:
        # すでにdatetime.dateオブジェクトの場合
        date_obj = date_value
    
    # Cybozu形式に変換 (da.YYYY.M.D)
    return f"da.{date_obj.year}.{date_obj.month}.{date_obj.day}"


def get_participants_for_event(connection, event_id):
    """スケジュールイベントの参加者を取得"""
    try:
        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT u.name
            FROM schedule_participants sp
            JOIN users u ON sp.user_id = u.id
            WHERE sp.schedule_event_id = %s
            ORDER BY sp.id
        """
        cursor.execute(query, (event_id,))
        participants = cursor.fetchall()
        cursor.close()
        return [p['name'] for p in participants]
    except Error as e:
        print(f'参加者取得エラー: {e}')
        return []


def register_schedule_to_cybozu(driver, connection, event, log_messages=None):
    """Cybozuのスケジュール登録フォームにアクセスして時刻を設定"""
    print(f'\n--- スケジュール登録処理開始 (ID: {event["id"]}) ---')
    print(f'施設: {event["facility_name"]}')
    print(f'日付: {event["date"]}')
    print(f'タイトル: {event["title"]}')
    print(f'開始時刻: {event["start_datetime"]}')
    
    try:
        # 日付をCybozu形式に変換
        cybozu_date = convert_date_to_cybozu_format(event["date"])
        print(f'変換後の日付: {cybozu_date}')
        
        # スケジュール登録ページのURLを構築
        url = f"https://9w4c9.cybozu.com/o/ag.cgi?page=ScheduleEntry&UID=796&GID=&Date={cybozu_date}&BDate={cybozu_date}&CP="
        print(f'アクセスURL: {url}')
        
        # URLにアクセス
        driver.get(url)
        time.sleep(2)
        
        # 開始時刻を時と分に分割
        start_time_parts = event["start_datetime"].split(':')
        if len(start_time_parts) != 2:
            print(f'エラー: 開始時刻のフォーマットが不正です: {event["start_datetime"]}')
            return False
        
        start_hour = start_time_parts[0].strip().lstrip('0') or '0'  # 先頭の0を削除
        start_minute = start_time_parts[1].strip()
        
        # 分が"00"の場合は"0"に変換
        if start_minute == "00":
            start_minute = "0"
        
        print(f'設定する開始時刻: {start_hour}時 {start_minute}分')
        
        # 開始時刻の「時」を設定
        hour_select = driver.find_element(By.CLASS_NAME, 'SetTimeHourScheduleEntry')
        select_hour = Select(hour_select)
        select_hour.select_by_value(start_hour)
        print(f'  開始時を設定: {start_hour}')
        
        # 開始時刻の「分」を設定
        minute_select = driver.find_element(By.CLASS_NAME, 'SetTimeMinuteScheduleEntry')
        select_minute = Select(minute_select)
        select_minute.select_by_value(start_minute)
        print(f'  開始分を設定: {start_minute}')
        
        print('開始時刻の設定が完了しました')
        time.sleep(0.5)
        
        # 終了時刻を時と分に分割
        end_time_parts = event["end_datetime"].split(':')
        if len(end_time_parts) != 2:
            print(f'エラー: 終了時刻のフォーマットが不正です: {event["end_datetime"]}')
            return False
        
        end_hour = end_time_parts[0].strip().lstrip('0') or '0'  # 先頭の0を削除
        end_minute = end_time_parts[1].strip()
        
        # 分が"00"の場合は"0"に変換
        if end_minute == "00":
            end_minute = "0"
        
        print(f'設定する終了時刻: {end_hour}時 {end_minute}分')
        
        # 終了時刻の「時」を設定
        end_hour_select = driver.find_element(By.CLASS_NAME, 'EndTimeHourScheduleEntry')
        select_end_hour = Select(end_hour_select)
        select_end_hour.select_by_value(end_hour)
        print(f'  終了時を設定: {end_hour}')
        
        # 終了時刻の「分」を設定
        end_minute_select = driver.find_element(By.CLASS_NAME, 'EndTimeMinuteScheduleEntry')
        select_end_minute = Select(end_minute_select)
        select_end_minute.select_by_value(end_minute)
        print(f'  終了分を設定: {end_minute}')
        
        print('終了時刻の設定が完了しました')
        time.sleep(0.5)
        
        # タイトルを入力
        print(f'タイトルを入力: {event["title"]}')
        schedule_detail = driver.find_element(By.CLASS_NAME, 'scheduleEntryLayoutDetail')
        title_input = schedule_detail.find_element(By.TAG_NAME, 'input')
        title_input.clear()
        title_input.send_keys(event["title"])
        print('タイトルの入力が完了しました')
        time.sleep(0.5)
        
        # 参加者を取得
        participants = get_participants_for_event(connection, event["id"])
        print(f'参加者数: {len(participants)}人')
        
        if participants:
            for idx, participant_name in enumerate(participants, 1):
                print(f'  [{idx}/{len(participants)}] 参加者を入力: {participant_name}')
                
                # 参加者入力フィールドに名前を入力
                participant_input = driver.find_element(By.NAME, 'sUIDUserSearchText')
                participant_input.clear()
                participant_input.send_keys(participant_name)
                time.sleep(0.5)
                
                # 検索ボタンをクリック
                search_button = driver.find_element(By.CLASS_NAME, 'searchButton')
                search_button.click()
                print(f'    検索ボタンをクリック')
                time.sleep(1)
                
                # 追加ボタンをクリック
                vr_select_buttons = driver.find_element(By.CLASS_NAME, 'vr_selectButtons')
                buttons = vr_select_buttons.find_elements(By.TAG_NAME, 'button')
                if buttons:
                    buttons[0].click()  # 最初のボタンをクリック
                    print(f'    追加ボタンをクリック')
                else:
                    print(f'    警告: 追加ボタンが見つかりませんでした')
                time.sleep(0.5)
                
            print(f'全参加者の入力が完了しました ({len(participants)}人)')
        else:
            print('参加者が見つかりませんでした')
        
        time.sleep(1)
        
        # 施設を設定
        if event.get("facility_cybozu_id"):
            print(f'施設IDを設定: {event["facility_cybozu_id"]}')
            fcid_select = driver.find_element(By.NAME, 'FCID')
            select_fcid = Select(fcid_select)
            select_fcid.select_by_value(str(event["facility_cybozu_id"]))
            print('施設の設定が完了しました')
            time.sleep(0.5)
            
            # 施設追加ボタンをクリック
            vr_select_buttons_list = driver.find_elements(By.CLASS_NAME, 'vr_selectButtons')
            if len(vr_select_buttons_list) >= 2:
                # 二つ目のvr_selectButtons要素
                second_vr_select_buttons = vr_select_buttons_list[1]
                # その中の一つ目のvr_stdButtonボタン
                buttons = second_vr_select_buttons.find_elements(By.CLASS_NAME, 'vr_stdButton')
                if buttons:
                    buttons[0].click()
                    print('施設追加ボタンをクリックしました')
                    time.sleep(0.5)
                else:
                    print('警告: 施設追加ボタンが見つかりませんでした')
            else:
                print('警告: vr_selectButtonsが2つ見つかりませんでした')
        else:
            print('施設IDが設定されていません')
        
        time.sleep(1)
        
        # 送信ボタンをクリック
        print('スケジュールを送信中...')
        submit_button = driver.find_element(By.CLASS_NAME, 'vr_hotButton')
        submit_button.click()
        print('送信ボタンをクリックしました')
        time.sleep(2)
        
        # statusを0に更新（登録完了）
        try:
            cursor = connection.cursor()
            cursor.execute("""
                UPDATE schedule_events
                SET status = 0, updated_at = NOW()
                WHERE id = %s
            """, (event["id"],))
            connection.commit()
            cursor.close()
            print('ステータスを0に更新しました（登録完了）')
        except Error as e:
            print(f'警告: ステータス更新エラー: {e}')
        
        # ログに登録成功を記録
        if log_messages is not None:
            log_messages.append(f'  [成功] ID:{event["id"]} | {event["date"]} {event["start_datetime"]}-{event["end_datetime"]} | {event["title"]}')
        
        return True
        
    except Exception as e:
        print(f'エラーが発生しました: {e}')
        # ログに登録失敗を記録
        if log_messages is not None:
            log_messages.append(f'  [失敗] ID:{event["id"]} | {event["date"]} {event["start_datetime"]}-{event["end_datetime"]} | {event["title"]} | エラー: {e}')
        return False


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


def main():
    # 開始時刻を記録
    start_time = datetime.now()
    
    # ログメッセージを格納するリスト
    log_messages = []
    log_messages.append('=' * 80)
    log_messages.append(f'■ 実行開始: {start_time.strftime("%Y-%m-%d %H:%M:%S")}')
    
    print('=' * 60)
    print('Cybozu処理スクリプトを開始します')
    print('=' * 60)
    
    # データベース接続
    print('データベースに接続中...')
    connection = get_db_connection()
    if not connection:
        error_msg = 'データベース接続に失敗しました。処理を終了します。'
        print(error_msg)
        log_messages.append(f'■ エラー: {error_msg}')
        log_messages.append('=' * 80)
        log_messages.append('')
        write_log('\n'.join(log_messages))
        return
    
    print('データベース接続成功')
    
    # schedule_eventsテーブルからデータを取得
    print('')
    print('=' * 60)
    print('スケジュールを取得中...')
    print('=' * 60)
    
    try:
        cursor = connection.cursor(dictionary=True)
        
        # statusカラムの存在を確認
        cursor.execute("""
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = %s 
              AND TABLE_NAME = 'schedule_events' 
              AND COLUMN_NAME = 'status'
        """, (DB_CONFIG['database'],))
        
        has_status_column = cursor.fetchone() is not None
        
        # statusカラムの有無に応じてクエリを構築
        if has_status_column:
            print('statusカラムが存在します。status=1の条件で取得します。')
            query = """
                SELECT 
                    se.id,
                    se.facility_id,
                    f.name as facility_name,
                    f.cybozu_id as facility_cybozu_id,
                    se.date,
                    se.title,
                    se.start_datetime,
                    se.end_datetime,
                    se.badge,
                    se.description_url,
                    se.status
                FROM schedule_events se
                JOIN facilities f ON se.facility_id = f.id
                WHERE se.status = 1
                ORDER BY se.date, se.start_datetime
            """
        else:
            print('statusカラムが存在しません。全件取得します。')
            query = """
                SELECT 
                    se.id,
                    se.facility_id,
                    f.name as facility_name,
                    f.cybozu_id as facility_cybozu_id,
                    se.date,
                    se.title,
                    se.start_datetime,
                    se.end_datetime,
                    se.badge,
                    se.description_url
                FROM schedule_events se
                JOIN facilities f ON se.facility_id = f.id
                ORDER BY se.date, se.start_datetime
            """
        
        cursor.execute(query)
        events = cursor.fetchall()
        cursor.close()
        
        if events:
            print(f'\n取得件数: {len(events)}件\n')
            log_messages.append(f'■ 取得件数: {len(events)}件')
            log_messages.append('')
            
            for idx, event in enumerate(events, 1):
                print(f'--- [{idx}] ---')
                print(f'ID: {event["id"]}')
                print(f'施設: {event["facility_name"]} (ID: {event["facility_id"]}, Cybozu ID: {event.get("facility_cybozu_id", "未設定")})')
                print(f'日付: {event["date"]}')
                print(f'タイトル: {event["title"]}')
                print(f'時間: {event["start_datetime"]} - {event["end_datetime"]}')
                print(f'バッジ: {event["badge"]}')
                print(f'URL: {event["description_url"]}')
                if has_status_column and 'status' in event:
                    print(f'ステータス: {event["status"]}')
                print('')
            
            # Chromeブラウザのオプションを設定
            print('\n' + '=' * 60)
            print('ブラウザを起動します')
            print('=' * 60)
            options = webdriver.ChromeOptions()
            # options.add_argument('--headless')  # ヘッドレスモードにする場合はコメント解除

            # Chromeブラウザのドライバーを設定
            print('Chromeドライバーを起動中...')
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

            # ログイン処理
            print('Cybozuにログイン中...')
            login(driver)
            print('ログイン成功')
            
            # スケジュールの登録処理
            print('\n' + '=' * 60)
            print('スケジュール登録処理を開始します')
            print('=' * 60)
            
            success_count = 0
            fail_count = 0
            
            for idx, event in enumerate(events, 1):
                print(f'\n[{idx}/{len(events)}] 処理中...')
                result = register_schedule_to_cybozu(driver, connection, event, log_messages)
                
                if result:
                    success_count += 1
                    print('✓ 登録成功')
                else:
                    fail_count += 1
                    print('✗ 登録失敗')
                
                # 次のイベント処理前に少し待機
                if idx < len(events):
                    time.sleep(1)
            
            print('\n' + '=' * 60)
            print('スケジュール登録処理完了')
            print('=' * 60)
            print(f'成功: {success_count}件')
            print(f'失敗: {fail_count}件')
            print(f'合計: {len(events)}件')
            print('=' * 60)
            
            # サマリーをログに追加
            log_messages.append('')
            log_messages.append(f'■ 処理結果サマリー')
            log_messages.append(f'  成功: {success_count}件')
            log_messages.append(f'  失敗: {fail_count}件')
            log_messages.append(f'  合計: {len(events)}件')
            
            # ブラウザを閉じる
            driver.quit()
            
        else:
            if has_status_column:
                skip_msg = 'status=1のスケジュールは見つかりませんでした。登録処理をスキップします。'
                print(f'\n{skip_msg}')
            else:
                skip_msg = 'スケジュールは見つかりませんでした。登録処理をスキップします。'
                print(f'\n{skip_msg}')
            
            log_messages.append(f'■ {skip_msg}')
            
    except Error as e:
        error_msg = f'データ取得エラー: {e}'
        print(error_msg)
        log_messages.append(f'■ エラー: {error_msg}')
    
    print('\n' + '=' * 60)
    print('全処理完了')
    print('=' * 60)
    
    # 終了時刻を記録
    end_time = datetime.now()
    processing_time = (end_time - start_time).total_seconds()
    
    log_messages.append('')
    log_messages.append(f'■ 実行終了: {end_time.strftime("%Y-%m-%d %H:%M:%S")}')
    log_messages.append(f'■ 処理時間: {processing_time:.2f}秒')
    log_messages.append('=' * 80)
    log_messages.append('')
    
    # ログファイルに書き込み
    write_log('\n'.join(log_messages))
    print(f'\nログを {LOG_FILE} に保存しました。')
    
    # クリーンアップ
    connection.close()
    
    print('\nスクリプトを終了します。')
    print('=' * 60)


if __name__ == "__main__":
    main()

