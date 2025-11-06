from flask import Flask, render_template, request, jsonify
import json
from datetime import datetime

app = Flask(__name__)

def load_schedule_data():
    """schedule.jsonからデータを読み込む"""
    try:
        with open('schedule.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

def search_schedules(facility=None, date=None, keyword=None, participant=None):
    """スケジュールを検索する"""
    data = load_schedule_data()
    results = []
    
    for place_name, dates_dict in data.items():
        # 施設名でフィルタ
        if facility and facility != "all" and place_name != facility:
            continue
            
        if not isinstance(dates_dict, dict):
            continue
            
        for date_key, events in dates_dict.items():
            # 日付でフィルタ
            if date and date_key != date:
                continue
                
            if not isinstance(events, list):
                continue
                
            for event in events:
                if not isinstance(event, dict):
                    continue
                
                # キーワード検索（タイトル、バッジ）
                if keyword:
                    keyword_lower = keyword.lower()
                    title = event.get('title', '').lower()
                    badge = event.get('badge', '').lower()
                    
                    if keyword_lower not in title and keyword_lower not in badge:
                        continue
                
                # 参加者検索
                if participant:
                    participants = event.get('participants', [])
                    participant_lower = participant.lower()
                    
                    # 参加者リストに含まれているかチェック
                    if not any(participant_lower in p.lower() for p in participants):
                        continue
                
                # 結果に追加
                results.append({
                    'facility': place_name,
                    'date': date_key,
                    'title': event.get('title', ''),
                    'start_time': event.get('start_datetime', ''),
                    'end_time': event.get('end_datetime', ''),
                    'badge': event.get('badge', ''),
                    'participants': event.get('participants', []),
                    'url': event.get('description_url', ''),
                    'id': event.get('id', '')
                })
    
    # 日付と開始時刻でソート
    results.sort(key=lambda x: (x['date'], x['start_time']))
    
    return results

def get_facilities():
    """施設名のリストを取得"""
    data = load_schedule_data()
    return sorted(data.keys())

def get_dates():
    """日付のリストを取得（ソート済み）"""
    data = load_schedule_data()
    dates = set()
    
    for dates_dict in data.values():
        if isinstance(dates_dict, dict):
            dates.update(dates_dict.keys())
    
    return sorted(dates)

@app.route('/')
def index():
    """メインページ"""
    facilities = get_facilities()
    dates = get_dates()
    return render_template('index.html', facilities=facilities, dates=dates)

@app.route('/booking')
def booking():
    """予約ページ"""
    facilities = get_facilities()
    return render_template('booking.html', facilities=facilities)

@app.route('/api/search')
def api_search():
    """検索API"""
    facility = request.args.get('facility', 'all')
    date = request.args.get('date', '')
    keyword = request.args.get('keyword', '')
    participant = request.args.get('participant', '')
    
    results = search_schedules(
        facility=facility if facility != 'all' else None,
        date=date if date else None,
        keyword=keyword if keyword else None,
        participant=participant if participant else None
    )
    
    return jsonify({
        'success': True,
        'count': len(results),
        'results': results
    })

@app.route('/api/facilities')
def api_facilities():
    """施設一覧API"""
    facilities = get_facilities()
    return jsonify({
        'success': True,
        'facilities': facilities
    })

@app.route('/api/dates')
def api_dates():
    """日付一覧API"""
    dates = get_dates()
    return jsonify({
        'success': True,
        'dates': dates
    })

@app.route('/api/stats')
def api_stats():
    """統計情報API"""
    data = load_schedule_data()
    
    total_facilities = len(data)
    total_events = 0
    total_dates = set()
    
    for dates_dict in data.values():
        if isinstance(dates_dict, dict):
            total_dates.update(dates_dict.keys())
            for events in dates_dict.values():
                if isinstance(events, list):
                    total_events += len(events)
    
    return jsonify({
        'success': True,
        'stats': {
            'total_facilities': total_facilities,
            'total_dates': len(total_dates),
            'total_events': total_events
        }
    })

@app.route('/api/events/<facility>/<date>')
def api_events_by_date(facility, date):
    """特定の施設・日付の予定を取得"""
    data = load_schedule_data()
    
    events = []
    if facility in data:
        if isinstance(data[facility], dict) and date in data[facility]:
            events_list = data[facility][date]
            if isinstance(events_list, list):
                for event in events_list:
                    if isinstance(event, dict):
                        events.append({
                            'title': event.get('title', ''),
                            'start_time': event.get('start_datetime', ''),
                            'end_time': event.get('end_datetime', ''),
                            'badge': event.get('badge', ''),
                            'participants': event.get('participants', [])
                        })
    
    return jsonify({
        'success': True,
        'events': events
    })

@app.route('/api/book', methods=['POST'])
def api_book():
    """予約を登録（コンソール出力のみ）"""
    try:
        data = request.get_json()
        
        facility = data.get('facility')
        date = data.get('date')
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        title = data.get('title')
        participants = data.get('participants', [])
        
        # コンソールに出力
        print('\n' + '='*50)
        print('新規予約登録')
        print('='*50)
        print(f'施設: {facility}')
        print(f'日付: {date}')
        print(f'開始時刻: {start_time}')
        print(f'終了時刻: {end_time}')
        print(f'タイトル: {title}')
        print(f'参加者: {", ".join(participants) if participants else "なし"}')
        print('='*50 + '\n')
        
        return jsonify({
            'success': True,
            'message': '予約が登録されました（コンソールに出力）'
        })
    except Exception as e:
        print(f'予約エラー: {e}')
        return jsonify({
            'success': False,
            'message': 'エラーが発生しました'
        }), 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

