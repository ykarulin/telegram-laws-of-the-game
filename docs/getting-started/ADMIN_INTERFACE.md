# Admin Interface Documentation

## Overview

The admin interface allows authorized administrators to monitor the bot's operations in real-time with configurable monitoring levels (error, info, debug). All communication happens in private direct messages only.

## Configuration

### Setup in `.env`

Add admin user IDs as a comma-separated list in your `.env` file:

```env
ADMIN_USER_IDS=123456789,987654321
```

If no admin IDs are configured, the admin interface is effectively disabled.

## Monitoring Levels

Each admin can set their own monitoring level independently:

### 1. **error** (Default)
- Receives only error messages
- Format: `⚠️ **Error**`
- Includes: Error message + User ID who caused it
- **When triggered**: An unrecoverable error occurs during message processing (LLM errors, API failures, etc.)

### 2. **info**
- Receives errors + bot response notifications
- Includes both error messages and confirmations that the bot replied to users
- Format: `ℹ️ **Response Sent**`
- Includes: User ID + First 200 chars of the response
- **When triggered**: After successfully sending a response to a user

### 3. **debug**
- Receives everything (errors, incoming messages, tool calls, responses)
- Three notification types:
  - **Incoming messages**: `🔵 **Incoming Message**` - User ID + first 150 chars of message
  - **Tool calls**: `🔧 **Tool Call**` - Tool name + parameters (with sensitive data redacted)
  - **Bot replies**: `💬 **Bot Reply**` - User ID + first 150 chars of response
- **When triggered**: For every significant event in message processing

## Admin Commands

All commands are available via `/command` in private messages with the bot.

### `/help`
Displays comprehensive help information about available admin commands and monitoring levels.

**Usage:**
```
/help
```

**Response:** Shows all available commands with explanations and level descriptions.

### `/monitor [level|status]`
Set your monitoring level or check your current level.

**Usage:**
```
/monitor debug     # Set to debug (all notifications)
/monitor info      # Set to info (errors + responses)
/monitor error     # Set to error (errors only)
/monitor status    # Check current monitoring level
```

**Response:** Confirmation message with the new (or current) monitoring level.

## Database Schema

### Admin Preferences Table
```
admin_preferences
├── id (Integer, PK, Auto)
├── user_id (Integer, Unique, Index) - Telegram user ID
├── monitoring_level (String) - 'error', 'info', or 'debug'
├── created_at (DateTime, UTC)
└── updated_at (DateTime, UTC, Auto)
```

**Auto-creation:** Admin preferences are automatically created on first `/monitor` command with default level 'error'.

## Sensitive Data Redaction

The admin interface automatically redacts sensitive information from all notifications:

- **API Keys**: `sk-...` patterns, `api_key=...` → `***REDACTED***`
- **Tokens**: `token_...` patterns → `***REDACTED***`
- **Database URLs**: `postgresql://user:password@host` → `postgresql://user:***REDACTED***@host`
- **Generic patterns**: Any `key=value` with credential-like names

This ensures that admins can see what's happening without exposing secrets in notifications.

## Implementation Details

### Files Modified/Created

1. **src/config.py**
   - Added `admin_user_ids: list[int]` field
   - Parse comma-separated admin IDs from `ADMIN_USER_IDS` environment variable

2. **src/core/db.py**
   - Added `MonitoringLevel` enum (error, info, debug)
   - Added `AdminPreferenceModel` SQLAlchemy model
   - Added methods:
     - `get_or_create_admin_preference(user_id, default_level)`
     - `update_admin_monitoring_level(user_id, level)`
     - `get_admin_monitoring_level(user_id)`

3. **src/services/admin_service.py** (NEW)
   - `AdminService` class handles all admin notifications
   - Methods:
     - `is_admin(user_id)` - Check if user is admin
     - `get_monitoring_level(user_id)` - Retrieve admin's level
     - `set_monitoring_level(user_id, level)` - Update admin's level
     - `redact_sensitive_data(text)` - Redact secrets from text
     - `send_error_notification()` - Send error alerts
     - `send_info_notification()` - Send response confirmations
     - `send_debug_notification()` - Send debug events
     - `send_admin_help()` - Send help text

4. **src/handlers/admin_handler.py** (NEW)
   - `AdminHandler` class processes admin commands
   - Methods:
     - `handle_monitor_command()` - Process `/monitor` command
     - `handle_help_command()` - Process `/help` command

5. **src/handlers/message_handler.py**
   - Added `admin_service` parameter to constructor
   - Integrated monitoring notifications:
     - Send debug notification on incoming message
     - Send info notification on successful response
     - Send error notification on LLM errors
   - Private helper methods:
     - `_notify_admins_incoming_message()`
     - `_notify_admins_info()`
     - `_notify_admins_error()`

6. **src/bot_factory.py**
   - Initialize `AdminService` with config admin IDs
   - Create `AdminHandler` instance
   - Pass admin_service to `MessageHandler`
   - Register `/monitor` and `/help` command handlers

## Message Flow

### Incoming User Message
```
User sends message
    ↓
MessageHandler receives it
    ↓
Send debug notification to admins with level "debug"
    (Shows: User ID + message text)
    ↓
Process message normally
    ↓
If error occurs → Send error notification
    (Shows: User ID + error message, to admins with level >= "error")
    ↓
If successful → Send info notification
    (Shows: User ID + response text, to admins with level >= "info")
```

### Admin Modifying Their Monitoring Level
```
Admin sends /monitor [level]
    ↓
AdminHandler processes command
    ↓
Validates level (error|info|debug)
    ↓
Updates/creates admin preference in database
    ↓
Sends confirmation to admin
```

## Important Notes

1. **Private Messages Only**: All admin commands only work in private 1-on-1 chats with the bot. Commands in group chats are rejected.

2. **Per-Admin Settings**: Each admin can independently set their own monitoring level. Changes don't affect other admins.

3. **Persistent Storage**: Monitoring levels are stored in the database and persist across bot restarts.

4. **Performance**: Admin notifications are sent asynchronously and don't block user message processing.

5. **No Message Queue Limits**: Unlike user messages, admin notifications are not rate-limited (to ensure admins stay informed).

6. **Security**: Only exact user IDs in `ADMIN_USER_IDS` are recognized. Usernames are not sufficient.

## Example Usage

### Setting Up an Admin
1. Get your Telegram user ID (you can use a bot like `@userinfobot`)
2. Add to `.env`: `ADMIN_USER_IDS=123456789`
3. Restart the bot
4. Send `/help` to the bot in a private message
5. Send `/monitor debug` to see all activity

### Monitoring a Production Issue
1. Set monitoring to `debug`: `/monitor debug`
2. Wait for errors to occur (notifications come automatically)
3. Review what failed in real-time
4. Switch back to `error` level: `/monitor error`

### Quiet Monitoring
1. Set to `error` level: `/monitor error` (or keep default)
2. Only get notifications when something goes wrong
3. Check status anytime: `/monitor status`

## Troubleshooting

**No notifications received?**
- Verify your user ID is in `ADMIN_USER_IDS`
- Check `/monitor status` to see current level
- Ensure you're sending private messages (not group)
- Check bot logs for errors

**Sensitive data being logged?**
- AdminService automatically redacts API keys, tokens, and credentials
- If more patterns need redacting, update `redact_sensitive_data()` method in AdminService

**Commands not working?**
- Must be in private DM with bot (not group chat)
- Must be an authorized admin (check `ADMIN_USER_IDS`)
- Use exact syntax: `/monitor debug` (with space)
