# Laravelマイグレーション

このプロジェクトのデータベーステーブルをLaravelのマイグレーションで作成する手順です。

## 📋 必要な環境

- Laravel 10以上
- MySQL 8.0以上
- usersテーブルが既に存在すること（Laravelのデフォルトの認証システム）

## 📁 ファイル構成

```
database/
└── migrations/
    ├── 2024_01_01_000001_create_facilities_table.php
    ├── 2024_01_01_000002_create_schedule_events_table.php
    └── 2024_01_01_000003_create_schedule_participants_table.php

app/
└── Models/
    ├── Facility.php
    ├── ScheduleEvent.php
    └── ScheduleParticipant.php
```

## 🚀 セットアップ手順

### 1. マイグレーションファイルの配置

作成されたマイグレーションファイルをLaravelプロジェクトの`database/migrations/`ディレクトリに配置してください。

```bash
# マイグレーションファイルをコピー
cp database/migrations/*.php /path/to/laravel-project/database/migrations/
```

### 2. モデルファイルの配置

モデルファイルをLaravelプロジェクトの`app/Models/`ディレクトリに配置してください。

```bash
# モデルファイルをコピー
cp app/Models/*.php /path/to/laravel-project/app/Models/
```

### 3. usersテーブルの確認

Laravelのデフォルトのusersテーブルが存在することを確認してください。もし存在しない場合は、以下を実行：

```bash
php artisan migrate
```

または、usersテーブルに`name`カラムがあることを確認してください：

```php
// database/migrations/xxxx_create_users_table.php
Schema::create('users', function (Blueprint $table) {
    $table->id();
    $table->string('name');
    $table->string('email')->unique();
    // ... その他のカラム
});
```

### 4. マイグレーションの実行

```bash
php artisan migrate
```

これで以下の3つのテーブルが作成されます：
- `facilities` - 施設マスタ
- `schedule_events` - 予定テーブル
- `schedule_participants` - 参加者テーブル（user_idでusersテーブルと紐づけ）

## 📊 テーブル構造

### facilities

```php
Schema::create('facilities', function (Blueprint $table) {
    $table->id();
    $table->string('name')->unique();
    $table->timestamps();
});
```

### schedule_events

```php
Schema::create('schedule_events', function (Blueprint $table) {
    $table->id();
    $table->foreignId('facility_id')->constrained('facilities')->onDelete('cascade');
    $table->date('date');
    $table->string('title', 500);
    $table->string('start_datetime', 10);
    $table->string('end_datetime', 10);
    $table->string('badge', 100)->nullable();
    $table->text('description_url')->nullable();
    $table->timestamps();
    
    $table->unique(['facility_id', 'date', 'description_url'], 'unique_event');
    $table->index(['facility_id', 'date']);
    $table->index('date');
});
```

### schedule_participants

```php
Schema::create('schedule_participants', function (Blueprint $table) {
    $table->id();
    $table->foreignId('schedule_event_id')->constrained('schedule_events')->onDelete('cascade');
    $table->foreignId('user_id')->constrained('users')->onDelete('cascade');
    $table->timestamps();
    
    $table->unique(['schedule_event_id', 'user_id']);
    $table->index('schedule_event_id');
    $table->index('user_id');
});
```

## 🔗 リレーション

### Facility モデル

```php
// 施設の予定一覧
$facility = Facility::find(1);
$events = $facility->scheduleEvents;
```

### ScheduleEvent モデル

```php
// 予定の施設
$event = ScheduleEvent::find(1);
$facility = $event->facility;

// 予定の参加者（ユーザー）
$participants = $event->participants;
```

### User モデル

Userモデルにリレーションを追加する場合：

```php
// app/Models/User.php
use Illuminate\Database\Eloquent\Relations\BelongsToMany;

public function scheduleEvents(): BelongsToMany
{
    return $this->belongsToMany(ScheduleEvent::class, 'schedule_participants')
        ->withTimestamps();
}
```

使用例：

```php
// ユーザーの参加予定
$user = User::find(1);
$events = $user->scheduleEvents;
```

### ScheduleParticipant モデル

中間テーブル用のモデルです。通常は`BelongsToMany`リレーションで十分ですが、中間テーブルに直接アクセスしたい場合に使用します。

使用例：

