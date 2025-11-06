# MySQLデータベース連携

`main.py`をMySQLデータベースに接続して、スケジュールデータを保存するように変更しました。

## 📋 必要な環境

### 1. MySQLのインストール

MySQL 8.0以上をインストールしてください。

**Windows**:
```bash
# MySQL公式サイトからダウンロード
# https://dev.mysql.com/downloads/mysql/
```

**インストール確認**:
```bash
mysql --version
```

### 2. データベースの作成

MySQLにログインして、データベースを作成します：

```sql
CREATE DATABASE schedule_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

## ⚙️ 設定

### データベース設定の変更

`main.py`の`DB_CONFIG`を編集してください：

```python
DB_CONFIG = {
    'host': 'localhost',        # MySQLサーバーのホスト
    'database': 'schedule_db',  # データベース名
    'user': 'root',             # ユーザー名
    'password': 'your_password', # パスワード
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci'
}
```

## 📦 必要なパッケージのインストール

```bash
pip install mysql-connector-python
```

または、すべてのパッケージを一括インストール：

```bash
pip install -r requirements.txt
```

## 🗄️ データベース構造

### テーブル構成

#### 1. `facilities` - 施設マスタ

```sql
CREATE TABLE facilities (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

#### 2. `schedule_events` - 予定テーブル

```sql
CREATE TABLE schedule_events (
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
);
```

#### 3. `schedule_participants` - 参加者テーブル

```sql
CREATE TABLE schedule_participants (
    id INT AUTO_INCREMENT PRIMARY KEY,
    schedule_event_id INT NOT NULL,
    participant_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (schedule_event_id) REFERENCES schedule_events(id) ON DELETE CASCADE,
    INDEX idx_event (schedule_event_id)
);
```

## 🚀 使用方法

### 1. データベース接続の確認

```bash
mysql -u root -p
```

```sql
USE schedule_db;
SHOW TABLES;
```

### 2. プログラムの実行

```bash
python main.py
```

初回実行時に、テーブルが自動的に作成されます。

### 3. データの確認

```sql
-- 施設一覧
SELECT * FROM facilities;

-- 予定一覧
SELECT 
    f.name as facility,
    se.date,
    se.title,
    se.start_datetime,
    se.end_datetime,
    se.badge
FROM schedule_events se
JOIN facilities f ON se.facility_id = f.id
ORDER BY se.date, se.start_datetime;

-- 参加者一覧
SELECT 
    se.title,
    sp.participant_name
FROM schedule_participants sp
JOIN schedule_events se ON sp.schedule_event_id = se.id
ORDER BY se.date;
```

## 🔄 機能

### 自動テーブル作成

初回実行時に、テーブルが自動的に作成されます：
- `facilities` - 施設マスタ
- `schedule_events` - 予定テーブル
- `schedule_participants` - 参加者テーブル

### データ同期

- **追加**: 新規予定を自動追加
- **更新**: 変更された予定を自動更新（IDは保持）
- **削除**: Cybozuから削除された予定を自動削除
- **参加者**: 参加者情報も自動取得・更新

### トランザクション管理

各操作はトランザクションで実行されるため、エラー時は自動的にロールバックされます。

## 📊 データの移行

既存の`schedule.json`からデータベースに移行する場合：

```python
# migrate_json_to_db.py (別途作成が必要)
import json
import mysql.connector

# schedule.jsonを読み込む
with open('schedule.json', 'r', encoding='utf-8') as f:
    schedule_data = json.load(f)

# データベースに移行
# (実装が必要)
```

## 🐛 トラブルシューティング

### 接続エラー

**エラー**: `mysql.connector.errors.ProgrammingError: Access denied`

**対処**:
1. ユーザー名とパスワードを確認
2. MySQLのユーザー権限を確認

```sql
GRANT ALL PRIVILEGES ON schedule_db.* TO 'root'@'localhost';
FLUSH PRIVILEGES;
```

### テーブルが見つからない

**エラー**: `Table 'schedule_db.facilities' doesn't exist`

**対処**:
```bash
python main.py
```

初回実行時に自動的にテーブルが作成されます。

### 文字化け

**エラー**: 日本語が文字化けする

**対処**:
データベースとテーブルの文字コードを確認：

```sql
ALTER DATABASE schedule_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 外部キー制約エラー

**エラー**: `Cannot add or update a child row: a foreign key constraint fails`

**対処**:
施設マスタが正しく作成されているか確認：

```sql
SELECT * FROM facilities;
```

## 📝 データベース設定の変更

### リモートMySQLサーバーに接続

```python
DB_CONFIG = {
    'host': '192.168.1.100',  # リモートサーバーのIP
    'database': 'schedule_db',
    'user': 'remote_user',
    'password': 'remote_password',
    'port': 3306,  # ポート番号
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci'
}
```

### 接続プールの使用

大量のデータを扱う場合は、接続プールを使用できます：

```python
from mysql.connector import pooling

config = {
    'user': 'root',
    'password': 'password',
    'host': 'localhost',
    'database': 'schedule_db',
    'pool_name': 'mypool',
    'pool_size': 5
}

connection_pool = pooling.MySQLConnectionPool(**config)
```

## 🔒 セキュリティ

### パスワードの管理

パスワードは環境変数や設定ファイルから読み込むことを推奨：

```python
import os

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'schedule_db'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci'
}
```

### バックアップ

定期的にデータベースをバックアップ：

```bash
mysqldump -u root -p schedule_db > schedule_db_backup.sql
```

### 復元

```bash
mysql -u root -p schedule_db < schedule_db_backup.sql
```

## 📈 パフォーマンス

### インデックスの確認

```sql
SHOW INDEX FROM schedule_events;
```

### クエリの最適化

```sql
EXPLAIN SELECT * FROM schedule_events WHERE facility_id = 1 AND date = '2025-11-05';
```

## 🔄 JSONとの互換性

データベースに保存されたデータをJSON形式でエクスポート：

```sql
-- JSON形式で出力（MySQL 5.7.8+）
SELECT JSON_OBJECT(
    'facility', f.name,
    'date', DATE_FORMAT(se.date, '%Y-%m-%d'),
    'title', se.title,
    'start_datetime', se.start_datetime,
    'end_datetime', se.end_datetime,
    'badge', se.badge
) as json_data
FROM schedule_events se
JOIN facilities f ON se.facility_id = f.id;
```

## 📚 関連ドキュメント

- [MySQL公式ドキュメント](https://dev.mysql.com/doc/)
- [mysql-connector-python公式ドキュメント](https://dev.mysql.com/doc/connector-python/en/)
- `README_SYNC.md` - 同期機能の詳細
- `README_LOGGING.md` - ログ機能の詳細