```php
// 中間テーブルに直接アクセス
$participant = ScheduleParticipant::where('schedule_event_id', 1)
    ->where('user_id', 1)
    ->first();

// 予定とユーザーを取得
$event = $participant->scheduleEvent;
$user = $participant->user;

// 参加日時を取得
$joinedAt = $participant->created_at;
```

**注意**: 
- 通常は`ScheduleEvent`の`participants()`リレーションを使用する方が簡単です
- 中間テーブルに直接アクセスする必要がある場合のみ、このモデルを使用してください

## 🔧 main.pyの設定

### データベース接続設定

`main.py`の`DB_CONFIG`をLaravelプロジェクトのデータベース設定に合わせてください：

```python
DB_CONFIG = {
    'host': 'localhost',
    'database': 'your_laravel_database',  # Laravelのデータベース名
    'user': 'your_database_user',
    'password': 'your_database_password',
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci'
}
```

### usersテーブルのnameカラム

`main.py`は`users`テーブルの`name`カラムでユーザーを検索します。Laravelのデフォルトのusersテーブルに`name`カラムがあることを確認してください。

もし`name`カラムが存在しない場合、または別のカラム名を使用している場合は、`get_user_id_by_name`関数を修正してください：

```python
def get_user_id_by_name(connection, user_name):
    """ユーザー名からユーザーIDを取得"""
    cursor = connection.cursor()
    
    # 例: emailカラムで検索する場合
    # cursor.execute("SELECT id FROM users WHERE email = %s", (user_name,))
    
    # nameカラムで検索（デフォルト）
    cursor.execute("SELECT id FROM users WHERE name = %s", (user_name,))
    result = cursor.fetchone()
    
    user_id = result[0] if result else None
    cursor.close()
    return user_id
```

## 📝 使用例

### 施設の作成

```php
$facility = Facility::create([
    'name' => '社長室',
]);
```

### 予定の作成

```php
$event = ScheduleEvent::create([
    'facility_id' => 1,
    'date' => '2025-11-10',
    'title' => '営業会議',
    'start_datetime' => '10:00',
    'end_datetime' => '12:00',
    'badge' => '会議',
    'description_url' => 'https://...',
]);
```

### 参加者の追加

```php
$event = ScheduleEvent::find(1);
$user = User::find(1);

// 参加者を追加
$event->participants()->attach($user->id);

// または複数の参加者を追加
$event->participants()->attach([1, 2, 3]);
```

### 参加者の取得

```php
$event = ScheduleEvent::find(1);
$participants = $event->participants;

foreach ($participants as $participant) {
    echo $participant->name;
}
```

### ユーザーの参加予定を取得

```php
$user = User::find(1);
$events = $user->scheduleEvents()->where('date', '>=', now())->get();
```

## 🔍 クエリ例

### 特定の施設の今日の予定

```php
$today = now()->format('Y-m-d');
$events = ScheduleEvent::where('facility_id', 1)
    ->where('date', $today)
    ->with('participants')
    ->get();
```

### 特定のユーザーが参加する予定

```php
$userId = 1;
$events = ScheduleEvent::whereHas('participants', function ($query) use ($userId) {
    $query->where('users.id', $userId);
})->get();
```

### 参加者数の多い予定

```php
$events = ScheduleEvent::withCount('participants')
    ->orderBy('participants_count', 'desc')
    ->get();
```

## 🐛 トラブルシューティング

### 外部キー制約エラー

**エラー**: `Cannot add or update a child row: a foreign key constraint fails`

**対処**:
1. usersテーブルが存在することを確認
2. 参照するuser_idがusersテーブルに存在することを確認

### ユーザーが見つからない

**エラー**: `ユーザーが見つかりません`

**対処**:
1. usersテーブルに`name`カラムがあることを確認
2. ユーザー名が正確に一致していることを確認（スペース、全角半角など）
3. `get_user_id_by_name`関数を修正して、別のカラムで検索するように変更

### マイグレーションエラー

**エラー**: `Table already exists`

**対処**:
```bash
# テーブルを削除してから再実行
php artisan migrate:fresh
```

または、既存のテーブルを確認：

```bash
php artisan migrate:status
```

## 📚 関連ドキュメント

- [Laravelマイグレーション公式ドキュメント](https://laravel.com/docs/migrations)
- [Eloquentリレーション公式ドキュメント](https://laravel.com/docs/eloquent-relationships)
- `README_MYSQL.md` - データベース設定の詳細

